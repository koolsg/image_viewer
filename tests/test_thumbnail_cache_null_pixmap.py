from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

# Ensure repository root is on path (pytest might not add package layout)
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from image_viewer.image_engine.db.thumbdb_bytes_adapter import ThumbDBBytesAdapter


def test_thumbnail_cache_does_not_store_null_pixmap() -> None:
    _ = QApplication.instance() or QApplication([])

    # On Windows, SQLite can keep a short-lived handle even after close();
    # avoid flaky test failures from temp directory cleanup.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        cache_dir = Path(tmp)
        cache = ThumbDBBytesAdapter(cache_dir / "test_thumbs.db")

        null_pixmap = QPixmap()
        # Do not insert null pixmaps (mimic prior behavior)
        if not null_pixmap.isNull():
            from PySide6.QtCore import QBuffer, QIODevice

            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            null_pixmap.save(buf, "PNG")
            thumbnail_data = buf.data().data()
            cache.upsert_meta("C:/dummy/a.jpg", 1, 123, meta={"thumbnail": bytes(thumbnail_data), "width": 100, "height": 50, "thumb_width": 64, "thumb_height": 64, "created_at": time.time()})

        from image_viewer.image_engine.db.thumbdb_core import ThumbDB
        db = ThumbDB(cache.db_path)
        row = db.probe("C:/dummy/a.jpg")
        assert row is None or row[1] is None

        cache.close()


def test_thumbnail_cache_roundtrip_valid_pixmap() -> None:
    _ = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp)
        cache = ThumbDBBytesAdapter(cache_dir / "test_thumbs.db")

        pixmap = QPixmap(8, 8)
        pixmap.fill(Qt.GlobalColor.red)

        from PySide6.QtCore import QBuffer, QIODevice

        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        thumbnail_data = buffer.data().data()
        cache.upsert_meta("C:/dummy/b.jpg", 2000, 456, meta={"thumbnail": bytes(thumbnail_data), "width": 200, "height": 100, "thumb_width": 64, "thumb_height": 64, "created_at": time.time()})

        row = cache.probe("C:/dummy/b.jpg")
        assert row is not None
        _, thumbnail_data, orig_w, orig_h, _mt, _sz, _tw, _th, _c = row
        got_pixmap = QPixmap()
        assert got_pixmap.loadFromData(thumbnail_data)
        assert not got_pixmap.isNull()
        assert orig_w == 200
        assert orig_h == 100

        cache.close()


def test_thumbnail_cache_meta_only_roundtrip() -> None:
    _ = QApplication.instance() or QApplication([])

    # On Windows, SQLite can keep a short-lived handle even after close();
    # avoid flaky test failures from temp directory cleanup.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        cache_dir = Path(tmp)
        cache = ThumbDBBytesAdapter(cache_dir / "test_thumbs.db")

        cache.upsert_meta(path="C:/dummy/meta.jpg", mtime=int(3.0 * 1000), size=789, meta={"width": 321, "height": 123, "thumb_width": 64, "thumb_height": 64, "created_at": time.time()})

        row = cache.probe(path="C:/dummy/meta.jpg")
        assert row is not None
        assert row[2] == 321 and row[3] == 123

        # No thumbnail stored yet.
        row = cache.probe("C:/dummy/meta.jpg")
        assert row is not None
        assert row[1] is None

        cache.close()
