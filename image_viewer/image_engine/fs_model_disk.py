from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QPixmap

from image_viewer.image_engine.db.thumbdb_bytes_adapter import ThumbDBBytesAdapter
from image_viewer.logger import get_logger

_logger = get_logger("fs_model_disk")


def init_thumbnail_cache_for_path(cache_dir: Path, db_name: str = "SwiftView_thumbs.db") -> ThumbDBBytesAdapter | None:
    """Create and return a ThumbnailCache instance for `cache_dir`.

    The ThumbnailCache constructor will create a DbOperator; if that fails,
    ThumbnailCache will raise. This helper returns the instance or None on error.
    """
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        tc = ThumbDBBytesAdapter(cache_dir / db_name)
        return tc
    except Exception as exc:
        _logger.debug("init_thumbnail_cache_for_path failed: %s", exc)
        return None


def load_thumbnail_from_cache(
    db_cache: ThumbDBBytesAdapter, path: str, thumb_size: tuple[int, int]
) -> tuple[QPixmap, int | None, int | None] | None:
    """Try to load thumbnail from `db_cache`. Returns (pixmap, orig_w, orig_h) or None.

    Does not update any UI state; callers are responsible for applying metadata and caches.
    """
    try:
        stat_path = Path(path)
        if not stat_path.exists():
            return None

        # Probe raw bytes via the DB adapter and convert to QPixmap
        row = db_cache.probe(path)
        if not row:
            return None
        _, thumbnail_data, orig_width, orig_height, _db_mtime, _db_size, _tw, _th, _created = row
        if thumbnail_data is None:
            return None
        pixmap = QPixmap()
        if not pixmap.loadFromData(thumbnail_data):
            return None

        # Scale cached thumbnail to current UI size
        # Use Qt.AspectRatioMode.KeepAspectRatio (1) and Qt.TransformationMode.SmoothTransformation (1)
        # Note: scaled(w, h, aspectMode, mode)
        pixmap = pixmap.scaled(
            thumb_size[0], thumb_size[1], Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        return pixmap, orig_width, orig_height
    except Exception as exc:
        _logger.debug("load_thumbnail_from_cache failed: %s", exc)
        return None


def save_thumbnail_to_cache(
    db_cache: ThumbDBBytesAdapter,
    path: str,
    thumb_size: tuple[int, int],
    pixmap: QPixmap,
    orig_size: tuple[int | None, int | None],
) -> bool:
    """Save pixmap to cache and return True if succeeded.

    Return value indicates whether we requested a write; ignores exceptions and logs.
    """
    try:
        if db_cache is None:
            return False
        file_path = Path(path)
        if not file_path.exists():
            return False
        stat = file_path.stat()
        mtime = int(stat.st_mtime_ns) // 1_000_000
        size = stat.st_size

        if pixmap.isNull():
            _logger.debug("save_thumbnail_to_cache: null pixmap for %s", path)
            return False

        # Convert pixmap to PNG bytes and upsert via DB adapter
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not pixmap.save(buffer, "PNG"):
            _logger.debug("save_thumbnail_to_cache: failed to encode pixmap for %s", path)
            return False
        thumbnail_data = buffer.data().data()
        db_cache.upsert_meta(
            path,
            mtime,
            size,
            meta={
                "width": orig_size[0],
                "height": orig_size[1],
                "thumb_width": thumb_size[0],
                "thumb_height": thumb_size[1],
                "thumbnail": bytes(thumbnail_data),
                "created_at": time.time(),
            },
        )
        return True
    except Exception as exc:
        _logger.debug("save_thumbnail_to_cache failed: %s", exc)
        return False
