import pytest

from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPixmap

from image_viewer.crop.ui_crop import CropDialog


def make_pixmap(w: int, h: int) -> QPixmap:
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    return QPixmap.fromImage(img)


def test_preview_centers_pixmap(qtbot):
    pm = make_pixmap(200, 120)
    dlg = CropDialog(None, "/test/path", pm)
    qtbot.addWidget(dlg)

    # Set a selection rect to make the preview smaller/offset
    from PySide6.QtCore import QRectF

    dlg._selection.setRect(QRectF(10, 10, 80, 60))

    # Enter preview
    dlg._on_preview()
    qtbot.wait(50)

    # View center in scene coords
    view_center = dlg._view.mapToScene(dlg._view.viewport().rect().center())

    # Pixmap center in scene coords
    pix_center = dlg._pix_item.mapToScene(dlg._pix_item.boundingRect().center())

    # They should be essentially identical (allow small numeric tolerance)
    assert abs(view_center.x() - pix_center.x()) < 1.0
    assert abs(view_center.y() - pix_center.y()) < 1.0

    # Clean up
    dlg._on_cancel_preview()
