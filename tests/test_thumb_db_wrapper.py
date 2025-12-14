from pathlib import Path
import sqlite3
from image_viewer.image_engine.db.thumbdb_core import ThumbDB


def _create_test_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS thumbnails (path TEXT PRIMARY KEY, thumbnail BLOB, width INTEGER, height INTEGER, mtime INTEGER, size INTEGER)"
    )
    conn.commit()
    conn.close()


def test_thumb_db_upsert_and_fetch(tmp_path: Path):
    db_path = tmp_path / "thumbs.db"
    _create_test_db(db_path)

    with ThumbDB(db_path) as db:
        # initially no rows
        assert db.get_rows_for_paths(["/nope.jpg"]) == []
        # upsert a meta row
        db.upsert_meta("/file1.jpg", 12345, 1024, meta={"width": 200, "height": 100, "thumbnail": b"abc"})
        rows = db.get_rows_for_paths(["/file1.jpg"])
        assert len(rows) == 1
        assert rows[0][0] == "/file1.jpg"
        assert rows[0][4] == 12345
        assert rows[0][5] == 1024

        # probe returns the same
        probe = db.probe("/file1.jpg")
        assert probe is not None
        assert probe[0] == "/file1.jpg"

        # update existing row
        db.upsert_meta("/file1.jpg", 54321, 2048)
        p2 = db.probe("/file1.jpg")
        assert p2[4] == 54321
        assert p2[5] == 2048


