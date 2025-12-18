import pytest

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from image_viewer.ui_crop import SelectionRectItem, QGraphicsPixmapItem


def make_pixmap(w: int, h: int) -> QPixmap:
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    return QPixmap.fromImage(img)


def test_selection_rect_item_basic(qtbot):
    app = QApplication.instance() or QApplication([])

    # Create a pixmap item to parent the selection
    pm = make_pixmap(100, 80)
    pix_item = QGraphicsPixmapItem(pm)

    # Create selection rect
    selection = SelectionRectItem(pix_item)

    # Test initial state - SelectionRectItem starts with no aspect ratio
    assert selection._aspect_ratio is None

    # Test setting a rectangle
    from PySide6.QtCore import QRectF
    rect = QRectF(20, 20, 40, 30)
    selection.setRect(rect)

    # Test getting crop rect
    crop_rect = selection.get_crop_rect()
    assert crop_rect == (20, 20, 40, 30)


def test_selection_rect_item_aspect_ratio(qtbot):
    app = QApplication.instance() or QApplication([])

    # Create a pixmap item to parent the selection
    pm = make_pixmap(120, 100)
    pix_item = QGraphicsPixmapItem(pm)

    # Create selection rect
    selection = SelectionRectItem(pix_item)

    # Test setting aspect ratio
    selection.set_aspect_ratio((1, 1))

    # Test setting rectangle with aspect ratio constraint
    from PySide6.QtCore import QRectF
    rect = QRectF(30, 30, 40, 40)
    selection.setRect(rect)

    # Verify the rect was adjusted to maintain aspect ratio
    crop_rect = selection.get_crop_rect()
    assert crop_rect[0] == 30 and crop_rect[1] == 30
    assert crop_rect[2] == crop_rect[3] and crop_rect[2] > 0
