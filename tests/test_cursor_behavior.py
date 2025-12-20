import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QGraphicsSceneHoverEvent

from image_viewer.ui_crop import CropDialog


def test_handle_cursor_changes_on_drag(qtbot):
    w, h = 200, 150
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pm = QPixmap.fromImage(img)

    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    qtbot.addWidget(dlg)

    # Pick the top-left handle and simulate pressing it
    handle = dlg._selection._handles[dlg._selection.TOP_LEFT]

    # Ensure cursor before press is diagonal resize
    assert handle.cursor().shape() in (Qt.SizeFDiagCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor, Qt.SizeVerCursor)

    # Simulate press, move, release on the handle via direct calls (bypassing Qt mouse event synthesis)
    press = _create_mouse_event(handle, "press")
    handle.mousePressEvent(press)

    # While dragging, cursor should be ClosedHandCursor on handle
    assert handle.cursor().shape() == Qt.ClosedHandCursor

    move = _create_mouse_event(handle, "move")
    handle.mouseMoveEvent(move)

    release = _create_mouse_event(handle, "release")
    handle.mouseReleaseEvent(release)

    # After release, cursor should be restored to default for that handle
    assert handle.cursor().shape() != Qt.ClosedHandCursor


def test_selection_interior_shows_hand_cursor(qtbot):
    w, h = 200, 150
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pm = QPixmap.fromImage(img)

    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    qtbot.addWidget(dlg)

    view = dlg._view
    selection = dlg._selection

    # Pick a point inside the selection rect in VIEW coords
    selection.setRect(selection.rect())
    selection._refresh_view_rect_from_parent()

    parent_item = selection.parentItem()
    scene_pt = parent_item.mapToScene(selection.rect().center())
    view_pt = view.mapFromScene(scene_pt)

    # Simulate hovering over selection interior
    qtbot.mouseMove(view.viewport(), pos=view_pt)

    # Process events to ensure hoverMoveEvent is delivered
    qtbot.wait(50)

    # Expect viewport cursor to be open-hand (or OpenHandCursor applied to the view itself)
    vp_shape = view.viewport().cursor().shape()
    v_shape = view.cursor().shape()
    assert vp_shape in (Qt.OpenHandCursor, Qt.CrossCursor) or v_shape == Qt.OpenHandCursor


# Helper to synthesize minimal mouse events for handle calls
class _DummyEvent:
    def __init__(self, scene_pos=None):
        self._scene_pos = scene_pos or None
        self._accepted = False

    def scenePos(self):
        return self._scene_pos

    def accept(self):
        self._accepted = True

    def ignore(self):
        self._accepted = False


def _create_mouse_event(item, kind: str):
    # Create a dummy event where scenePos is mapped from the item's center
    parent = item.parentItem()
    center = item.rect().center()
    scene = item.scene()
    if scene and scene.views():
        view = scene.views()[0]
        pt = item.mapToScene(center)
    else:
        pt = center

    ev = _DummyEvent(pt)
    return ev


def test_hover_move_logs_transition_only(caplog, qtbot):
    import logging

    w, h = 200, 150
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pm = QPixmap.fromImage(img)

    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    qtbot.addWidget(dlg)

    caplog.set_level(logging.DEBUG, logger="image_viewer.ui_crop")

    view = dlg._view
    selection = dlg._selection

    # Ensure last hit is cleared
    selection._last_hit = None

    # Move to a point outside the selection first to ensure we generate a transition on enter
    outside_point = QPoint(1, 1)
    qtbot.mouseMove(view.viewport(), pos=outside_point)
    qtbot.wait(20)

    # Clear history and reset last_hit so we can observe a fresh transition
    selection._transition_log_history.clear()
    selection._last_hit = None

    # Move to interior using an explicit hover event so we can ensure a single transition is recorded
    selection._refresh_view_rect_from_parent()
    parent_item = selection.parentItem()
    scene_pt = parent_item.mapToScene(selection.rect().center())
    view_pt = view.mapFromScene(scene_pt)

    # Create hover events with item-local coordinates to trigger hoverMoveEvent directly
    item_center = selection.mapFromScene(scene_pt)
    ev = QGraphicsSceneHoverEvent()
    ev.setPos(QPointF(item_center.x(), item_center.y()))
    selection._transition_log_history.clear()
    selection._last_hit = None
    selection.hoverMoveEvent(ev)

    # Expect one hoverMove transition recorded in the selection's internal history
    assert any("hit=MOVE" in s and "OpenHandCursor" in s for s in selection._transition_log_history)

    prev_count = sum(1 for s in selection._transition_log_history if "hit=MOVE" in s)

    # Move slightly within same interior region; should NOT log a transition
    ev2 = QGraphicsSceneHoverEvent()
    ev2.setPos(QPointF(item_center.x() + 1, item_center.y() + 1))
    selection.hoverMoveEvent(ev2)

    new_count = sum(1 for s in selection._transition_log_history if "hit=MOVE" in s)
    assert new_count == prev_count

    # Move to top-left handle region and expect a new transition log
    handle = selection._handles[selection.TOP_LEFT]
    # Compute handle center in item coords
    handle_center_item = selection.mapFromScene(parent_item.mapToScene(handle.pos() + handle.rect().center()))

    ev3 = QGraphicsSceneHoverEvent()
    ev3.setPos(QPointF(handle_center_item.x(), handle_center_item.y()))
    selection.hoverMoveEvent(ev3)

    assert any("hit=TOP_LEFT" in s and "ResizeCursor" in s for s in selection._transition_log_history)


def test_handle_mouse_move_logs_only_when_verbose(caplog, qtbot):
    import logging

    w, h = 200, 150
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pm = QPixmap.fromImage(img)

    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    qtbot.addWidget(dlg)

    caplog.set_level(logging.DEBUG, logger="image_viewer.ui_crop")

    selection = dlg._selection
    handle = selection._handles[selection.TOP_LEFT]

    # Ensure verbose flag is off and verify internal history is not appended
    selection._VERBOSE_DRAG_LOG = False
    selection._handle_move_log_history.clear()
    handle.mouseMoveEvent(_create_mouse_event(handle, "move"))
    assert not any("Handle mouseMove" in s for s in selection._handle_move_log_history)

    # Enable verbose and expect logs recorded in internal history
    selection._VERBOSE_DRAG_LOG = True
    selection._handle_move_log_history.clear()
    handle.mouseMoveEvent(_create_mouse_event(handle, "move"))
    assert any("Handle mouseMove" in s for s in selection._handle_move_log_history)
