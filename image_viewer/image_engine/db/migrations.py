from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable

from ..metrics import metrics

# Migration function signature: (conn: sqlite3.Connection) -> None
MigrationFn = Callable[[sqlite3.Connection], None]


def _upgrade_to_1(conn: sqlite3.Connection) -> None:
    # Add columns if missing and set created_at for existing rows
    cols = [c[1] for c in conn.execute("PRAGMA table_info(thumbnails)").fetchall()]
    if "thumb_width" not in cols:
        conn.execute("ALTER TABLE thumbnails ADD COLUMN thumb_width INTEGER NOT NULL DEFAULT 0")
    if "thumb_height" not in cols:
        conn.execute("ALTER TABLE thumbnails ADD COLUMN thumb_height INTEGER NOT NULL DEFAULT 0")
    if "created_at" not in cols:
        conn.execute("ALTER TABLE thumbnails ADD COLUMN created_at REAL NOT NULL DEFAULT 0")
        conn.execute(
            "UPDATE thumbnails SET created_at = ? WHERE created_at IS NULL OR created_at = 0",
            (time.time(),),
        )
    conn.commit()
    conn.execute("PRAGMA user_version = 1")
    conn.commit()


def _downgrade_from_1_to_0(conn: sqlite3.Connection) -> None:
    # SQLite doesn't support dropping columns directly, so recreate the table
    cols = [c[1] for c in conn.execute("PRAGMA table_info(thumbnails)").fetchall()]
    # If there are no thumb_width/thumb_height/created_at columns, nothing to do
    if not any(c in cols for c in ("thumb_width", "thumb_height", "created_at")):
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        return

    # Copy data to a temp table without the three extra columns
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS thumbnails_tmp AS
        SELECT path, thumbnail, width, height, mtime, size
        FROM thumbnails
        """
    )
    conn.commit()
    conn.execute("DROP TABLE thumbnails")
    conn.execute(
        """
        CREATE TABLE thumbnails (
            path TEXT PRIMARY KEY,
            thumbnail BLOB,
            width INTEGER,
            height INTEGER,
            mtime INTEGER,
            size INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO thumbnails (path, thumbnail, width, height, mtime, size)
        SELECT path, thumbnail, width, height, mtime, size
        FROM thumbnails_tmp
        """
    )
    conn.execute("DROP TABLE thumbnails_tmp")
    conn.commit()
    conn.execute("PRAGMA user_version = 0")
    conn.commit()


MIGRATIONS_UPGRADE: dict[int, MigrationFn] = {1: _upgrade_to_1}
MIGRATIONS_DOWNGRADE: dict[int, MigrationFn] = {1: _downgrade_from_1_to_0}


def get_latest_version() -> int:
    return max(MIGRATIONS_UPGRADE.keys()) if MIGRATIONS_UPGRADE else 0


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply migrations to bring DB to latest user_version."""
    row = conn.execute("PRAGMA user_version").fetchone()
    current = int(row[0]) if row else 0
    latest = get_latest_version()

    if current == latest:
        return

    # Upgrade
    if current < latest:
        for v in range(current + 1, latest + 1):
            fn = MIGRATIONS_UPGRADE.get(v)
            if fn:
                with metrics.timed(f"migrations.apply_v{v}_duration"):
                    fn(conn)
                metrics.inc(f"migrations.applied_v{v}")
    # Downgrade (rare case): apply targeted downgrade logic
    elif current > latest:
        for v in range(current, latest, -1):
            fn = MIGRATIONS_DOWNGRADE.get(v)
            if fn:
                with metrics.timed(f"migrations.downgrade_v{v}_duration"):
                    fn(conn)
                metrics.inc(f"migrations.downgraded_v{v}")
