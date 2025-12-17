import pytest

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from image_viewer.ui_crop import CropDialog


def make_pixmap(w: int, h: int) -> QPixmap:
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    return QPixmap.fromImage(img)


def test_crop_dialog_fullscreen_flag_sets_window_state(qtbot):
    pm = make_pixmap(16, 16)
    dlg = CropDialog(None, "unused", initial_pixmap=pm, fullscreen=True)
    # Setting the window state should not require showing the dialog; verify flag is set
    assert bool(dlg.windowState() & Qt.WindowFullScreen)


def test_crop_dialog_default_not_fullscreen(qtbot):
    pm = make_pixmap(16, 16)
    dlg = CropDialog(None, "unused", initial_pixmap=pm)
    assert not bool(dlg.windowState() & Qt.WindowFullScreen)
