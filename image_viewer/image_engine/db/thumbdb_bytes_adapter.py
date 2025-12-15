from __future__ import annotations

import contextlib
import platform
import time
from collections.abc import Iterable
from pathlib import Path

from image_viewer.logger import get_logger
from image_viewer.path_utils import db_key

try:
    import ctypes
except Exception:
    ctypes = None

from .db_operator import DbOperator
from .migrations import apply_migrations
from .thumbdb_core import ThumbDBOperatorAdapter

_logger = get_logger("thumbnail_db")


def _set_hidden_attribute_immediate(path: Path) -> None:
    """Attempt to set hidden attribute on `path` immediately (no sleeps).

    Intended to be called from within the DB operator task so it runs while
    the DB connection and file are being created. Logs messages with
    "(immediate)" for easier diagnostic filtering.
    """
    try:
        if platform.system() != "Windows":
            return
        if ctypes is None:
            return
        path_str = str(Path(path))
        try:
            res = ctypes.windll.kernel32.SetFileAttributesW(path_str, 0x02)
        except Exception:
            res = 0
        if res == 0:
            # Try long-path prefix fallback
            try:
                prefixed = path_str
                if not path_str.startswith("\\\\?\\"):
                    prefixed = "\\\\?\\" + path_str
                res = ctypes.windll.kernel32.SetFileAttributesW(prefixed, 0x02)
            except Exception:
                res = 0
        if res == 0:
            _logger.debug("SetFileAttributesW failed (immediate) for %s", path)
        else:
            _logger.debug("set hidden attribute (immediate) on %s", path)
    except Exception:
        _logger.debug("_set_hidden_attribute_immediate failed", exc_info=True)


def _set_hidden_attribute_on_path(path: Path) -> None:
    """Set hidden attribute on a path (Windows only).

    Best-effort fallback that checks file existence once and tries the
    attribute set without sleeping. Prefer `_set_hidden_attribute_immediate`
    to be invoked from operator tasks when possible.
    """
    with contextlib.suppress(Exception):
        plat = platform.system()
        have_ctypes = bool(ctypes)
        _logger.debug("_set_hidden_attribute_on_path: entry: platform=%s ctypes=%s path=%s", plat, have_ctypes, path)

    try:
        if platform.system() != "Windows":
            _logger.debug("_set_hidden_attribute_on_path: not on Windows, skipping")
            return

        db_path = Path(path)
        if not db_path.exists():
            _logger.debug("_set_hidden_attribute_on_path: file does not exist: %s", db_path)
            return

        if ctypes is None:
            _logger.debug("_set_hidden_attribute_on_path: ctypes missing, skipping")
            return

        path_str = str(db_path)
        _logger.debug("_set_hidden_attribute_on_path: calling SetFileAttributesW for %s", path_str)
        result = ctypes.windll.kernel32.SetFileAttributesW(path_str, 0x02)
        if result == 0:
            try:
                prefixed = path_str
                if not path_str.startswith("\\\\?\\"):
                    prefixed = "\\\\?\\" + path_str
                _logger.debug(
                    "_set_hidden_attribute_on_path: initial call failed, trying long-path prefix: %s",
                    prefixed,
                )
                result = ctypes.windll.kernel32.SetFileAttributesW(prefixed, 0x02)
            except Exception:
                pass

        if result == 0:
            _logger.debug("SetFileAttributesW failed for %s", db_path)
        else:
            _logger.debug("set hidden attribute on %s", db_path)
    except Exception:
        _logger.debug("_set_hidden_attribute_on_path failed", exc_info=True)


class ThumbDBBytesAdapter:
    """A thin bytes/meta adapter around `ThumbDBOperatorAdapter`.

    This keeps the DB-facing API free of Qt types (bytes + metadata only).
    """

    def __init__(self, db_path: Path | str, operator: DbOperator | None = None):
        self._db_path = Path(db_path)
        # Log intent: where we will initialize/create the DB
        with contextlib.suppress(Exception):
            _logger.debug("ThumbDBBytesAdapter init: db_path=%s exists=%s", self._db_path, self._db_path.exists())
        self._operator_owned = False
        # Ensure parent directory exists so SQLite can create the DB file
        with contextlib.suppress(Exception):
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        if operator is None:
            # create an operator and own it
            self._operator = DbOperator(self._db_path)
            self._operator_owned = True
        else:
            self._operator = operator
        # Compatibility alias expected by consumers: _db_operator
        self._db_operator = self._operator
        self._adapter = ThumbDBOperatorAdapter(self._operator, self._db_path)
        # Ensure schema/migrations are applied via the operator on init
        try:

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
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mtime ON thumbnails(mtime)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON thumbnails(created_at)")
                conn.commit()
                # Attempt to set the hidden attribute here synchronously while the
                # operator task is executing and the file should exist.
                try:
                    _set_hidden_attribute_immediate(self._db_path)
                except Exception:
                    _logger.debug("_set_hidden_attribute_immediate failed", exc_info=True)

            self._operator.schedule_write(_schema_init).result()
            fut = self._operator.schedule_write(lambda conn: apply_migrations(conn))
            fut.result()
            # Try to set hidden attribute on the DB file (Windows only). This
            # helps keep the DB file out of Explorer listings for image folders.
            try:
                _set_hidden_attribute_on_path(self._db_path)
            except Exception:
                _logger.debug("_set_hidden_attribute_on_path failed", exc_info=True)
        except Exception:
            _logger.debug("thumbnail_db: apply_migrations failed during init", exc_info=True)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def probe(self, path: str):
        return self._adapter.probe(db_key(path))

    def get_rows_for_paths(self, paths: Iterable[str]):
        return self._adapter.get_rows_for_paths(list(paths))

    def upsert_meta(self, path: str, mtime: int, size: int, meta: dict | None = None) -> None:
        return self._adapter.upsert_meta(db_key(path), mtime, size, meta)

    def upsert_meta_many(self, rows: list[tuple[str, int, int, dict | None]]) -> None:
        return self._adapter.upsert_meta_many(rows)

    def delete(self, path: str) -> None:
        return self._adapter.delete(db_key(path))

    def close(self) -> None:
        if getattr(self, "_operator", None) is not None and self._operator_owned:
            try:
                self._operator.shutdown()
            except Exception:
                _logger.debug("failed to shutdown operator", exc_info=True)

    def set_meta(
        self,
        path: str,
        mtime: int,
        size: int,
        orig_width: int | None = None,
        orig_height: int | None = None,
    ) -> None:
        """Compatibility helper that mirrors `ThumbnailCache.set_meta()` semantics."""
        meta = {
            "width": orig_width,
            "height": orig_height,
            "created_at": time.time(),
        }
        return self.upsert_meta(path, mtime, size, meta=meta)


__all__ = ["ThumbDBBytesAdapter"]
