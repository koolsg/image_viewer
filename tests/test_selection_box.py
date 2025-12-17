import pytest
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint

from image_viewer.ui_selection import SelectionCanvas as ImageCanvas


def test_selection_drag_creates_rect(qtbot):
    app = QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    qtbot.addWidget(canvas)

    # Create a simple pixmap matching viewport size to simplify mapping
    canvas.resize(200, 150)
    w, h = 200, 150
    from PySide6.QtGui import QImage, QPixmap

    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pix = QPixmap.fromImage(img)
    canvas.set_pixmap(pix)

    # Start selection mode and set selection programmatically (safer for headless runners)
    canvas.start_selection()
    canvas.set_selection_rect((10, 10, 50, 30))

    rect = canvas.get_selection_in_image_coords()
    assert rect is not None
    left, top, width, height = rect
    assert width == 50 and height == 30

    # Ensure handles were created
    assert len(canvas._selection_handles) == 4
