import pytest
pytest.importorskip("PySide6")

import numpy as np

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QImage

from image_viewer.ui_canvas import ImageCanvas


def test_get_current_array_roundtrip(qtbot):
    app = QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    qtbot.addWidget(canvas)

    w, h = 16, 12
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pix = QPixmap.fromImage(img)
    canvas.set_pixmap(pix)

    arr = canvas.get_current_array()
    assert isinstance(arr, np.ndarray)
    assert arr.shape == (h, w, 3)
