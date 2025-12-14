import tempfile
import time
from pathlib import Path
import sqlite3
from PySide6.QtGui import QPixmap
from image_viewer.image_engine.db.thumbdb_bytes_adapter import ThumbDBBytesAdapter
from image_viewer.image_engine.db.thumbdb_core import ThumbDB

def test_set_and_probe_thumbdb(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache = ThumbDBBytesAdapter(cache_dir / "thumbs.db")
    p = tmp_path / "file1.jpg"
    p.write_text("filecontent")
    # Set metadata (mtime in ms)
    cache.set_meta(str(p), 12345_000, 100, orig_width=200, orig_height=100)
    db = ThumbDB(cache.db_path)
    row = db.probe(str(p))
    assert row is not None
    # DB stores normalized path strings; compare as Paths to be platform-agnostic
    assert Path(row[0]) == p
    # mtime stored in database is in milliseconds
    assert row[4] == 12345000
    # Set thumbnail
    pixmap = QPixmap(100, 50)
    # Convert pixmap to PNG bytes and upsert via DB adapter
    from PySide6.QtCore import QBuffer, QIODevice

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    thumbnail_data = buffer.data().data()
    cache.upsert_meta(str(p), 12345_000, 100, meta={
        "width": 200,
        "height": 100,
        "thumb_width": 128,
        "thumb_height": 128,
        "thumbnail": bytes(thumbnail_data),
        "created_at": time.time(),
    })
    row2 = db.probe(str(p))
    assert row2 is not None
    assert row2[1] is not None
    db.close()
    cache.close()

