import pytest

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from image_viewer.ui_crop import CropDialog


def make_pixmap(w: int, h: int) -> QPixmap:
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    return QPixmap.fromImage(img)


def test_crop_dialog_preview_mode(qtbot):
    pm = make_pixmap(64, 48)
    dlg = CropDialog(None, "/test/path", pm)
    qtbot.addWidget(dlg)

    # Test initial state - not in preview mode
    assert dlg._preview_mode is False
    assert dlg.preview_btn.isEnabled() is True
    assert dlg.cancel_btn.isVisible() is False
    assert dlg._selection.isVisible() is True

    # Set a selection rectangle
    from PySide6.QtCore import QRectF
    initial_rect = QRectF(10, 5, 20, 20)
    dlg._selection.setRect(initial_rect)

    # Test entering preview mode
    dlg._on_preview()

    # Verify preview mode state
    assert dlg._preview_mode is True
    assert dlg.preview_btn.isEnabled() is False
    assert dlg.cancel_btn.isVisible() is True
    assert dlg._selection.isVisible() is False

    # Test canceling preview
    dlg._on_cancel_preview()

    # Verify back to original state
    assert dlg._preview_mode is False
    assert dlg.preview_btn.isEnabled() is True
    assert dlg.cancel_btn.isVisible() is False
    assert dlg._selection.isVisible() is True


def test_crop_dialog_zoom_modes(qtbot):
    pm = make_pixmap(64, 48)
    dlg = CropDialog(None, "/test/path", pm)
    qtbot.addWidget(dlg)

    # Test initial zoom mode is "fit"
    assert dlg._zoom_mode == "fit"
    assert dlg.fit_btn.isChecked() is True
    assert dlg.actual_btn.isChecked() is False

    # Test switching to actual mode
    dlg._apply_zoom_mode("actual")
    assert dlg._zoom_mode == "actual"
    assert dlg.fit_btn.isChecked() is False
    assert dlg.actual_btn.isChecked() is True

    # Test switching back to fit mode
    dlg._apply_zoom_mode("fit")
    assert dlg._zoom_mode == "fit"
    assert dlg.fit_btn.isChecked() is True
    assert dlg.actual_btn.isChecked() is False


def test_crop_dialog_aspect_ratio_preset(qtbot):
    pm = make_pixmap(64, 48)
    dlg = CropDialog(None, "/test/path", pm)
    qtbot.addWidget(dlg)

    # Test setting aspect ratio
    dlg._apply_preset((16, 9))
    assert dlg._selection._aspect_ratio == (16, 9)

    # Test clearing aspect ratio
    dlg._selection.set_aspect_ratio(None)
    assert dlg._selection._aspect_ratio is None


def test_crop_dialog_save_info(qtbot):
    pm = make_pixmap(64, 48)
    dlg = CropDialog(None, "/test/path", pm)
    qtbot.addWidget(dlg)

    # Test initial state - no save info
    assert dlg.get_save_info() is None

    # Simulate save by setting internal attributes
    dlg._saved_path = "/test/output.jpg"
    dlg._crop_rect = (10, 5, 20, 15)

    # Test save info is returned correctly
    save_info = dlg.get_save_info()
    assert save_info is not None
    assert save_info == ((10, 5, 20, 15), "/test/output.jpg")
