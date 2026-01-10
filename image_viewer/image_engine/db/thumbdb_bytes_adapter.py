from __future__ import annotations

import contextlib
import platform
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from image_viewer.infra.logger import get_logger
from image_viewer.infra.path_utils import abs_path_str, db_key

try:
    import ctypes
except Exception:  # pragma: no cover
    ctypes = None

from .db_operator import DbOperator

# Current schema contract (no migrations; pre-release: incompatible DBs are recreated).
# IMPORTANT: keep the schema spec centralized so future schema changes require
# editing only this block.
THUMB_DB_SCHEMA_VERSION: Final[int] = 2

THUMB_TABLE: Final[str] = "thumbnails"

COL_PATH: Final[str] = "path"
COL_MTIME: Final[str] = "mtime"
COL_SIZE: Final[str] = "size"
COL_WIDTH: Final[str] = "width"
COL_HEIGHT: Final[str] = "height"
COL_THUMB_WIDTH: Final[str] = "thumb_width"
COL_THUMB_HEIGHT: Final[str] = "thumb_height"
COL_THUMBNAIL: Final[str] = "thumbnail"
COL_CREATED_AT: Final[str] = "created_at"

# Column definitions: (name, SQL declaration).
# The SQL declaration includes type + constraints (NOT NULL, PRIMARY KEY, ...).
_THUMB_COL_DEFS: Final[tuple[tuple[str, str], ...]] = (
    (COL_PATH, "TEXT PRIMARY KEY"),
    (COL_MTIME, "INTEGER NOT NULL"),
    (COL_SIZE, "INTEGER NOT NULL"),
    (COL_WIDTH, "INTEGER"),
    (COL_HEIGHT, "INTEGER"),
    (COL_THUMB_WIDTH, "INTEGER NOT NULL"),
    (COL_THUMB_HEIGHT, "INTEGER NOT NULL"),
    (COL_THUMBNAIL, "BLOB"),
    (COL_CREATED_AT, "REAL NOT NULL"),
)

_THUMB_REQUIRED_COLUMNS: Final[tuple[str, ...]] = tuple(name for (name, _decl) in _THUMB_COL_DEFS)

# Select order used across the engine (kept stable for RowType unpacking).
_THUMB_SELECT_COLS: Final[tuple[str, ...]] = (
    COL_PATH,
    COL_THUMBNAIL,
    COL_WIDTH,
    COL_HEIGHT,
    COL_MTIME,
    COL_SIZE,
    COL_THUMB_WIDTH,
    COL_THUMB_HEIGHT,
    COL_CREATED_AT,
)

_THUMB_SELECT_SQL: Final[str] = ", ".join(_THUMB_SELECT_COLS)

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

_logger = get_logger("thumbnail_db")


def _set_hidden_attribute_immediate(path: Path) -> None:
    """Attempt to set hidden attribute on `path` immediately (no sleeps).

    Intended to be called from within a DB operator task so it runs while the DB
    file is being created/opened.
    """

    if platform.system() != "Windows":
        return
    if ctypes is None:
        return

    try:
        path_str = abs_path_str(path)
        res = ctypes.windll.kernel32.SetFileAttributesW(path_str, 0x02)
        if res == 0:
            # Try long-path prefix fallback
            prefixed = path_str
            if not path_str.startswith("\\\\?\\"):
                prefixed = "\\\\?\\" + path_str
            res = ctypes.windll.kernel32.SetFileAttributesW(prefixed, 0x02)
        if res == 0:
            _logger.debug("SetFileAttributesW failed (immediate) for %s", path)
        else:
            _logger.debug("set hidden attribute (immediate) on %s", path)
    except Exception:
        _logger.debug("_set_hidden_attribute_immediate failed", exc_info=True)


def _set_hidden_attribute_on_path(path: Path) -> None:
    """Set hidden attribute on a path (Windows only).

    Best-effort fallback that checks file existence once and tries the attribute
    set without sleeping. Prefer `_set_hidden_attribute_immediate` from inside an
    operator task when possible.
    """

    with contextlib.suppress(Exception):
        _logger.debug(
            "_set_hidden_attribute_on_path: entry: platform=%s ctypes=%s path=%s",
            platform.system(),
            bool(ctypes),
            path,
        )

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
            prefixed = path_str
            if not path_str.startswith("\\\\?\\"):
                prefixed = "\\\\?\\" + path_str
            _logger.debug(
                "_set_hidden_attribute_on_path: initial call failed, trying long-path prefix: %s",
                prefixed,
            )
            result = ctypes.windll.kernel32.SetFileAttributesW(prefixed, 0x02)

        if result == 0:
            _logger.debug("SetFileAttributesW failed for %s", db_path)
        else:
            _logger.debug("set hidden attribute on %s", db_path)
    except Exception:
        _logger.debug("_set_hidden_attribute_on_path failed", exc_info=True)


