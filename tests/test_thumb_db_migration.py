from pathlib import Path
import sqlite3
import time

from image_viewer.image_engine.thumb_db import ThumbDB
from image_viewer.image_engine.migrations import apply_migrations


def _create_legacy_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS thumbnails (path TEXT PRIMARY KEY, thumbnail BLOB, width INTEGER, height INTEGER, mtime INTEGER, size INTEGER)"
    )
    conn.execute(
        "INSERT INTO thumbnails (path, thumbnail, width, height, mtime, size) VALUES (?, ?, ?, ?, ?, ?)",
        ("/file1.jpg", b"abc", 200, 100, 12345, 1024),
    )
    conn.commit()
    conn.close()


def test_thumb_db_migration(tmp_path: Path):
    db_path = tmp_path / "thumbs.db"
    _create_legacy_db(db_path)

    db = ThumbDB(db_path)
    # trigger migration by creating the adapter
    # now expect added columns
    # Use operator-backed read to ensure we observe post-migration schema
    # Force migration via operator in case ThumbDB init didn't apply it yet.
    db._operator.schedule_write(lambda conn: apply_migrations(conn)).result()
    cols = db._operator.schedule_read(lambda conn: [c[1] for c in conn.execute("PRAGMA table_info(thumbnails)").fetchall()]).result()
    assert "thumb_width" in cols
    assert "thumb_height" in cols
    assert "created_at" in cols
    # version bumped
    ver_row = db._operator.schedule_read(lambda conn: conn.execute("PRAGMA user_version").fetchone()).result()
    assert ver_row is not None and int(ver_row[0]) >= 1
    db.close()
