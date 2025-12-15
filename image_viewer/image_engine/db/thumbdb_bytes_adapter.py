from __future__ import annotations

import contextlib
import time
from collections.abc import Iterable
from pathlib import Path

from image_viewer.logger import get_logger

from .db_operator import DbOperator
from .migrations import apply_migrations
from .thumbdb_core import ThumbDBOperatorAdapter

_logger = get_logger("thumbnail_db")

_MIN_WIN_DRIVE_PREFIX_LEN = 2


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

            self._operator.schedule_write(_schema_init).result()
            fut = self._operator.schedule_write(lambda conn: apply_migrations(conn))
            fut.result()
        except Exception:
            _logger.debug("thumbnail_db: apply_migrations failed during init", exc_info=True)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def probe(self, path: str):
        # Normalize to absolute path with consistent separators and drive case
        try:
            p = Path(path)
            try:
                p = p.resolve()
            except Exception:
                p = p.absolute()
            s = str(p).replace("\\", "/")
            if len(s) >= _MIN_WIN_DRIVE_PREFIX_LEN and s[1] == ":":
                s = s[0].upper() + s[1:]
        except Exception:
            s = path
        return self._adapter.probe(s)

    def get_rows_for_paths(self, paths: Iterable[str]):
        return self._adapter.get_rows_for_paths(list(paths))

    def upsert_meta(self, path: str, mtime: int, size: int, meta: dict | None = None) -> None:
        try:
            p = Path(path)
            try:
                p = p.resolve()
            except Exception:
                p = p.absolute()
            s = str(p).replace("\\", "/")
            if len(s) >= _MIN_WIN_DRIVE_PREFIX_LEN and s[1] == ":":
                s = s[0].upper() + s[1:]
        except Exception:
            s = path
        return self._adapter.upsert_meta(s, mtime, size, meta)

    def upsert_meta_many(self, rows: list[tuple[str, int, int, dict | None]]) -> None:
        return self._adapter.upsert_meta_many(rows)

    def delete(self, path: str) -> None:
        try:
            p = Path(path)
            try:
                p = p.resolve()
            except Exception:
                p = p.absolute()
            s = str(p).replace("\\", "/")
            if len(s) >= _MIN_WIN_DRIVE_PREFIX_LEN and s[1] == ":":
                s = s[0].upper() + s[1:]
        except Exception:
            s = path
        return self._adapter.delete(s)

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
