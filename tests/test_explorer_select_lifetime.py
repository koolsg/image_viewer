import pytest
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPixmap

from image_viewer.main import ImageViewer
from image_viewer.explorer_mode_operations import _on_explorer_image_selected


def test_explorer_select_handles_ui_update_exceptions(qtbot, monkeypatch):
    app = QApplication.instance() or QApplication([])
    viewer = ImageViewer()
    qtbot.addWidget(viewer)

    # Prepare engine to report the file
    test_path = "/tmp/test.jpg"
    viewer.engine._file_list_cache = [test_path]

    # Simulate that the UI update will raise (e.g., hover menu lifetime race)
    def broken_update():
        raise RuntimeError("simulated UI race")

    monkeypatch.setattr(viewer, "_update_ui_for_mode", broken_update)

    # Call the explorer select handler; it should not raise and should set current_index
    _on_explorer_image_selected(viewer, test_path)

    assert viewer.explorer_state.view_mode is True
    assert viewer.current_index == 0
