from __future__ import annotations

import contextlib
import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path

from image_viewer.logger import get_logger

from .db_operator import DbOperator
from .migrations import apply_migrations

_logger = get_logger("thumb_db")

RowType = tuple[
    str,
    bytes | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    float | None,
]


class ThumbDB:
    """Lightweight DB helper for the thumbnails DB.

    Usage:
        with ThumbDB(path) as db:
            rows = db.get_rows_for_paths(paths)
            db.upsert_meta(...)
    """

    def __init__(self, db_path: Path | str, operator: DbOperator | None = None):
        self._path = Path(db_path)
        self._lock = threading.RLock()
        self._operator_owned = False
        if operator is None:
            # create an operator and own it
            self._operator = DbOperator(self._path)
            self._operator_owned = True
        else:
            self._operator = operator
        # use the operator adapter as the implementation
        self._adapter = ThumbDBOperatorAdapter(self._operator, self._path)
        # Ensure schema/migrations are applied via the operator on init
        try:
            fut = self._operator.schedule_write(lambda conn: apply_migrations(conn))
            fut.result()
        except Exception:
            _logger.debug("thumb_db: apply_migrations failed during init", exc_info=True)

    def connect(self) -> None:
        # Operator-based adapter doesn't expose a live connection; return None for compatibility
        return None

    def get_user_version(self) -> int:
        # Delegate to operator-backed adapter
        return self._adapter.get_user_version()

    def set_user_version(self, version: int) -> None:
        return self._adapter.set_user_version(version)

    def _ensure_schema(self) -> None:
        """Ensure the thumbnails table has the new columns and set schema version.

        This will add missing columns for `thumb_width`, `thumb_height`, and `created_at`.
        Existing rows will be populated with sensible defaults.
        """
        # Schema initialization is handled via operator migrations; nothing to do here.
        return None

    def close(self) -> None:
        # If we own the operator, shut it down
        if getattr(self, "_operator", None) is not None and self._operator_owned:
            with contextlib.suppress(Exception):
                self._operator.shutdown()

    def __enter__(self) -> ThumbDB:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - trivial
        self.close()

    def probe(self, path: str) -> RowType | None:
        # Delegate to adapter which uses operator for reads/writes
        return self._adapter.probe(path)

    def get_rows_for_paths(self, paths: Sequence[str]) -> list[RowType]:
        return self._adapter.get_rows_for_paths(paths)

    def upsert_meta(self, path: str, mtime: int, size: int, meta: dict | None = None) -> None:
        return self._adapter.upsert_meta(path, mtime, size, meta)

    def delete(self, path: str) -> None:
        return self._adapter.delete(path)


