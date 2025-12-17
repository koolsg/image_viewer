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


def test_canvas_open_crop_dialog_no_image(qtbot):
    viewer = DummyViewer()
    qtbot.addWidget(viewer)
    canvas = ImageCanvas(viewer)

    # Should simply set an informative status and not raise
    canvas.open_crop_dialog()
    assert getattr(viewer, "_status", None) == "No image to crop"
