from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

from image_viewer.image_engine.engine_core import EngineCore


def test_enginecore_png_encode_rgb888_odd_width():
    """Regression guard for thumbnail encoding.

    Some images can produce thumbnails with widths that lead to a non-4-byte-aligned
    bytesPerLine when using RGB888. Encoding should still succeed.
    """

    h = 10
    w = 257  # 257*3 = 771 bytes/line (not 4-byte aligned)
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[:, :, 0] = 255

    bytes_per_line = w * 3
    qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
    out = EngineCore._qimage_to_png_bytes(qimg)

    assert out
    assert out.startswith(b"\x89PNG\r\n\x1a\n")