class ThumbDBOperatorAdapter:
    """Adapter that implements ThumbDB-like API using DbOperator.

    This adapter keeps the same method signatures but delegates execution to
    the queued DbOperator, blocking on results for compatibility.
    """

    def __init__(self, operator: DbOperator, db_path: Path | str):
        self._operator = operator
        self._db_path = Path(db_path)

    def connect(self) -> None:
        # Operator owns the connection.
        return None

    def close(self) -> None:
        return None

    def get_user_version(self) -> int:
        def _read(conn):
            row = conn.execute("PRAGMA user_version").fetchone()
            return int(row[0]) if row else 0

        fut = self._operator.schedule_read(_read)
        return fut.result()

    def set_user_version(self, version: int) -> None:
        def _write(conn):
            conn.execute(f"PRAGMA user_version = {int(version)}")

        fut = self._operator.schedule_write(_write)
        return fut.result()

    def probe(self, path: str) -> RowType | None:
        def _do(conn):
            try:
                # try normalized path first, then raw path
                path_norm = _norm_path(path)
                cursor = conn.execute(
                    (
                        "SELECT path, thumbnail, width, height, mtime, size, "
                        "thumb_width, thumb_height, created_at FROM thumbnails WHERE path = ?"
                    ),
                    (path_norm,),
                )
                row = cursor.fetchone()
                if not row and path_norm != path:
                    cursor = conn.execute(
                        (
                            "SELECT path, thumbnail, width, height, mtime, size, "
                            "thumb_width, thumb_height, created_at FROM thumbnails WHERE path = ?"
                        ),
                        (path,),
                    )
                    row = cursor.fetchone()
                return cast_row(row)
            except sqlite3.OperationalError:
                cursor = conn.execute(
                    "SELECT path, thumbnail, width, height, mtime, size FROM thumbnails WHERE path = ?",
                    (path_norm,),
                )
                row = cursor.fetchone()
                if not row:
                    if path_norm != path:
                        cursor = conn.execute(
                            "SELECT path, thumbnail, width, height, mtime, size FROM thumbnails WHERE path = ?",
                            (path,),
                        )
                        row = cursor.fetchone()
                        if not row:
                            return None
                        return cast_row(tuple([*list(row), None, None, None]))
                    return None
                return cast_row(tuple([*list(row), None, None, None]))

        fut = self._operator.schedule_read(_do)
        return fut.result()

    def get_rows_for_paths(self, paths: Sequence[str]) -> list[RowType]:
        if not paths:
            return []

        def _do(conn, paths):
            placeholders = ",".join(["?" for _ in paths])
            query = (
                f"SELECT path, thumbnail, width, height, mtime, size, thumb_width, "
                f"thumb_height, created_at FROM thumbnails WHERE path IN ({placeholders})"
            )
            try:
                rows = conn.execute(query, list(paths)).fetchall()
                return [cast_row(r) for r in rows]
            except sqlite3.OperationalError:
                query2 = (
                    f"SELECT path, thumbnail, width, height, mtime, size FROM thumbnails WHERE path IN ({placeholders})"
                )
                rows2 = conn.execute(query2, list(paths)).fetchall()
                return [cast_row(tuple([*list(r), None, None, None])) for r in rows2]

        fut = self._operator.schedule_read(_do, paths)
        return fut.result()

    def upsert_meta(self, path: str, mtime: int, size: int, meta: dict | None = None) -> None:
        def _do(conn, path, mtime, size, meta):
            try:
                conn.execute(
                    """
            INSERT INTO thumbnails (
                path, thumbnail, width, height, mtime, size, thumb_width, thumb_height, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                thumbnail = excluded.thumbnail,
                width = excluded.width,
                height = excluded.height,
                mtime = excluded.mtime,
                size = excluded.size,
                thumb_width = excluded.thumb_width,
                thumb_height = excluded.thumb_height,
                created_at = excluded.created_at
        """,
                    (
                        path,
                        None if meta is None else meta.get("thumbnail"),
                        None if meta is None else meta.get("width"),
                        None if meta is None else meta.get("height"),
                        mtime,
                        size,
                        0 if meta is None or meta.get("thumb_width") is None else int(meta.get("thumb_width")),
                        0 if meta is None or meta.get("thumb_height") is None else int(meta.get("thumb_height")),
                        0 if meta is None or meta.get("created_at") is None else float(meta.get("created_at")),
                    ),
                )
                conn.commit()
            except sqlite3.OperationalError:
                conn.execute(
                    """
                INSERT INTO thumbnails (path, thumbnail, width, height, mtime, size)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    thumbnail = excluded.thumbnail,
                    width = excluded.width,
                    height = excluded.height,
                    mtime = excluded.mtime,
                    size = excluded.size
            """,
                    (
                        path,
                        None if meta is None else meta.get("thumbnail"),
                        None if meta is None else meta.get("width"),
                        None if meta is None else meta.get("height"),
                        mtime,
                        size,
                    ),
                )

        fut = self._operator.schedule_write(_do, path, mtime, size, meta)
        return fut.result()

    def upsert_meta_many(self, rows: list[tuple[str, int, int, dict | None]]) -> None:
        # rows: list of (path, mtime, size, meta)
        funcs = []

        def _make_upsert_fn(p, m, s, mm):
            def _fn(conn):
                try:
                    conn.execute(
                        """
            INSERT INTO thumbnails (
                path, thumbnail, width, height, mtime, size, thumb_width, thumb_height, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                thumbnail = excluded.thumbnail,
                width = excluded.width,
                height = excluded.height,
                mtime = excluded.mtime,
                size = excluded.size,
                thumb_width = excluded.thumb_width,
                thumb_height = excluded.thumb_height,
                created_at = excluded.created_at
        """,
                        (
                            p,
                            None if mm is None else mm.get("thumbnail"),
                            None if mm is None else mm.get("width"),
                            None if mm is None else mm.get("height"),
                            m,
                            s,
                            0 if mm is None or mm.get("thumb_width") is None else int(mm.get("thumb_width")),
                            0 if mm is None or mm.get("thumb_height") is None else int(mm.get("thumb_height")),
                            0 if mm is None or mm.get("created_at") is None else float(mm.get("created_at")),
                        ),
                    )
                except sqlite3.OperationalError:
                    conn.execute(
                        """
                INSERT INTO thumbnails (path, thumbnail, width, height, mtime, size)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    thumbnail = excluded.thumbnail,
                    width = excluded.width,
                    height = excluded.height,
                    mtime = excluded.mtime,
                    size = excluded.size
            """,
                        (
                            p,
                            None if mm is None else mm.get("thumbnail"),
                            None if mm is None else mm.get("width"),
                            None if mm is None else mm.get("height"),
                            m,
                            s,
                        ),
                    )

            return _fn

        for path, mtime, size, meta in rows:
            fn = _make_upsert_fn(path, mtime, size, meta)
            funcs.append((fn, (), {}))

        fut = self._operator.schedule_write_batch(funcs)
        return fut.result()

    def delete(self, path: str) -> None:
        def _do(conn, path):
            conn.execute("DELETE FROM thumbnails WHERE path = ?", (path,))
            conn.commit()

        fut = self._operator.schedule_write(_do, path)
        return fut.result()


IDX_PATH = 0
IDX_THUMBNAIL = 1
IDX_WIDTH = 2
IDX_HEIGHT = 3
IDX_MTIME = 4
IDX_SIZE = 5
IDX_TW = 6
IDX_TH = 7
IDX_CREATED_AT = 8


def cast_row(row: Sequence[object] | tuple | None) -> RowType:
    if not row:
        return ("", None, None, None, None, None, None, None, None)
    return (
        str(row[IDX_PATH]),
        None if row[IDX_THUMBNAIL] is None else bytes(row[IDX_THUMBNAIL]),
        None if row[IDX_WIDTH] is None else int(row[IDX_WIDTH]),
        None if row[IDX_HEIGHT] is None else int(row[IDX_HEIGHT]),
        None if row[IDX_MTIME] is None else int(row[IDX_MTIME]),
        None if row[IDX_SIZE] is None else int(row[IDX_SIZE]),
        None if len(row) <= IDX_TW or row[IDX_TW] is None else int(row[IDX_TW]),
        None if len(row) <= IDX_TH or row[IDX_TH] is None else int(row[IDX_TH]),
        None if len(row) <= IDX_CREATED_AT or row[IDX_CREATED_AT] is None else float(row[IDX_CREATED_AT]),
    )


DRIVE_PREFIX_LEN = 2


def _norm_path(path: str) -> str:
    p = path.replace("\\", "/")
    # Normalize drive letter casing on Windows
    if len(p) >= DRIVE_PREFIX_LEN and p[1] == ":":
        p = p[0].upper() + p[1:]
    return p
