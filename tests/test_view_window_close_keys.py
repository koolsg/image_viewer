import pytest
from image_viewer.main import ImageViewer
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="function")
def viewer(qtbot):
    if QApplication.instance() is None:
        QApplication([])
    v = ImageViewer()
    qtbot.addWidget(v)
    v.show()
    return v


def test_enter_closes_view_window(qtbot, viewer):
    viewer.open_view_window()
    qtbot.wait(100)
    dlg = viewer._view_window
    qwidget = dlg._qml_widget
    assert qwidget is not None

    # Give the dialog focus and send Return to it (QML root will receive via focus chain)
    dlg.setFocus()
    qtbot.wait(50)

    qtbot.keyClick(dlg, Qt.Key.Key_Return)
    qtbot.wait(200)

    assert viewer._view_window is None


