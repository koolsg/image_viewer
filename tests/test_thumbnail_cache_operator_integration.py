import time
from pathlib import Path
import sqlite3

from image_viewer.image_engine.db.thumbdb_bytes_adapter import ThumbDBBytesAdapter
from image_viewer.image_engine.thumbdb_core import ThumbDB


def test_thumbnail_cache_uses_operator(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache = ThumbDBBytesAdapter(cache_dir / "thumbs.db")

    path = str((tmp_path / "file1.jpg").as_posix())
    cache.upsert_meta(path, int(time.time() * 1000), 123, meta={
        "width": 200,
        "height": 100,
        "thumb_width": 128,
        "thumb_height": 128,
        "created_at": time.time(),
    })

    # Directly inspect DB with ThumbDB to verify that row persisted
    with ThumbDB(cache.db_path) as db:
        rows = db.get_rows_for_paths([path])
        assert len(rows) == 1
        assert rows[0][0] == path

    # Clean up
    cache.close()
