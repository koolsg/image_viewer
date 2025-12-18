import pytest
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint

from image_viewer.ui_crop import SelectionRectItem, QGraphicsPixmapItem


def test_selection_rect_item_handles(qtbot):
    app = QApplication.instance() or QApplication([])

    # Create a pixmap item to parent the selection
    w, h = 200, 150
    from PySide6.QtGui import QImage, QPixmap
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pix = QPixmap.fromImage(img)
    pix_item = QGraphicsPixmapItem(pix)

    # Create selection rect
    selection = SelectionRectItem(pix_item)

    # Test setting selection rectangle
    from PySide6.QtCore import QRectF
    rect = QRectF(10, 10, 50, 30)
    selection.setRect(rect)

    # Verify the rectangle was set correctly
    crop_rect = selection.get_crop_rect()
    assert crop_rect == (10, 10, 50, 30)

    # Ensure handles were created (should be 8 handles for corners and edges)
    assert len(selection._handles) == 8
