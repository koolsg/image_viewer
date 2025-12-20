"""UI tests for selection-only interactions (deterministic)."""

import logging
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRectF, Qt

from tests.helpers.selection_test_ui import SelectionTestWindow
from image_viewer.logger import get_logger


_test_logger = get_logger("ui_crop_test")


def test_selection_handle_drag_changes_rect_and_logs(qtbot):
    app = QApplication.instance() or QApplication([])

    # Ensure the test logger and base logger are permissive so debug messages are emitted
    from image_viewer.logger import get_logger as _get_logger
    _get_logger().setLevel(logging.DEBUG)
    _test_logger.setLevel(logging.DEBUG)

    # Attach a local in-memory handler to capture ui_crop_test logs
    class ListHandler(logging.Handler):
        def __init__(self):
            super().__init__(logging.DEBUG)
            self.records: list[logging.LogRecord] = []

        def emit(self, record: logging.LogRecord) -> None:  # type: ignore
            self.records.append(record)

    handler = ListHandler()
    _test_logger.addHandler(handler)

    # Build deterministic environment
    window = SelectionTestWindow(200, 150)
    qtbot.addWidget(window)
    qtbot.waitForWindowShown(window)

    # Set an initial rect (left, top, width, height)
    start_rect = QRectF(20, 20, 40, 30)
    window.selection.setRect(start_rect)

    # Drag TOP_LEFT handle (index 0) from (20,20) to (25,25)
    start = (20.0, 20.0)
    end = (25.0, 25.0)
    _test_logger.debug("Test: dragging handle 0 from %s to %s", start, end)
    window.simulate_handle_drag(0, start, end)

    # Verify the crop rect changed as expected:
    expected = (25.0, 25.0, 35.0, 25.0)
    crop_rect = window.selection.get_crop_rect()
    assert crop_rect == expected

    # Now move the interior a bit and assert moves are logged
    _test_logger.debug("Test: dragging selection interior from center by (-10,-7)")
    parent_rect = window.selection._get_parent_rect()
    center = (parent_rect.center().x(), parent_rect.center().y())
    window.simulate_selection_drag(center, (center[0] - 10.0, center[1] - 7.0))

    # Read messages from our in-memory handler
    messages = [r.getMessage() for r in handler.records]
    # Some expectations
    assert any("Handle mousePress" in m or "Handle mouseMove" in m for m in messages)
    assert any("Test: dragging handle 0" in m for m in messages)
    assert any("simulate_selection_drag" in m or "Selection mousePress" in m for m in messages)

    # ESC should close the window when pressed (simulate via qtbot)
    qtbot.keyClick(window, Qt.Key_Escape)
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=2000)

    _test_logger.removeHandler(handler)
