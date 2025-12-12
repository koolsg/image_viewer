from __future__ import annotations

from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

# Ensure repository root is on path (pytest might not add package layout)
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from image_viewer.image_engine.thumbnail_cache import ThumbnailCache


def test_thumbnail_cache_does_not_store_null_pixmap() -> None:
    _ = QApplication.instance() or QApplication([])

    # On Windows, SQLite can keep a short-lived handle even after close();
    # avoid flaky test failures from temp directory cleanup.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        cache_dir = Path(tmp)
        cache = ThumbnailCache(cache_dir, "test_thumbs.db")

        null_pixmap = QPixmap()
        cache.set(
            path="C:/dummy/a.jpg",
            mtime=1.0,
            size=123,
            width=100,
            height=50,
            thumb_width=64,
            thumb_height=64,
            pixmap=null_pixmap,
        )

        assert cache._conn is not None
        cursor = cache._conn.execute("SELECT COUNT(*) FROM thumbnails")
        (count,) = cursor.fetchone()
        cursor.close()
        assert count == 0

    cache.close()


def test_thumbnail_cache_roundtrip_valid_pixmap() -> None:
    _ = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp)
        cache = ThumbnailCache(cache_dir, "test_thumbs.db")

        pixmap = QPixmap(8, 8)
        pixmap.fill(Qt.GlobalColor.red)

        cache.set(
            path="C:/dummy/b.jpg",
            mtime=2.0,
            size=456,
            width=200,
            height=100,
            thumb_width=64,
            thumb_height=64,
            pixmap=pixmap,
        )

        got = cache.get(
            path="C:/dummy/b.jpg",
            mtime=2.0,
            size=456,
            thumb_width=64,
            thumb_height=64,
        )
        assert got is not None
        got_pixmap, orig_w, orig_h = got
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
        cache = ThumbnailCache(cache_dir, "test_thumbs.db")

        cache.set_meta(
            path="C:/dummy/meta.jpg",
            mtime=3.0,
            size=789,
            width=321,
            height=123,
            thumb_width=64,
            thumb_height=64,
        )

        meta = cache.get_meta(path="C:/dummy/meta.jpg", mtime=3.0, size=789)
        assert meta == (321, 123)

        # No thumbnail stored yet.
        assert (
            cache.get(path="C:/dummy/meta.jpg", mtime=3.0, size=789, thumb_width=64, thumb_height=64)
            is None
        )

        cache.close()
