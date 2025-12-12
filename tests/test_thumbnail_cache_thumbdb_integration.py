import tempfile
from pathlib import Path
import sqlite3
from PySide6.QtGui import QPixmap
from image_viewer.image_engine.thumbnail_cache import ThumbnailCache
from image_viewer.image_engine.thumb_db import ThumbDB

def test_set_and_probe_thumbdb(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache = ThumbnailCache(cache_dir, db_name="thumbs.db")
    p = tmp_path / "file1.jpg"
    p.write_text("filecontent")
    # Set metadata
    cache.set_meta(str(p), mtime=12345.0, size=100, width=200, height=100, thumb_width=128, thumb_height=128)
    db = ThumbDB(cache.db_path)
    row = db.probe(str(p))
    assert row is not None
    assert row[0] == str(p)
    assert row[4] == 12345
    # Set thumbnail
    pixmap = QPixmap(100, 50)
    cache.set(str(p), 12345.0, 100, 200, 100, 128, 128, pixmap)
    row2 = db.probe(str(p))
    assert row2 is not None
    assert row2[1] is not None

