import pytest

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from image_viewer.ui_selection import SelectionCanvas


def make_pixmap(w: int, h: int) -> QPixmap:
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    return QPixmap.fromImage(img)


def test_resize_handle_tl_basic(qtbot):
    app = QApplication.instance() or QApplication([])
    canvas = SelectionCanvas()
    qtbot.addWidget(canvas)

    pm = make_pixmap(100, 80)
    canvas.set_pixmap(pm)
    canvas.start_selection()
    canvas.set_selection_rect((20, 20, 40, 30))

    # Move top-left handle to (10,10)
    canvas.resize_selection_from_item_point(0, 10, 10)

    rect = canvas.get_selection_in_image_coords()
    assert rect == (10, 10, 50, 40)


def test_resize_handle_with_aspect_lock(qtbot):
    app = QApplication.instance() or QApplication([])
    canvas = SelectionCanvas()
    qtbot.addWidget(canvas)

    pm = make_pixmap(120, 100)
    canvas.set_pixmap(pm)
    # Start selection with 1:1 aspect lock
    canvas.start_selection(aspect_ratio=(1, 1))
    canvas.set_selection_rect((30, 30, 40, 40))

    # Move bottom-right outwards (expected to keep 1:1)
    canvas.resize_selection_from_item_point(3, 80, 60)

    rect = canvas.get_selection_in_image_coords()
    # left/top should remain 30, new size should be square and not exceed requested bottom/right
    assert rect[0] == 30 and rect[1] == 30
    assert rect[2] == rect[3] and rect[2] > 0


def test_selection_changed_emitted_on_handle_drag(qtbot):
    app = QApplication.instance() or QApplication([])
    canvas = SelectionCanvas()
    qtbot.addWidget(canvas)

    pm = make_pixmap(60, 40)
    canvas.set_pixmap(pm)
    canvas.start_selection()
    canvas.set_selection_rect((10, 5, 20, 10))

    recorded = {}

    def on_change(r):
        recorded['r'] = r

    canvas.selection_changed.connect(on_change)
    canvas.resize_selection_from_item_point(3, 45, 30)

    assert 'r' in recorded
    assert recorded['r'] == canvas.get_selection_in_image_coords()
