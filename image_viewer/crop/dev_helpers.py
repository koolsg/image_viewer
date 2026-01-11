"""Developer helpers for crop backend operations.

These helpers are intended for scripts and tests that need to exercise
crop functionality without spinning up the legacy widget UI (`ui_crop.py`).

Short-term: use these helpers in demo scripts and tests during migration.
Long-term: remove once all callers use QML or direct backend APIs.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PySide6.QtGui import QImage, QPixmap

from .crop import apply_crop_to_file

_logger = logging.getLogger("image_viewer.crop.dev_helpers")


def make_test_pixmap(width: int = 64, height: int = 48, color: int = 0x112233) -> QPixmap:
    img = QImage(width, height, QImage.Format.Format_RGB888)
    img.fill(color)
    return QPixmap.fromImage(img)


def apply_crop_to_tempfile(source_path: str, crop: tuple[int, int, int, int]) -> Path:
    """Apply crop via backend and write to a temp file.

    Returns path to the written file or raises on error.
    """
    out = Path(tempfile.gettempdir()) / f"crop_out_{Path(source_path).stem}.png"
    _logger.debug("apply_crop_to_tempfile: %s -> %s crop=%s", source_path, out, crop)
    apply_crop_to_file(source_path, crop, str(out))
    return out
