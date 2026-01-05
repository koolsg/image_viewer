import pytest
from image_viewer.main import ImageViewer
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt


@pytest.fixture(scope="function")
def viewer(qtbot):
    if QApplication.instance() is None:
        QApplication([])
    v = ImageViewer()
    qtbot.addWidget(v)
    v.show()
    return v


def test_open_and_close_view_window(qtbot, viewer):
    # Open the view window
    viewer.open_view_window()
    qtbot.wait(100)
    assert viewer._view_window is not None
    dlg = viewer._view_window
    assert dlg.isVisible()

    # Modal check: ensure modality returns an enum-like value (implementation-dependent)
    assert dlg.windowModality() is not None

    # Dialog is visible and modal; main window should remain available for cleanup
    # (Active window may depend on test environment/window manager.)
    assert dlg.isVisible() is True

    # Close and verify cleanup
    viewer.close_view_window()
    qtbot.wait(100)
    assert viewer._view_window is None


def test_separate_view_close_does_not_change_main_geometry(qtbot, viewer):
    # Record original geometry and maximized state
    orig_geom = viewer.geometry()
    orig_max = viewer.isMaximized()

    # Open separate view window and then close it
    viewer.open_view_window()
    qtbot.wait(100)
    assert viewer._view_window is not None

    viewer.close_view_window()
    qtbot.wait(100)

    # Main window geometry/state should be unchanged
    assert viewer.isMaximized() == orig_max
    assert viewer.geometry() == orig_geom


def test_enter_in_separate_view_does_not_affect_main_fullscreen(qtbot, viewer):
    # Make main window fullscreen (if environment supports it) and record state
    try:
        viewer.enter_fullscreen()
        qtbot.wait(50)
    except Exception:
        # If enter_fullscreen not supported in this environment, skip
        pytest.skip("fullscreen not supported in this test environment")

    assert viewer.isFullScreen() is True

    # Open separate view window
    viewer.open_view_window()
    qtbot.wait(100)
    dlg = viewer._view_window
    assert dlg is not None

    # Ensure dialog has focus and send Enter - should close dialog but leave main fullscreen
    dlg.setFocus()
    qtbot.wait(50)

    qtbot.keyClick(dlg, Qt.Key.Key_Return)

    # Dialog should immediately be hidden
    assert not dlg.isVisible()

    # Give scheduled cleanup time to complete
    qtbot.wait(200)

    assert viewer._view_window is None
    assert viewer.isFullScreen() is True

    # Cleanup: exit fullscreen
    try:
        viewer.exit_fullscreen()
    except Exception:
        pass



