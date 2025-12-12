"""SQLite-based thumbnail cache manager.

This module provides persistent thumbnail caching using SQLite database
for fast thumbnail retrieval and reduced disk I/O.
"""

from __future__ import annotations

import platform
import sqlite3
import time
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QPixmap

try:
    import ctypes
except Exception:
    ctypes = None

from image_viewer.logger import get_logger

_logger = get_logger("thumbnail_cache")


class ThumbnailCache:
    """Manages thumbnail cache using SQLite database."""

    def __init__(self, cache_dir: Path, db_name: str = "thumbs.db"):
        """Initialize thumbnail cache.

        Args:
            cache_dir: Directory to store the cache database
            db_name: Name of the database file
        """
        self.cache_dir = cache_dir
        self.db_path = cache_dir / db_name
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database and create tables if needed."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)

            # Set hidden attribute on Windows
            self._set_hidden_attribute()
            # Unified cache table: metadata is always storable; thumbnail may be NULL until generated.
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS thumbnails (
                    path TEXT PRIMARY KEY,
                    mtime REAL NOT NULL,
                    size INTEGER NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    thumb_width INTEGER NOT NULL,
                    thumb_height INTEGER NOT NULL,
                    thumbnail BLOB,
                    created_at REAL NOT NULL
                )
            """)

            # Migrate older DBs that had `thumbnail BLOB NOT NULL`.
            try:
                cols = self._conn.execute("PRAGMA table_info(thumbnails)").fetchall()
                # columns: (cid, name, type, notnull, dflt_value, pk)
                thumb_info = next((c for c in cols if c[1] == "thumbnail"), None)
                if thumb_info is not None and int(thumb_info[3]) == 1:
                    self._conn.execute("""
                        CREATE TABLE thumbnails__new (
                            path TEXT PRIMARY KEY,
                            mtime REAL NOT NULL,
                            size INTEGER NOT NULL,
                            width INTEGER,
                            height INTEGER,
                            thumb_width INTEGER NOT NULL,
                            thumb_height INTEGER NOT NULL,
                            thumbnail BLOB,
                            created_at REAL NOT NULL
                        )
                    """)
                    self._conn.execute("""
                        INSERT INTO thumbnails__new (
                            path, mtime, size, width, height,
                            thumb_width, thumb_height, thumbnail, created_at
                        )
                        SELECT
                            path, mtime, size, width, height,
                            thumb_width, thumb_height, thumbnail, created_at
                        FROM thumbnails
                    """)
                    self._conn.execute("DROP TABLE thumbnails")
                    self._conn.execute("ALTER TABLE thumbnails__new RENAME TO thumbnails")
                    self._conn.commit()
                    _logger.debug("thumbnail cache migrated: thumbnail column is now nullable")
            except Exception as exc:
                _logger.debug("thumbnail cache migration skipped/failed: %s", exc)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_mtime ON thumbnails(mtime)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at ON thumbnails(created_at)
            """)
            self._conn.commit()
            _logger.debug("thumbnail cache initialized: %s", self.db_path)
        except Exception as exc:
            _logger.error("failed to initialize thumbnail cache: %s", exc)

    def set_meta(  # noqa: PLR0913
        self,
        path: str,
        mtime: float,
        size: int,
        width: int | None,
        height: int | None,
        thumb_width: int,
        thumb_height: int,
    ) -> None:
        """Upsert metadata without writing any thumbnail bytes."""
        if not self._conn:
            return

        try:
            # Keep schema coherent: meta can exist even when thumbnail is not yet generated.
            # If the file changed (mtime/size), any previous thumbnail is treated as stale.
            self._conn.execute(
                """
                INSERT INTO thumbnails
                (path, mtime, size, width, height, thumb_width, thumb_height, thumbnail, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(path) DO UPDATE SET
                    mtime=excluded.mtime,
                    size=excluded.size,
                    width=excluded.width,
                    height=excluded.height,
                    thumb_width=excluded.thumb_width,
                    thumb_height=excluded.thumb_height,
                    thumbnail=NULL,
                    created_at=excluded.created_at
                """,
                (
                    path,
                    mtime,
                    size,
                    width,
                    height,
                    thumb_width,
                    thumb_height,
                    time.time(),
                ),
            )
            self._conn.commit()
        except Exception as exc:
            _logger.debug("failed to save metadata to cache: %s", exc)

    def get_meta(self, path: str, mtime: float, size: int) -> tuple[int | None, int | None] | None:
        """Get cached metadata (width/height) without loading any thumbnail blob."""
        if not self._conn:
            return None

        try:
            cursor = self._conn.execute(
                """
                SELECT width, height
                FROM thumbnails
                WHERE path = ? AND mtime = ? AND size = ?
                """,
                (path, mtime, size),
            )
            row = cursor.fetchone()
            if not row:
                return None
            width, height = row
            return width, height
        except Exception as exc:
            _logger.debug("failed to get metadata from cache: %s", exc)
            return None

    def clear_thumbnail(self, path: str) -> None:
        """Clear only the thumbnail blob for a path (preserve metadata)."""
        if not self._conn:
            return

        try:
            self._conn.execute("UPDATE thumbnails SET thumbnail = NULL WHERE path = ?", (path,))
            self._conn.commit()
        except Exception as exc:
            _logger.debug("failed to clear thumbnail for %s: %s", path, exc)

    def delete(self, path: str) -> None:
        """Delete a cache row for a path."""
        if not self._conn:
            return

        try:
            self._conn.execute("DELETE FROM thumbnails WHERE path = ?", (path,))
            self._conn.commit()
        except Exception as exc:
            _logger.debug("failed to delete cache entry for %s: %s", path, exc)

    def get(  # noqa: PLR0911
        self, path: str, mtime: float, size: int, thumb_width: int, thumb_height: int
    ) -> tuple[QPixmap, int | None, int | None] | None:
        """Get thumbnail from cache.

        Returns:
            Tuple of (pixmap, original_width, original_height) or None if not found.
        """
        if not self._conn:
            return None

        try:
            cursor = self._conn.execute(
                """
                SELECT thumbnail, width, height, thumb_width, thumb_height
                FROM thumbnails
                WHERE path = ? AND mtime = ? AND size = ?
                """,
                (path, mtime, size),
            )
            row = cursor.fetchone()
            if not row:
                return None

            thumbnail_data, orig_width, orig_height, cached_tw, cached_th = row

            # Metadata rows may exist without a thumbnail.
            if thumbnail_data is None:
                return None

            # Check if thumbnail size matches
            if cached_tw != thumb_width or cached_th != thumb_height:
                return None

            pixmap = QPixmap()
            if not pixmap.loadFromData(thumbnail_data):
                _logger.debug("failed to load pixmap from cache: %s (corrupt blob)", path)
                # Keep metadata but drop the corrupt thumbnail so future loads can re-decode.
                try:
                    self._conn.execute("UPDATE thumbnails SET thumbnail = NULL WHERE path = ?", (path,))
                    self._conn.commit()
                    _logger.debug("cleared corrupt thumbnail blob for path: %s", path)
                except Exception:
                    pass
                return None

            return pixmap, orig_width, orig_height
        except Exception as exc:
            _logger.debug("failed to get thumbnail from cache: %s", exc)
            return None

    def set(  # noqa: PLR0913
        self,
        path: str,
        mtime: float,
        size: int,
        width: int | None,
        height: int | None,
        thumb_width: int,
        thumb_height: int,
        pixmap: QPixmap,
    ) -> None:
        """Save thumbnail to cache.

        Args:
            path: Image file path
            mtime: File modification time
            size: File size in bytes
            width: Original image width
            height: Original image height
            thumb_width: Thumbnail width
            thumb_height: Thumbnail height
            pixmap: Thumbnail pixmap
        """
        if not self._conn:
            return

        try:
            # Convert pixmap to PNG bytes
            if pixmap.isNull():
                return

            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if not pixmap.save(buffer, "PNG"):
                return

            thumbnail_data = buffer.data().data()
            if not thumbnail_data:
                return

            self._conn.execute(
                """
                INSERT OR REPLACE INTO thumbnails
                (path, mtime, size, width, height, thumb_width, thumb_height, thumbnail, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    path,
                    mtime,
                    size,
                    width,
                    height,
                    thumb_width,
                    thumb_height,
                    thumbnail_data,
                    time.time(),
                ),
            )
            self._conn.commit()
        except Exception as exc:
            _logger.debug("failed to save thumbnail to cache: %s", exc)

    def cleanup_old(self, days: int = 30) -> int:
        """Remove thumbnails older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of thumbnails removed
        """
        if not self._conn:
            return 0

        try:
            cutoff = time.time() - (days * 86400)
            cursor = self._conn.execute("DELETE FROM thumbnails WHERE created_at < ?", (cutoff,))
            self._conn.commit()
            count = cursor.rowcount
            _logger.debug("cleaned up %d old thumbnails", count)
            return count
        except Exception as exc:
            _logger.error("failed to cleanup old thumbnails: %s", exc)
            return 0

    def vacuum(self) -> None:
        """Optimize database by reclaiming unused space."""
        if not self._conn:
            return

        try:
            self._conn.execute("VACUUM")
            _logger.debug("database vacuumed")
        except Exception as exc:
            _logger.error("failed to vacuum database: %s", exc)

    def _set_hidden_attribute(self) -> None:
        """Set hidden attribute on Windows."""
        try:
            if platform.system() != "Windows":
                return

            if not self.db_path.exists():
                return

            if ctypes is None:
                return

            # FILE_ATTRIBUTE_HIDDEN = 0x02
            ctypes.windll.kernel32.SetFileAttributesW(str(self.db_path), 0x02)
            _logger.debug("set hidden attribute on %s", self.db_path)
        except Exception as exc:
            _logger.debug("failed to set hidden attribute: %s", exc)

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            try:
                self._conn.close()
                self._conn = None
            except Exception as exc:
                _logger.error("failed to close database: %s", exc)

    def __del__(self):
        """Cleanup on deletion."""
        self.close()
