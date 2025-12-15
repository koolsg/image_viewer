"""ThumbnailCache: UI-facing cache that stores thumbnails in SQLite.

This class uses the pure-DB adapter available under
`image_viewer.image_engine.db.thumbnail_db.ThumbDBBytesAdapter` and keeps
`QPixmap`/`QBuffer` conversions in the UI layer.
"""

from __future__ import annotations

import contextlib
import platform
import time
import weakref
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QPixmap

from image_viewer.image_engine.db.db_operator import DbOperator
from image_viewer.image_engine.db.migrations import apply_migrations
from image_viewer.image_engine.db.thumbdb_bytes_adapter import ThumbDBBytesAdapter
from image_viewer.logger import get_logger
from image_viewer.path_utils import db_key

try:
    import ctypes
except Exception:
    ctypes = None

_logger = get_logger("thumbnail_cache")

_EPOCH_MS_THRESHOLD = 10**11


class ThumbnailCache:
    """Manages thumbnail cache using SQLite database and Qt Pixmaps."""

    @staticmethod
    def _to_mtime_ms(mtime: float | int) -> int:
        try:
            value = float(mtime)
        except Exception:
            return 0
        if value >= _EPOCH_MS_THRESHOLD:
            return int(value)
        return round(value * 1000.0)

    @staticmethod
    def _norm_path(path: str) -> str:
        return db_key(path)

    @staticmethod
    def _mtime_matches(db_mtime: float | None, current_mtime: float | int) -> bool:
        if db_mtime is None:
            return False
        try:
            return int(db_mtime) == ThumbnailCache._to_mtime_ms(current_mtime)
        except Exception:
            return False

    def probe(self, path: str) -> dict[str, object] | None:
        path_norm = self._norm_path(path)
        if self._thumb_db is not None:
            try:
                row = self._thumb_db.probe(path_norm)
                if not row and path_norm != path:
                    row = self._thumb_db.probe(path)
                if not row:
                    return None
                db_path, thumbnail, _w, _h, db_mtime, db_size, tw, th, _created = row
                return {
                    "path": db_path,
                    "mtime": int(db_mtime) if db_mtime is not None else None,
                    "size": int(db_size) if db_size is not None else None,
                    "thumb_width": int(tw) if tw is not None else None,
                    "thumb_height": int(th) if th is not None else None,
                    "has_thumbnail": thumbnail is not None,
                    "thumbnail_len": len(thumbnail) if thumbnail is not None else 0,
                }
            except Exception:
                pass
        return None

    def __init__(self, cache_dir: Path, db_name: str = "thumbs.db"):
        self.cache_dir = cache_dir
        self.db_path = cache_dir / db_name
        self._thumb_db: ThumbDBBytesAdapter | None = None
        try:
            # Prefer operator-backed adapter
            self._db_operator: DbOperator | None = DbOperator(self.db_path)
            self._operator_owned = True
            self._thumb_db = ThumbDBBytesAdapter(self.db_path, operator=self._db_operator)
        except Exception:
            self._db_operator = None
            self._operator_owned = False
            self._thumb_db = None
        self._init_db()
        if self._thumb_db is None:
            raise RuntimeError("ThumbnailCache requires a DbOperator; operator creation failed")
        self._finalizer = weakref.finalize(self, self.close)

    def _init_db(self) -> None:
        """Initialize database and create tables if needed."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            # Use the DbOperator to initialize the schema if available.
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._set_hidden_attribute()

            def _schema_init(conn):
                conn.execute("""
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
                    cols = conn.execute("PRAGMA table_info(thumbnails)").fetchall()
                    thumb_info = next((c for c in cols if c[1] == "thumbnail"), None)
                    if thumb_info is not None and int(thumb_info[3]) == 1:
                        conn.execute("""
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
                        conn.execute("""
                            INSERT INTO thumbnails__new (
                                path, mtime, size, width, height,
                                thumb_width, thumb_height, thumbnail, created_at
                            )
                            SELECT
                                path, mtime, size, width, height,
                                thumb_width, thumb_height, thumbnail, created_at
                            FROM thumbnails
                        """)
                        conn.execute("DROP TABLE thumbnails")
                        conn.execute("ALTER TABLE thumbnails__new RENAME TO thumbnails")
                except Exception:
                    pass
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mtime ON thumbnails(mtime)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON thumbnails(created_at)")
                conn.commit()

            # schedule a schema init via operator to keep ownership consistent
            self._db_operator.schedule_write(_schema_init).result()

            # ensure any registered migrations are applied through the operator
            def _apply_migrations(conn):
                try:
                    apply_migrations(conn)
                except Exception:
                    _logger.debug("apply_migrations via operator failed", exc_info=True)

            self._db_operator.schedule_write(_apply_migrations).result()

            # operator-backed migrations applied above; no direct connection migration required
            # Ensure the DB file itself is hidden on Windows now that it may have been created
            self._set_hidden_attribute()
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
        if self._thumb_db is None:
            return

        path = self._norm_path(path)

        mtime_ms = self._to_mtime_ms(mtime)

        try:
            # Keep schema coherent: meta can exist even when thumbnail is not yet generated.
            # If the file changed (mtime/size), any previous thumbnail is treated as stale.
            # Preserve thumbnail field but drop if mtime/size changed
            existing = self._thumb_db.probe(path)
            prev_mtime = existing[4] if existing else None
            prev_size = existing[5] if existing else None
            thumbnail = (existing[1] if existing else None) if prev_mtime == mtime_ms and prev_size == size else None
            self._thumb_db.upsert_meta(
                path,
                mtime_ms,
                size,
                meta={
                    "width": width,
                    "height": height,
                    "thumb_width": thumb_width,
                    "thumb_height": thumb_height,
                    "thumbnail": thumbnail,
                    "created_at": time.time(),
                },
            )
            return
        except Exception as exc:
            _logger.debug("failed to save metadata to cache: %s", exc)

    def get_meta(self, path: str, mtime: float, size: int) -> tuple[int | None, int | None] | None:  # noqa: PLR0911
        """Get cached metadata (width/height) without loading any thumbnail blob."""
        path_norm = self._norm_path(path)
        # Prefer operator probe for metadata queries
        if self._thumb_db:
            try:
                row = self._thumb_db.probe(path_norm)
                if not row and path_norm != path:
                    row = self._thumb_db.probe(path)
                if not row:
                    return None
                width, height = row[2], row[3]
                db_mtime, db_size = row[4], row[5]
                if int(db_size) != int(size) or not self._mtime_matches(db_mtime, mtime):
                    return None
                return width, height
            except Exception:
                pass
        try:
            row = self._thumb_db.probe(path_norm)
            if not row and path_norm != path:
                row = self._thumb_db.probe(path)
            if not row:
                return None
            width, height = row[2], row[3]
            db_mtime, db_size = row[4], row[5]
            if int(db_size) != int(size) or not self._mtime_matches(db_mtime, mtime):
                return None
            return width, height
        except Exception as exc:
            _logger.debug("failed to get metadata from cache: %s", exc)
            return None

    def clear_thumbnail(self, path: str) -> None:
        """Clear only the thumbnail blob for a path (preserve metadata)."""
        if self._thumb_db is None:
            return

        path = self._norm_path(path)

        try:
            existing = self._thumb_db.probe(path)
            if not existing:
                return
            mtime = existing[4] if existing else None
            size = existing[5] if existing else None
            if mtime is None or size is None:
                return
            self._thumb_db.upsert_meta(path, int(mtime), int(size), meta={"thumbnail": None})
            return
        except Exception as exc:
            _logger.debug("failed to clear thumbnail for %s: %s", path, exc)

    def delete(self, path: str) -> None:
        """Delete a cache row for a path."""
        if self._thumb_db is None:
            return

        path = self._norm_path(path)

        try:
            self._thumb_db.delete(path)
            return
        except Exception as exc:
            _logger.debug("failed to delete cache entry for %s: %s", path, exc)

    def close(self) -> None:
        """Close any internal resources (e.g., shutdown operator and DB connection)."""
        try:
            if getattr(self, "_operator_owned", False) and getattr(self, "_db_operator", None) is not None:
                with contextlib.suppress(Exception):
                    self._db_operator.shutdown(wait=True)
        except Exception:
            pass
        try:
            if getattr(self, "_thumb_db", None) is not None:
                with contextlib.suppress(Exception):
                    self._thumb_db.close()
                self._thumb_db = None
        except Exception:
            pass

    def __del__(self) -> None:
        self.close()

    def get(  # noqa: PLR0911
        self, path: str, mtime: float | int, size: int, thumb_width: int, thumb_height: int
    ) -> tuple[QPixmap, int | None, int | None] | None:
        """Get thumbnail from cache.

        Returns:
            Tuple of (pixmap, original_width, original_height) or None if not found.
        """
        path_norm = self._norm_path(path)

        # Prefer operator-backed reads
        if self._thumb_db is not None:
            try:
                row = self._thumb_db.probe(path_norm)
                if not row and path_norm != path:
                    row = self._thumb_db.probe(path)
                if not row:
                    return None
                # row: (path, thumbnail, width, height, mtime, size, thumb_width, thumb_height, created_at)
                _, thumbnail_data, orig_width, orig_height, db_mtime, db_size, _tw, _th, _created = row
            except Exception:
                return None
        # operator-backed probe already handled above

        try:
            # Verify the cache still matches the current file.
            if int(db_size) != int(size) or not self._mtime_matches(db_mtime, mtime):
                return None

            # Metadata rows may exist without a thumbnail.
            if thumbnail_data is None:
                return None

            # Do not treat thumbnail size mismatch as a cache miss.
            # The UI can scale a cached pixmap to its current cell size.

            pixmap = QPixmap()
            if not pixmap.loadFromData(thumbnail_data):
                _logger.debug("failed to load pixmap from cache: %s (corrupt blob)", path_norm)
                # Keep metadata but drop the corrupt thumbnail so future loads can re-decode.
                try:
                    # Re-upsert metadata with thumbnail=None to clear corrupt blob
                    try:
                        self._thumb_db.upsert_meta(
                            path_norm,
                            int(db_mtime) if db_mtime is not None else 0,
                            int(db_size) if db_size is not None else 0,
                            meta={"thumbnail": None},
                        )
                    except Exception:
                        _logger.debug("failed to clear corrupt thumbnail blob for path: %s", path_norm)
                    _logger.debug("cleared corrupt thumbnail blob for path: %s", path_norm)
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
        mtime: float | int,
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
        if self._thumb_db is None:
            return

        path = self._norm_path(path)
        mtime_ms = self._to_mtime_ms(mtime)

        try:
            # Convert pixmap to PNG bytes
            if pixmap.isNull():
                _logger.debug("thumb_db_write: stored=NULL path=%s", path)
                return

            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if not pixmap.save(buffer, "PNG"):
                _logger.debug("thumb_db_write: stored=NULL path=%s", path)
                return

            thumbnail_data = buffer.data().data()
            if not thumbnail_data:
                _logger.debug("thumb_db_write: stored=NULL path=%s", path)
                return

            # store via operator-backed upsert
            self._thumb_db.upsert_meta(
                path,
                mtime_ms,
                size,
                meta={
                    "width": width,
                    "height": height,
                    "thumb_width": thumb_width,
                    "thumb_height": thumb_height,
                    "thumbnail": bytes(thumbnail_data),
                    "created_at": time.time(),
                },
            )
            try:
                # Verify stored state
                existing = self._thumb_db.probe(path)
                is_null = existing[1] is None if existing else True
                _logger.debug(
                    "thumb_db_write: stored=%s path=%s",
                    "NULL" if is_null else "BLOB",
                    path,
                )
            except Exception:
                _logger.debug("thumb_db_write: stored=? path=%s", path)
            return
        except Exception as exc:
            _logger.debug("failed to save thumbnail to cache: %s", exc)

    def cleanup_old(self, days: int = 30) -> int:
        """Remove thumbnails older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of thumbnails removed
        """
        if self._thumb_db is None:
            return 0

        try:
            cutoff = time.time() - (days * 86400)
            if self._db_operator is not None:

                def _do(conn):
                    cur = conn.execute("DELETE FROM thumbnails WHERE created_at < ?", (cutoff,))
                    return cur.rowcount

                count = self._db_operator.schedule_write(_do).result()
            else:
                _logger.debug("thumbnail cache cleanup_old: no operator available to run cleanup; skipped")
                return 0
            _logger.debug("cleaned up %d old thumbnails", count)
            return count
        except Exception as exc:
            _logger.error("failed to cleanup old thumbnails: %s", exc)
            return 0

    def vacuum(self) -> None:
        """Optimize database by reclaiming unused space."""
        if self._thumb_db is None:
            return

        try:
            if self._db_operator is not None:

                def _do(conn):
                    conn.execute("VACUUM")

                self._db_operator.schedule_write(_do).result()
            else:
                _logger.debug("thumbnail cache vacuum: no operator available to run VACUUM; skipped")
            _logger.debug("database vacuumed")
        except Exception as exc:
            _logger.error("failed to vacuum database: %s", exc)

    def _set_hidden_attribute(self) -> None:
        """Set hidden attribute on Windows.

        This is an instance method so it can access `self.db_path` and be
        invoked during initialization. Keep failures silent but logged at
        debug level so it's useful when debugging Windows-specific behavior.
        """
        try:
            _logger.debug(
                "_set_hidden_attribute: entry: platform=%s ctypes=%s db_path=%s",
                platform.system(),
                bool(ctypes),
                getattr(self, "db_path", None),
            )

            if platform.system() != "Windows":
                _logger.debug("_set_hidden_attribute: not on Windows, skipping")
                return

            db_path_obj = getattr(self, "db_path", None)
            if not db_path_obj:
                _logger.debug("_set_hidden_attribute: no db_path set, skipping")
                return

            # Wait briefly for DB file to appear (it may be created by operator writes)
            db_path = Path(db_path_obj)
            for _ in range(5):
                if db_path.exists():
                    break
                time.sleep(0.1)

            if not db_path.exists():
                _logger.debug("_set_hidden_attribute: DB file does not exist yet: %s", db_path)
                return

            if ctypes is None:
                _logger.debug("_set_hidden_attribute: ctypes not available, skipping")
                return

            # FILE_ATTRIBUTE_HIDDEN = 0x02
            path_str = str(db_path)
            _logger.debug("_set_hidden_attribute: calling SetFileAttributesW for %s", path_str)
            result = ctypes.windll.kernel32.SetFileAttributesW(path_str, 0x02)
            if result == 0:
                # Try long-path prefix fallback for paths exceeding MAX_PATH or with special chars
                try:
                    prefixed = path_str
                    if not path_str.startswith("\\\\?\\"):
                        prefixed = "\\\\?\\" + path_str
                    _logger.debug("_set_hidden_attribute: initial call failed, trying long-path prefix: %s", prefixed)
                    result = ctypes.windll.kernel32.SetFileAttributesW(prefixed, 0x02)
                except Exception:
                    pass

            if result == 0:
                _logger.debug("SetFileAttributesW failed for %s", db_path)
            else:
                _logger.debug("set hidden attribute on %s", db_path)
        except Exception:
            _logger.debug("failed to set hidden attribute", exc_info=True)


# NOTE: `close()` and `__del__` are implemented above (earlier) and perform
# operator shutdown, connection closure, and adapter disposal. Duplicate
# functions were removed to avoid shadowing and redeclaration errors.
