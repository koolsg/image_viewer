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
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS thumbnails (
                    path TEXT PRIMARY KEY,
                    mtime REAL NOT NULL,
                    size INTEGER NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    thumb_width INTEGER NOT NULL,
                    thumb_height INTEGER NOT NULL,
                    thumbnail BLOB NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
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

    def get(
        self, path: str, mtime: float, size: int, thumb_width: int, thumb_height: int
    ) -> tuple[QPixmap, int | None, int | None] | None:
        """Get thumbnail from cache.

        Args:
            path: Image file path
            mtime: File modification time
            size: File size in bytes
            thumb_width: Expected thumbnail width
            thumb_height: Expected thumbnail height

        Returns:
            Tuple of (pixmap, original_width, original_height) or None if not found
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

            # Check if thumbnail size matches
            if cached_tw != thumb_width or cached_th != thumb_height:
                return None

            # Load pixmap from blob
            pixmap = QPixmap()
            if not pixmap.loadFromData(thumbnail_data):
                _logger.debug("failed to load pixmap from cache: %s (corrupt blob)", path)
                # Remove the corrupt DB entry so future loads can re-decode
                try:
                    self._conn.execute("DELETE FROM thumbnails WHERE path = ?", (path,))
                    self._conn.commit()
                    _logger.debug("removed corrupt thumbnail entry for path: %s", path)
                except Exception:
                    pass
                return None

            return pixmap, orig_width, orig_height
        except Exception as exc:
            _logger.debug("failed to get thumbnail from cache: %s", exc)
            return None

    def get_batch(
        self, paths_with_stats: list[tuple[str, float, int]], thumb_width: int, thumb_height: int
    ) -> dict[str, tuple[QPixmap, int | None, int | None]]:
        """Get multiple thumbnails from cache in a single query.

        Args:
            paths_with_stats: List of (path, mtime, size) tuples
            thumb_width: Expected thumbnail width
            thumb_height: Expected thumbnail height

        Returns:
            Dictionary mapping path to (pixmap, original_width, original_height)
        """
        if not self._conn or not paths_with_stats:
            return {}

        try:
            # Build query with multiple conditions
            placeholders = ",".join(["(?, ?, ?)"] * len(paths_with_stats))
            query = f"""
                SELECT path, thumbnail, width, height, thumb_width, thumb_height
                FROM thumbnails
                WHERE (path, mtime, size) IN ({placeholders})
            """

            # Flatten the list of tuples for query parameters
            params = []
            for path, mtime, size in paths_with_stats:
                params.extend([path, mtime, size])

            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()

            # Process results
            results = {}
            for row in rows:
                path, thumbnail_data, orig_width, orig_height, cached_tw, cached_th = row

                # Check if thumbnail size matches
                if cached_tw != thumb_width or cached_th != thumb_height:
                    continue

                # Load pixmap from blob
                pixmap = QPixmap()
                if pixmap.loadFromData(thumbnail_data):
                    results[path] = (pixmap, orig_width, orig_height)
                else:
                    _logger.debug("batch_get: corrupt thumbnail blob removed for %s", path)
                    try:
                        self._conn.execute("DELETE FROM thumbnails WHERE path = ?", (path,))
                        self._conn.commit()
                    except Exception:
                        pass

            _logger.debug("batch loaded %d/%d thumbnails", len(results), len(paths_with_stats))
            return results
        except Exception as exc:
            _logger.debug("failed to batch get thumbnails: %s", exc)
            return {}

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
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            pixmap.save(buffer, "PNG")
            thumbnail_data = buffer.data().data()

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