class ThumbDBBytesAdapter:
    """Bytes/meta adapter around a SQLite DB (no Qt types).

    Schema policy:
    - Strict schema. If the on-disk DB doesn't match our schema contract,
      we DROP+CREATE the `thumbnails` table and reset `PRAGMA user_version`.
    - No migrations/compat paths (pre-release).
    """

    def __init__(self, db_path: Path | str, operator: DbOperator | None = None):
        self._db_path = Path(db_path)
        self._operator_owned = False

        with contextlib.suppress(Exception):
            _logger.debug(
                "ThumbDBBytesAdapter init: db_path=%s exists=%s",
                self._db_path,
                self._db_path.exists(),
            )

        with contextlib.suppress(Exception):
            self._db_path.parent.mkdir(parents=True, exist_ok=True)

        if operator is None:
            self._operator = DbOperator(self._db_path)
            self._operator_owned = True
        else:
            self._operator = operator

        # Ensure schema is present and matches our strict contract.
        try:

            def _schema_matches(conn) -> bool:  # noqa: PLR0911
                version_row = conn.execute("PRAGMA user_version").fetchone()
                user_version = int(version_row[0]) if version_row else 0
                if user_version != THUMB_DB_SCHEMA_VERSION:
                    return False

                cols = conn.execute(f"PRAGMA table_info({THUMB_TABLE})").fetchall()
                if not cols:
                    return False

                # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
                actual: dict[str, tuple[str, int, int]] = {}
                for c in cols:
                    name = str(c[1])
                    ctype = str(c[2] or "").upper()
                    notnull = int(c[3])
                    pk = int(c[5])
                    actual[name] = (ctype, notnull, pk)

                # Strict: no missing or extra columns.
                if set(actual.keys()) != set(_THUMB_REQUIRED_COLUMNS):
                    return False

                # Compare type and key constraints derived from our declarations.
                for name, decl in _THUMB_COL_DEFS:
                    exp_type = str(decl.split()[0]).upper()
                    exp_notnull = 1 if "NOT NULL" in decl.upper() else 0
                    exp_pk = 1 if "PRIMARY KEY" in decl.upper() else 0
                    act_type, act_notnull, act_pk = actual.get(name, ("", 0, 0))
                    if act_type != exp_type:
                        return False
                    if act_notnull != exp_notnull:
                        return False
                    if act_pk != exp_pk:
                        return False

                return True

            def _ensure_schema(conn, *_args, **_kwargs) -> None:
                if not _schema_matches(conn):
                    _logger.debug(
                        "thumbnail_db: schema mismatch; recreating table=%s version=%d (db_path=%s)",
                        THUMB_TABLE,
                        THUMB_DB_SCHEMA_VERSION,
                        self._db_path,
                    )
                    conn.execute(f"DROP TABLE IF EXISTS {THUMB_TABLE}")
                    conn.execute("DROP INDEX IF EXISTS idx_mtime")
                    conn.execute("DROP INDEX IF EXISTS idx_created_at")

                cols_sql = ",\n".join(f"{name} {decl}" for name, decl in _THUMB_COL_DEFS)
                conn.execute(f"CREATE TABLE IF NOT EXISTS {THUMB_TABLE} (\n{cols_sql}\n)")
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_mtime ON {THUMB_TABLE}({COL_MTIME})")
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_created_at ON {THUMB_TABLE}({COL_CREATED_AT})")
                conn.execute(f"PRAGMA user_version = {THUMB_DB_SCHEMA_VERSION}")

                _set_hidden_attribute_immediate(self._db_path)

            self._operator.schedule_write(_ensure_schema).result()
            _set_hidden_attribute_on_path(self._db_path)
        except Exception:
            _logger.debug("thumbnail_db: schema init failed", exc_info=True)

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def operator(self) -> DbOperator:
        return self._operator

    def probe(self, path: str) -> RowType | None:
        key = db_key(path)

        def _do(conn, *_args, **_kwargs):
            row = conn.execute(
                f"SELECT {_THUMB_SELECT_SQL} FROM {THUMB_TABLE} WHERE {COL_PATH} = ?",
                (key,),
            ).fetchone()
            if not row:
                return None
            return (
                str(row[0]),
                None if row[1] is None else bytes(row[1]),
                None if row[2] is None else int(row[2]),
                None if row[3] is None else int(row[3]),
                None if row[4] is None else int(row[4]),
                None if row[5] is None else int(row[5]),
                None if row[6] is None else int(row[6]),
                None if row[7] is None else int(row[7]),
                None if row[8] is None else float(row[8]),
            )

        return self._operator.schedule_read(_do).result()

    def get_rows_for_paths(self, paths: Iterable[str]) -> list[RowType]:
        query_paths = [db_key(p) for p in paths]
        if not query_paths:
            return []

        # De-dupe while preserving order
        query_paths = list(dict.fromkeys(query_paths))

        def _do(conn, qpaths):
            placeholders = ",".join(["?" for _ in qpaths])
            rows = conn.execute(
                f"SELECT {_THUMB_SELECT_SQL} FROM {THUMB_TABLE} WHERE {COL_PATH} IN ({placeholders})",
                list(qpaths),
            ).fetchall()
            out: list[RowType] = []
            for r in rows:
                out.append(
                    (
                        str(r[0]),
                        None if r[1] is None else bytes(r[1]),
                        None if r[2] is None else int(r[2]),
                        None if r[3] is None else int(r[3]),
                        None if r[4] is None else int(r[4]),
                        None if r[5] is None else int(r[5]),
                        None if r[6] is None else int(r[6]),
                        None if r[7] is None else int(r[7]),
                        None if r[8] is None else float(r[8]),
                    )
                )
            return out

        return self._operator.schedule_read(_do, query_paths).result()

    def upsert_meta(self, path: str, mtime: int, size: int, meta: dict | None = None) -> None:
        key = db_key(path)
        tw = 0 if meta is None or meta.get("thumb_width") is None else int(meta.get("thumb_width"))
        th = 0 if meta is None or meta.get("thumb_height") is None else int(meta.get("thumb_height"))
        created_at = 0.0 if meta is None or meta.get("created_at") is None else float(meta.get("created_at"))

        def _do(conn, *_args, **_kwargs):
            conn.execute(
                f"""
                INSERT INTO {THUMB_TABLE} (
                    {COL_PATH}, {COL_MTIME}, {COL_SIZE}, {COL_WIDTH}, {COL_HEIGHT},
                    {COL_THUMB_WIDTH}, {COL_THUMB_HEIGHT}, {COL_THUMBNAIL}, {COL_CREATED_AT}
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT({COL_PATH}) DO UPDATE SET
                    {COL_MTIME} = excluded.{COL_MTIME},
                    {COL_SIZE} = excluded.{COL_SIZE},
                    {COL_WIDTH} = excluded.{COL_WIDTH},
                    {COL_HEIGHT} = excluded.{COL_HEIGHT},
                    {COL_THUMB_WIDTH} = excluded.{COL_THUMB_WIDTH},
                    {COL_THUMB_HEIGHT} = excluded.{COL_THUMB_HEIGHT},
                    {COL_THUMBNAIL} = excluded.{COL_THUMBNAIL},
                    {COL_CREATED_AT} = excluded.{COL_CREATED_AT}
                """,
                (
                    key,
                    int(mtime),
                    int(size),
                    None if meta is None else meta.get("width"),
                    None if meta is None else meta.get("height"),
                    int(tw),
                    int(th),
                    None if meta is None else meta.get("thumbnail"),
                    float(created_at),
                ),
            )

        self._operator.schedule_write(_do).result()

    def upsert_meta_many(self, rows: list[tuple[str, int, int, dict | None]]) -> None:
        funcs: list[tuple] = []

        def _make_fn(path: str, mtime: int, size: int, meta: dict | None):
            key = db_key(path)
            tw = 0 if meta is None or meta.get("thumb_width") is None else int(meta.get("thumb_width"))
            th = 0 if meta is None or meta.get("thumb_height") is None else int(meta.get("thumb_height"))
            created_at = 0.0 if meta is None or meta.get("created_at") is None else float(meta.get("created_at"))

            def _fn(conn):
                conn.execute(
                    f"""
                    INSERT INTO {THUMB_TABLE} (
                        {COL_PATH}, {COL_MTIME}, {COL_SIZE}, {COL_WIDTH}, {COL_HEIGHT},
                        {COL_THUMB_WIDTH}, {COL_THUMB_HEIGHT}, {COL_THUMBNAIL}, {COL_CREATED_AT}
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT({COL_PATH}) DO UPDATE SET
                        {COL_MTIME} = excluded.{COL_MTIME},
                        {COL_SIZE} = excluded.{COL_SIZE},
                        {COL_WIDTH} = excluded.{COL_WIDTH},
                        {COL_HEIGHT} = excluded.{COL_HEIGHT},
                        {COL_THUMB_WIDTH} = excluded.{COL_THUMB_WIDTH},
                        {COL_THUMB_HEIGHT} = excluded.{COL_THUMB_HEIGHT},
                        {COL_THUMBNAIL} = excluded.{COL_THUMBNAIL},
                        {COL_CREATED_AT} = excluded.{COL_CREATED_AT}
                    """,
                    (
                        key,
                        int(mtime),
                        int(size),
                        None if meta is None else meta.get("width"),
                        None if meta is None else meta.get("height"),
                        int(tw),
                        int(th),
                        None if meta is None else meta.get("thumbnail"),
                        float(created_at),
                    ),
                )

            return _fn

        for p, m, s, meta in rows:
            funcs.append((_make_fn(p, m, s, meta), (), {}))

        self._operator.schedule_write_batch(funcs).result()

    def delete(self, path: str) -> None:
        key = db_key(path)

        def _do(conn, *_args, **_kwargs):
            conn.execute(f"DELETE FROM {THUMB_TABLE} WHERE {COL_PATH} = ?", (key,))

        self._operator.schedule_write(_do).result()

    def close(self) -> None:
        if getattr(self, "_operator", None) is not None and self._operator_owned:
            try:
                self._operator.shutdown()
            except Exception:
                _logger.debug("failed to shutdown operator", exc_info=True)


__all__ = [
    "ThumbDBBytesAdapter",
    "_set_hidden_attribute_on_path",
]
