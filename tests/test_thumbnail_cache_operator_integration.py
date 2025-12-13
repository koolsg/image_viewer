import time
from pathlib import Path
import sqlite3

from image_viewer.image_engine.thumbnail_cache import ThumbnailCache
from image_viewer.image_engine.thumb_db import ThumbDB


def test_thumbnail_cache_uses_operator(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache = ThumbnailCache(cache_dir)

    path = str((tmp_path / "file1.jpg").as_posix())
    cache.set_meta(path, time.time(), 123, 200, 100, 128, 128)

    # Directly inspect DB with ThumbDB to verify that row persisted
    with ThumbDB(cache.db_path) as db:
        rows = db.get_rows_for_paths([path])
        assert len(rows) == 1
        assert rows[0][0] == path

    # Clean up
    cache.close()
