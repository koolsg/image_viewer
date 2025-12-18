import pytest

from PySide6.QtWidgets import QWidget

from image_viewer.ui_canvas import ImageCanvas


class DummyViewer(QWidget):
    def __init__(self):
        super().__init__()
        self._status = None
        self.image_files = []
        self.current_index = -1

    def _update_status(self, s: str) -> None:
        self._status = s


def test_canvas_no_image_operations(qtbot):
    viewer = DummyViewer()
    qtbot.addWidget(viewer)
    canvas = ImageCanvas(viewer)

    # Canvas should initialize properly even without image
    assert canvas._zoom == 1.0
    assert canvas._preset_mode == "fit"
    assert canvas._pix_item.pixmap().isNull()  # No pixmap set
