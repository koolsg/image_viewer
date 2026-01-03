import pytest

from PySide6.QtGui import QImage, QPixmap

from image_viewer.crop.ui_crop import CropDialog


class _FakeWheelEvent:
    def __init__(self, dy: int):
        from PySide6.QtCore import QPoint

        self._dy = dy
        self._accepted = False

    def angleDelta(self):
        from PySide6.QtCore import QPoint

        return QPoint(0, self._dy)

    def accept(self):
        self._accepted = True

    def ignore(self):
        self._accepted = False


def make_pixmap(w: int, h: int) -> QPixmap:
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x445566)
    return QPixmap.fromImage(img)


def test_wheel_event_updates_view_scale(qtbot):
    pm = make_pixmap(800, 600)
    dlg = CropDialog(None, "/test/path", pm)
    qtbot.addWidget(dlg)

    # Ensure we have an initial scale
    initial = dlg._view.transform().m11()

    # Simulate wheel up (zoom in)
    evt = _FakeWheelEvent(120)
    dlg.eventFilter(dlg._view.viewport(), evt)
    after_in = dlg._view.transform().m11()
    assert after_in > initial

    # Simulate wheel down (zoom out)
    evt2 = _FakeWheelEvent(-120)
    dlg.eventFilter(dlg._view.viewport(), evt2)
    after_out = dlg._view.transform().m11()
    assert after_out < after_in or after_out == pytest.approx(initial)
