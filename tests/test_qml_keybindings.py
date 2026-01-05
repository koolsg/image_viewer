import pytest
from image_viewer.main import ImageViewer
from PySide6.QtGui import QPixmap, Qt
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="function")
def viewer(qtbot):
    if QApplication.instance() is None:
        QApplication([])
    v = ImageViewer()
    qtbot.addWidget(v)
    v.show()
    return v


def test_qml_arrow_keys_navigate(qtbot, viewer):
    # Prepare a small image list and ensure current image is cached so navigation isn't blocked
    viewer.image_files = ["C:/img1.jpg", "C:/img2.jpg", "C:/img3.jpg"]
    viewer.current_index = 0
    # Put a cached pixmap for the current image so next_image doesn't ignore input
    viewer.engine._pixmap_cache[viewer.image_files[0]] = QPixmap(1, 1)

    # Ensure QML container has focus so Keys handlers receive events
    viewer.qml_container.setFocus()
    qtbot.wait(50)

    # Press Right arrow -> should advance to index 1
    qtbot.keyClick(viewer.qml_container, Qt.Key.Key_Right)
    qtbot.wait(50)
    assert viewer.current_index == 1

    # Ensure current (now index 1) is cached so prev works
    viewer.engine._pixmap_cache[viewer.image_files[1]] = QPixmap(1, 1)

    # Press Left arrow -> should go back to index 0
    qtbot.keyClick(viewer.qml_container, Qt.Key.Key_Left)
    qtbot.wait(50)
    assert viewer.current_index == 0

    # Press End -> should go to last index
    qtbot.keyClick(viewer.qml_container, Qt.Key.Key_End)
    qtbot.wait(50)
    assert viewer.current_index == len(viewer.image_files) - 1

    # Press Home -> should go to first index
    qtbot.keyClick(viewer.qml_container, Qt.Key.Key_Home)
    qtbot.wait(50)
    assert viewer.current_index == 0


def test_qml_f11_toggles_fullscreen(qtbot, viewer):
    # Pressing F11 should toggle fullscreen state via appController
    viewer.qml_container.setFocus()
    qtbot.wait(50)

    # Ensure starting state is not fullscreen
    try:
        assert not viewer.isFullScreen()
    except AssertionError:
        # If environment starts in fullscreen, try to exit first
        viewer.exit_fullscreen()
        qtbot.wait(50)

    # Press F11 - enter fullscreen
    qtbot.keyClick(viewer.qml_container, Qt.Key.Key_F11)
    qtbot.wait(200)
    assert viewer.isFullScreen() is True

    # Press F11 again - exit fullscreen
    qtbot.keyClick(viewer.qml_container, Qt.Key.Key_F11)
    qtbot.wait(200)
    assert viewer.isFullScreen() is False
