
from image_viewer.crop.ui_crop import CropDialog
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPixmap


def make_pixmap(w: int, h: int) -> QPixmap:
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x445566)
    return QPixmap.fromImage(img)


def test_set_dialog_pixmap_resets_selection_and_centers(qtbot):
    pm = make_pixmap(200, 120)
    dlg = CropDialog(None, "/test/path", pm)
    qtbot.addWidget(dlg)

    # Make selection non-default and off-center
    dlg._selection.setRect(QRectF(10, 10, 80, 60))

    # New pixmap with different size
    new_pm = make_pixmap(300, 80)
    dlg._set_dialog_pixmap("/other/path", new_pm)

    # Allow deferred centering to run
    qtbot.wait(50)

    # Expected parent rect should equal computed initial parent rect
    expected = dlg._compute_initial_parent_rect(dlg._pix_item.boundingRect())
    got = dlg._selection._get_parent_rect()
    assert got is not None
    assert abs(got.x() - expected.x()) < 1.0
    assert abs(got.y() - expected.y()) < 1.0
    assert abs(got.width() - expected.width()) < 1.0
    assert abs(got.height() - expected.height()) < 1.0

    # Center check (allow small rounding differences on different platforms/test runners)
    MAX_CENTER_OFFSET = 2.0
    view_center = dlg._view.mapToScene(dlg._view.viewport().rect().center())
    pix_center = dlg._pix_item.mapToScene(dlg._pix_item.boundingRect().center())
    assert abs(view_center.x() - pix_center.x()) <= MAX_CENTER_OFFSET
    assert abs(view_center.y() - pix_center.y()) <= MAX_CENTER_OFFSET


def test_fit_or_reset_and_center_does_not_crash_if_called_directly(qtbot):
    pm = make_pixmap(120, 90)
    dlg = CropDialog(None, "/test/path", pm)
    qtbot.addWidget(dlg)

    # Call helper directly both deferred and immediate
    dlg._fit_or_reset_and_center(deferred=False)
    dlg._fit_or_reset_and_center(deferred=True)

    # No asserts beyond not crashing; allow timers to run
    qtbot.wait(50)
