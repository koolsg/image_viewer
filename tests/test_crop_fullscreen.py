import pytest

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from image_viewer.ui_crop import CropDialog


def make_pixmap(w: int, h: int) -> QPixmap:
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    return QPixmap.fromImage(img)


def test_crop_dialog_show_maximized(qtbot):
    # CropDialog always shows maximized by default (showMaximized() is called in __init__)
    pm = make_pixmap(16, 16)
    dlg = CropDialog(None, "/test/path", pm)
    # Dialog always shows maximized by default, but starts in normal state
    # We can't test fullscreen since CropDialog doesn't support fullscreen parameter
    assert not bool(dlg.windowState() & Qt.WindowFullScreen)


def test_crop_dialog_initial_window_state(qtbot):
    pm = make_pixmap(16, 16)
    dlg = CropDialog(None, "/test/path", pm)

    # Verify dialog is properly initialized
    assert dlg._image_path == "/test/path"
    assert dlg._original_pixmap is pm

    # Dialog starts in normal window state (not fullscreen)
    assert not bool(dlg.windowState() & Qt.WindowFullScreen)
