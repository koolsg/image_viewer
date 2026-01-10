from __future__ import annotations

import contextlib

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsView

# Optional import for type guarding when forwarding real Qt hover events
try:
    from PySide6.QtWidgets import QGraphicsSceneHoverEvent
except Exception:
    QGraphicsSceneHoverEvent = None

# Optional import for cursor/overlay helpers
try:
    from .crop_selection_debug import cursor_name, overlay_message
except Exception:
    cursor_name = None
    overlay_message = None

from image_viewer.infra.logger import get_logger

_logger = get_logger("ui_crop")

_RECT_ARGS_LEN = 4


class SelectionRectItem(QGraphicsRectItem):
    # Toggle verbose drag-related debug logs (False to reduce spam)
    _VERBOSE_DRAG_LOG = False

    # Hit test return values for interior and none (distinct from handle indices 0..7)
    MOVE = -1
    NONE = -2

    # Style and handles
    HANDLE_SIZE = 10
    GRID_LINES = 4

    TOP_LEFT = 0
    TOP_CENTER = 1
    TOP_RIGHT = 2
    RIGHT_CENTER = 3
    BOTTOM_RIGHT = 4
    BOTTOM_CENTER = 5
    BOTTOM_LEFT = 6
    LEFT_CENTER = 7

    class _HandleItem(QGraphicsRectItem):
        def __init__(self, index: int, parent: SelectionRectItem):
            super().__init__(parent)
            self._index = index
            self._selection = parent
            self.setBrush(QBrush(QColor(255, 255, 255, 255)))
            self.setPen(QPen(QColor(0, 0, 0, 255), 1))
            self.setAcceptedMouseButtons(Qt.LeftButton)
            self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
            self.setAcceptHoverEvents(True)

            try:
                cursor_map = {
                    SelectionRectItem.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
                    SelectionRectItem.TOP_CENTER: Qt.CursorShape.SizeVerCursor,
                    SelectionRectItem.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
                    SelectionRectItem.RIGHT_CENTER: Qt.CursorShape.SizeHorCursor,
                    SelectionRectItem.BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
                    SelectionRectItem.BOTTOM_CENTER: Qt.CursorShape.SizeVerCursor,
                    SelectionRectItem.BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
                    SelectionRectItem.LEFT_CENTER: Qt.CursorShape.SizeHorCursor,
                }
                self._default_cursor = QCursor(cursor_map.get(index, Qt.SizeAllCursor))
                self.setCursor(self._default_cursor)
            except Exception:
                self._default_cursor = QCursor(Qt.SizeAllCursor)

        def mousePressEvent(self, event) -> None:  # type: ignore
            self._prev_view_state = None
            scene = self.scene()
            if scene is not None:
                views = scene.views()
                if views:
                    view = views[0]
                    try:
                        self._prev_view_state = view.dragMode()
                        view.setDragMode(QGraphicsView.DragMode.NoDrag)
                    except Exception:
                        self._prev_view_state = None

            self._start_scene_pos = event.scenePos()
            scene = self.scene()
            if scene and scene.views():
                view = scene.views()[0]
                if getattr(self._selection, "_view_rect", None) is not None:
                    self._start_view_rect = QRectF(self._selection._view_rect)
                else:
                    pr = QRectF(self._selection.rect())
                    tl_scene = self._selection.parentItem().mapToScene(pr.topLeft())
                    br_scene = self._selection.parentItem().mapToScene(pr.bottomRight())
                    tl_view = view.mapFromScene(tl_scene)
                    br_view = view.mapFromScene(br_scene)
                    self._start_view_rect = QRectF(
                        float(tl_view.x()),
                        float(tl_view.y()),
                        float(br_view.x() - tl_view.x()),
                        float(br_view.y() - tl_view.y()),
                    )
            else:
                self._start_view_rect = QRectF(self._selection.rect())

            if getattr(self._selection, "_parent_rect", None) is not None:
                self._start_parent_rect = QRectF(self._selection._parent_rect)
            else:
                pr = self._selection._compute_parent_rect_from_view()
                self._start_parent_rect = QRectF(pr) if pr is not None else QRectF(self._selection.rect())

            # Debug logging moved to overlay in mouseMoveEvent

            with contextlib.suppress(Exception):
                self.setCursor(Qt.ClosedHandCursor)

            event.accept()

        def mouseMoveEvent(self, event) -> None:  # type: ignore
            scene_pos = event.scenePos()
            parent_item = self._selection.parentItem()
            if parent_item is None:
                return
            p = parent_item.mapFromScene(scene_pos)
            if getattr(self._selection, "_VERBOSE_DRAG_LOG", False):
                with contextlib.suppress(Exception):
                    scene_x = float(scene_pos.x())
                    scene_y = float(scene_pos.y())
                    parent_x = float(p.x())
                    parent_y = float(p.y())

                    # Store in history for testing; console logging removed
                    msg = (
                        f"Handle mouseMove: idx={self._index} "
                        f"scene=({scene_x:.1f},{scene_y:.1f}) "
                        f"parent=({parent_x:.1f},{parent_y:.1f})"
                    )
                    with contextlib.suppress(Exception):
                        self._selection._handle_move_log_history.append(msg)

                    # Display only on overlay, not console
                    with contextlib.suppress(Exception):
                        ov = getattr(self._selection, "_debug_overlay", None)
                        debug_requested = getattr(self._selection, "_debug_overlay_requested", False)
                        msg = {"handler": f"h{self._index}", "mouse": f"{round(parent_x)},{round(parent_y)}"}
                        if ov is not None:
                            ov.show_message(msg)
                        elif not debug_requested:
                            _logger.debug("Handle mouseMove: %s", msg)
                        # else: debug was requested and overlay missing -> prefer silent (overlay-only mode)

            start_rect = getattr(self, "_start_parent_rect", QRectF(self._selection.rect()))
            self._selection.resize_handle_to(self._index, p.x(), p.y(), start_rect)
            try:
                self._selection.update()
                scene = self.scene()
                if scene is not None:
                    scene.update()
            except Exception:
                pass
            event.accept()

        def mouseReleaseEvent(self, event) -> None:  # type: ignore
            scene = self.scene()
            if scene is not None and hasattr(self, "_prev_view_state") and self._prev_view_state is not None:
                views = scene.views()
                if views:
                    view = views[0]
                    with contextlib.suppress(Exception):
                        view.setDragMode(self._prev_view_state)

            with contextlib.suppress(Exception):
                try:
                    self.setCursor(getattr(self, "_default_cursor", QCursor(Qt.ArrowCursor)))
                except Exception:
                    self.setCursor(Qt.ArrowCursor)
                with contextlib.suppress(Exception):
                    self.releaseMouse()

            with contextlib.suppress(Exception):
                scene = self.scene()
                if scene and scene.views():
                    scene.views()[0].viewport().unsetCursor()

            event.accept()

        def hoverMoveEvent(self, event) -> None:  # type: ignore
            try:
                cursor_map = {
                    SelectionRectItem.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
                    SelectionRectItem.TOP_CENTER: Qt.CursorShape.SizeVerCursor,
                    SelectionRectItem.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
                    SelectionRectItem.RIGHT_CENTER: Qt.CursorShape.SizeHorCursor,
                    SelectionRectItem.BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
                    SelectionRectItem.BOTTOM_CENTER: Qt.CursorShape.SizeVerCursor,
                    SelectionRectItem.BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
                    SelectionRectItem.LEFT_CENTER: Qt.CursorShape.SizeHorCursor,
                }
                chosen = cursor_map.get(self._index, Qt.CursorShape.SizeAllCursor)
                self.setCursor(chosen)
                scene = self.scene()
                if scene and scene.views():
                    with contextlib.suppress(Exception):
                        scene.views()[0].viewport().setCursor(chosen)
            except Exception:
                pass
            super().hoverMoveEvent(event)

        def hoverEnterEvent(self, event) -> None:  # type: ignore
            try:
                cursor_map = {
                    SelectionRectItem.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
                    SelectionRectItem.TOP_CENTER: Qt.CursorShape.SizeVerCursor,
                    SelectionRectItem.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
                    SelectionRectItem.RIGHT_CENTER: Qt.CursorShape.SizeHorCursor,
                    SelectionRectItem.BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
                    SelectionRectItem.BOTTOM_CENTER: Qt.CursorShape.SizeVerCursor,
                    SelectionRectItem.BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
                    SelectionRectItem.LEFT_CENTER: Qt.CursorShape.SizeHorCursor,
                }
                chosen = cursor_map.get(self._index, Qt.CursorShape.SizeAllCursor)
                self.setCursor(chosen)
                scene = self.scene()
                if scene and scene.views():
                    with contextlib.suppress(Exception):
                        scene.views()[0].viewport().setCursor(chosen)
            except Exception:
                pass
            super().hoverEnterEvent(event)

        def hoverLeaveEvent(self, event) -> None:  # type: ignore
            try:
                scene = self.scene()
                if scene and scene.views():
                    with contextlib.suppress(Exception):
                        scene.views()[0].viewport().unsetCursor()
            except Exception:
                pass
            super().hoverLeaveEvent(event)

    def __init__(self, parent: QGraphicsPixmapItem):
        super().__init__(parent)
        self._aspect_ratio: tuple[int, int] | None = None
        self._handles: list[SelectionRectItem._HandleItem] = []

        self._view_rect: QRectF | None = None
        self._start_view_rect: QRectF | None = None
        self._grab_offset: QPointF | None = None
        self._parent_rect: QRectF | None = None
        self._updating_parent_from_view = False

        self.setPen(QPen(QColor(255, 255, 255, 200), 2, Qt.PenStyle.SolidLine))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton)

        self._create_handles()

        self.setAcceptedMouseButtons(Qt.LeftButton)

        self._was_dragged = False
        self._last_action: str | None = None
        self._last_hit: int | None = None
        self._transition_log_history: list[str] = []
        self._handle_move_log_history: list[str] = []

    def hit_test(self, pos) -> int:
        r = self.rect()
        x = float(pos.x())
        y = float(pos.y())
        hs = float(self.HANDLE_SIZE) / 2.0

        result = self.NONE

        # Corner proximity test
        if abs(x - r.left()) <= hs and abs(y - r.top()) <= hs:
            result = self.TOP_LEFT
        elif abs(x - r.right()) <= hs and abs(y - r.top()) <= hs:
            result = self.TOP_RIGHT
        elif abs(x - r.right()) <= hs and abs(y - r.bottom()) <= hs:
            result = self.BOTTOM_RIGHT
        elif abs(x - r.left()) <= hs and abs(y - r.bottom()) <= hs:
            result = self.BOTTOM_LEFT
        else:
            edge_len_x = max(self.HANDLE_SIZE * 2, r.width() * 0.18)
            edge_len_y = max(self.HANDLE_SIZE * 2, r.height() * 0.18)
            edge_half_x = edge_len_x / 2.0
            edge_half_y = edge_len_y / 2.0

            cx = float(r.center().x())
            cy = float(r.center().y())

            if abs(y - r.top()) <= hs and abs(x - cx) <= edge_half_x:
                result = self.TOP_CENTER
            elif abs(y - r.bottom()) <= hs and abs(x - cx) <= edge_half_x:
                result = self.BOTTOM_CENTER
            elif abs(x - r.left()) <= hs and abs(y - cy) <= edge_half_y:
                result = self.LEFT_CENTER
            elif abs(x - r.right()) <= hs and abs(y - cy) <= edge_half_y:
                result = self.RIGHT_CENTER
            elif r.contains(pos):
                result = self.MOVE

        return result

    def _hit_name(self, hit: int) -> str:
        names = {
            self.TOP_LEFT: "TOP_LEFT",
            self.TOP_CENTER: "TOP_CENTER",
            self.TOP_RIGHT: "TOP_RIGHT",
            self.RIGHT_CENTER: "RIGHT_CENTER",
            self.BOTTOM_RIGHT: "BOTTOM_RIGHT",
            self.BOTTOM_CENTER: "BOTTOM_CENTER",
            self.BOTTOM_LEFT: "BOTTOM_LEFT",
            self.LEFT_CENTER: "LEFT_CENTER",
            self.MOVE: "MOVE",
            self.NONE: "NONE",
        }
        return names.get(hit, str(hit))

    def _cursor_name(self, cursor_shape) -> str:
        cmap = {
            Qt.CursorShape.SizeFDiagCursor: "SizeFDiagCursor",
            Qt.CursorShape.SizeBDiagCursor: "SizeBDiagCursor",
            Qt.CursorShape.SizeHorCursor: "SizeHorCursor",
            Qt.CursorShape.SizeVerCursor: "SizeVerCursor",
            Qt.CursorShape.OpenHandCursor: "OpenHandCursor",
            Qt.CursorShape.ClosedHandCursor: "ClosedHandCursor",
            Qt.CursorShape.CrossCursor: "CrossCursor",
            Qt.CursorShape.ArrowCursor: "ArrowCursor",
        }
        try:
            if isinstance(cursor_shape, int):
                return cmap.get(cursor_shape, str(cursor_shape))
            if hasattr(cursor_shape, "shape"):
                return cmap.get(cursor_shape.shape(), str(cursor_shape.shape()))
            return str(cursor_shape)
        except Exception:
            return str(cursor_shape)

    def _overlay_update(
        self,
        hit: int,
        cursor_shape=None,
        parent_x: float | None = None,
        parent_y: float | None = None,
        handle_index: int | None = None,
    ) -> None:
        try:
            ov = getattr(self, "_debug_overlay", None)
            if ov is None:
                return
            line1 = f"hover: hit={self._hit_name(hit)}"
            handler_name = (
                self._hit_name(handle_index)
                if handle_index is not None
                else (
                    self._hit_name(hit)
                    if hit
                    in (
                        self.TOP_LEFT,
                        self.TOP_CENTER,
                        self.TOP_RIGHT,
                        self.RIGHT_CENTER,
                        self.BOTTOM_RIGHT,
                        self.BOTTOM_CENTER,
                        self.BOTTOM_LEFT,
                        self.LEFT_CENTER,
                    )
                    else "none"
                )
            )
            c = (
                self._cursor_name(cursor_shape)
                if cursor_shape is not None
                else self._cursor_name(self.cursor().shape())
            )
            if handle_index is not None and parent_x is not None and parent_y is not None:
                line2 = f"cursor={c} handler={handler_name} (x={round(parent_x)} y={round(parent_y)})"
            else:
                line2 = f"cursor={c} handler={handler_name}"
            with contextlib.suppress(Exception):
                ov = getattr(self, "_debug_overlay", None)
                debug_requested = getattr(self, "_debug_overlay_requested", False)
                if ov is not None:
                    ov.show_message(line1 + "\n" + line2)
                elif not debug_requested:
                    _logger.debug("%s %s", line1, line2)
                # else: debug requested and overlay missing -> silent

        except Exception:
            pass

    def _log_hit_transition(self, new_hit: int, cursor_name: str) -> None:
        if getattr(self, "_transition_log_history", None) is None:
            self._transition_log_history = []
        if self._last_hit != new_hit:
            # Console logging removed; overlay shows state
            self._transition_log_history.append(f"hit={self._hit_name(new_hit)} cursor={cursor_name}")
            self._last_hit = new_hit

            try:
                ov = getattr(self, "_debug_overlay", None)
                debug_requested = getattr(self, "_debug_overlay_requested", False)
                if ov is not None:
                    ov.show_message(f"hover: hit={self._hit_name(new_hit)}")
                elif not debug_requested:
                    _logger.debug("hit=%s", self._hit_name(new_hit))
                # else: debug requested and overlay missing -> silent

            except Exception:
                pass

    def hoverEnterEvent(self, event) -> None:  # type: ignore
        try:
            pos = event.pos()
            hit = self.hit_test(pos)

            if hit in (
                self.TOP_LEFT,
                self.TOP_RIGHT,
                self.BOTTOM_LEFT,
                self.BOTTOM_RIGHT,
                self.LEFT_CENTER,
                self.RIGHT_CENTER,
                self.TOP_CENTER,
                self.BOTTOM_CENTER,
            ):
                cursor = Qt.CursorShape.SizeAllCursor
                self.setCursor(cursor)
                scene = self.scene()
                if scene and scene.views():
                    with contextlib.suppress(Exception):
                        scene.views()[0].viewport().setCursor(cursor)
                self._log_hit_transition(hit, "ResizeCursor")
            elif hit == self.MOVE:
                self.setCursor(Qt.OpenHandCursor)
                scene = self.scene()
                if scene and scene.views():
                    with contextlib.suppress(Exception):
                        scene.views()[0].viewport().setCursor(Qt.OpenHandCursor)
                self._log_hit_transition(self.MOVE, "OpenHandCursor")
            else:
                with contextlib.suppress(Exception):
                    self.unsetCursor()
                scene = self.scene()
                if scene and scene.views():
                    with contextlib.suppress(Exception):
                        scene.views()[0].viewport().unsetCursor()
                self._log_hit_transition(self.NONE, "CrossCursor")

            # Console logging removed; overlay shows state
        except Exception:
            pass  # Silent handling; overlay shows state
        super().hoverEnterEvent(event)

    def _get_parent_pos_from_event(self, event) -> tuple[float, float] | None:
        try:
            parent_item = self.parentItem()
            scene = self.scene()
            if parent_item is None or scene is None or not scene.views():
                return None
            scene_pt = scene.views()[0].mapToScene(event.pos())
            ppos = parent_item.mapFromScene(scene_pt)
            return (float(ppos.x()), float(ppos.y()))
        except Exception:
            return None

    def _handle_hover_resize(self, hit: int, event, chosen_cursor) -> None:
        self.setCursor(chosen_cursor)
        scene = self.scene()
        if scene and scene.views():
            with contextlib.suppress(Exception):
                scene.views()[0].viewport().setCursor(chosen_cursor)
        parent_pos = self._get_parent_pos_from_event(event)
        handle_index = hit if parent_pos is not None else None
        self._overlay_update(
            hit,
            cursor_shape=chosen_cursor,
            parent_x=(parent_pos[0] if parent_pos else None),
            parent_y=(parent_pos[1] if parent_pos else None),
            handle_index=handle_index,
        )
        self._log_hit_transition(hit, "ResizeCursor")

    def _handle_hover_move(self) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        scene = self.scene()
        if scene and scene.views():
            with contextlib.suppress(Exception):
                scene.views()[0].viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        self._overlay_update(self.MOVE, cursor_shape=Qt.CursorShape.OpenHandCursor)
        self._log_hit_transition(self.MOVE, "OpenHandCursor")

    def _handle_hover_none(self) -> None:
        with contextlib.suppress(Exception):
            self.unsetCursor()
        scene = self.scene()
        if scene and scene.views():
            with contextlib.suppress(Exception):
                scene.views()[0].viewport().unsetCursor()
        self._overlay_update(self.NONE, cursor_shape=Qt.CursorShape.CrossCursor)
        self._log_hit_transition(self.NONE, "CrossCursor")

    def hoverMoveEvent(self, event) -> None:  # type: ignore
        try:
            pos = event.pos()
            # Compute hit early so we can show structured overlay info
            hit = self.hit_test(pos)

            # Send hover info to the debug overlay when present (structured table)
            with contextlib.suppress(Exception):
                ov = getattr(self, "_debug_overlay", None)
                if ov is not None:
                    try:
                        cur_shape = self.cursor().shape() if hasattr(self, "cursor") else None
                        cur_name = cursor_name(cur_shape) if callable(cursor_name) else str(cur_shape)
                    except Exception:
                        cur_name = ""
                    msg = {
                        "mouse": f"{int(pos.x())},{int(pos.y())}",
                        "hit": self._hit_name(hit) if getattr(self, "_hit_name", None) else str(hit),
                        "cursor": cur_name,
                    }
                    debug_requested = getattr(self, "_debug_overlay_requested", False)
                    if ov is not None:
                        ov.show_message(msg)
                    elif not debug_requested:
                        _logger.debug("hover: %s", msg)
                    # else: debug requested and overlay missing -> silent

            cursor_map = {
                self.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
                self.BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
                self.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
                self.BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
                self.LEFT_CENTER: Qt.CursorShape.SizeHorCursor,
                self.RIGHT_CENTER: Qt.CursorShape.SizeHorCursor,
                self.TOP_CENTER: Qt.CursorShape.SizeVerCursor,
                self.BOTTOM_CENTER: Qt.CursorShape.SizeVerCursor,
            }

            if hit in cursor_map:
                self._handle_hover_resize(hit, event, cursor_map[hit])
            elif hit == self.MOVE:
                self._handle_hover_move()
            elif hit == self.NONE:
                self._handle_hover_none()
            else:
                self._overlay_update(hit, cursor_shape=None)
                self._log_hit_transition(hit, f"unknown({hit})")
        except Exception:
            pass  # Silent handling; overlay shows state
        finally:
            # Only call the Qt base implementation if we were passed a real
            # QGraphicsSceneHoverEvent; tests sometimes pass lightweight
            # dummies that implement pos(), which should not be forwarded to
            # the Qt C++ method (it will raise TypeError).
            try:
                if QGraphicsSceneHoverEvent is not None and isinstance(event, QGraphicsSceneHoverEvent):
                    super().hoverMoveEvent(event)
            except Exception:
                # Avoid any exception bubbling from type checks or imports
                pass

    def hoverLeaveEvent(self, event) -> None:  # type: ignore
        try:
            self.unsetCursor()
            scene = self.scene()
            if scene and scene.views():
                view = scene.views()[0]
                view.viewport().unsetCursor()
            # Console logging removed; overlay clears on leave
        except Exception:
            pass  # Silent handling
        super().hoverLeaveEvent(event)

    def _create_handles(self) -> None:
        self._handles = []
        for i in range(8):
            handle = SelectionRectItem._HandleItem(i, self)
            handle.setRect(0, 0, self.HANDLE_SIZE, self.HANDLE_SIZE)
            self._handles.append(handle)

    def set_parent_rect(self, parent_rect: QRectF) -> None:
        """Set the selection using parent (pixmap) coordinates.

        Converts the parent rect into view coordinates and stores as `_view_rect` and `_parent_rect`.
        Clamps the provided rect to the parent item's bounding rect to prevent the selection from
        being positioned outside the image.
        """
        scene = self.scene()
        if scene is None:
            # Editor note: scene may not be set during construction; store a parent rect and defer
            self._deferred_parent_rect = QRectF(parent_rect)
            return

        view = scene.views()[0] if scene.views() else None
        if view is None:
            self._deferred_parent_rect = QRectF(parent_rect)
            return

        # Clamp incoming parent_rect to parent's bounds
        parent_item = self.parentItem()
        if parent_item is not None:
            bounds = parent_item.boundingRect()
            w = min(parent_rect.width(), bounds.width())
            h = min(parent_rect.height(), bounds.height())
            left = max(bounds.left(), min(parent_rect.x(), bounds.right() - w))
            top = max(bounds.top(), min(parent_rect.y(), bounds.bottom() - h))
            clamped = QRectF(float(left), float(top), float(w), float(h))
        else:
            clamped = QRectF(
                float(parent_rect.x()), float(parent_rect.y()), float(parent_rect.width()), float(parent_rect.height())
            )

        # Store authoritative parent rect (clamped)
        self._parent_rect = QRectF(clamped)
        self._last_update_by = "parent"

        # Map parent rect corners to view coordinates
        tl_scene = self.parentItem().mapToScene(self._parent_rect.topLeft())
        br_scene = self.parentItem().mapToScene(self._parent_rect.bottomRight())
        tl_view = view.mapFromScene(tl_scene)
        br_view = view.mapFromScene(br_scene)
        self._view_rect = QRectF(
            float(tl_view.x()), float(tl_view.y()), float(br_view.x() - tl_view.x()), float(br_view.y() - tl_view.y())
        )

        # Apply parent rect to the QGraphicsRectItem without invoking parent->view sync
        self._updating_parent_from_view = True
        try:
            super().setRect(QRectF(self._parent_rect))
            self._update_handles()
        finally:
            self._updating_parent_from_view = False

    def _update_handles(self) -> None:
        """Update handle positions based on current rectangle.

        Handles are positioned in parent (pixmap) coordinates based on the mapped `_view_rect` -> parent.
        """
        parent_rect = self._get_parent_rect()
        if parent_rect is None:
            return

        r = parent_rect
        hs = self.HANDLE_SIZE / 2

        positions = [
            (r.left() - hs, r.top() - hs),  # Top-left
            (r.center().x() - hs, r.top() - hs),  # Top-center
            (r.right() - hs, r.top() - hs),  # Top-right
            (r.right() - hs, r.center().y() - hs),  # Right-center
            (r.right() - hs, r.bottom() - hs),  # Bottom-right
            (r.center().x() - hs, r.bottom() - hs),  # Bottom-center
            (r.left() - hs, r.bottom() - hs),  # Bottom-left
            (r.left() - hs, r.center().y() - hs),  # Left-center
        ]

        # Ensure handles match positions exactly
        desired = len(positions)
        if len(self._handles) < desired:
            for i in range(len(self._handles), desired):
                h = SelectionRectItem._HandleItem(i, self)
                h.setRect(0, 0, self.HANDLE_SIZE, self.HANDLE_SIZE)
                self._handles.append(h)
        elif len(self._handles) > desired:
            self._handles = self._handles[:desired]

        for i, (x, y) in enumerate(positions):
            handle = self._handles[i]
            with contextlib.suppress(Exception):
                handle._index = i
            handle.setRect(0, 0, self.HANDLE_SIZE, self.HANDLE_SIZE)
            handle.setPos(x, y)

    def _refresh_view_rect_from_parent(self) -> None:
        """Sync `_view_rect` with the current view transform using the parent rect."""
        scene = self.scene()
        if scene is None or not scene.views():
            return

        parent_item = self.parentItem()
        if parent_item is None:
            return

        view = scene.views()[0]
        parent_rect = getattr(self, "_parent_rect", None) or QRectF(self.rect())

        tl_scene = parent_item.mapToScene(parent_rect.topLeft())
        br_scene = parent_item.mapToScene(parent_rect.bottomRight())
        tl_view = view.mapFromScene(tl_scene)
        br_view = view.mapFromScene(br_scene)

        self._view_rect = QRectF(
            float(tl_view.x()),
            float(tl_view.y()),
            float(br_view.x() - tl_view.x()),
            float(br_view.y() - tl_view.y()),
        )

    def move_by(self, dx: float, dy: float) -> None:
        """Shift the selection rect by dx/dy in VIEW coordinates (if available), otherwise fallback to parent coords.

        This updates `_view_rect` and then maps to the parent for display.
        """
        if self._view_rect is not None:
            rect = QRectF(self._view_rect)
            rect.translate(dx, dy)
            scene = self.scene()
            view = scene.views()[0] if scene and scene.views() else None
            if view is not None:
                vb = view.viewport().rect()
                left = max(vb.left(), min(rect.left(), vb.right() - rect.width()))
                top = max(vb.top(), min(rect.top(), vb.bottom() - rect.height()))
                rect = QRectF(left, top, rect.width(), rect.height())
            self._view_rect = rect
            self._last_update_by = "view"
            self._apply_view_rect_to_parent()
            return

        r = QRectF(self.rect())
        parent_rect = self.parentItem().boundingRect()

        new_left = max(parent_rect.left(), min(r.left() + dx, parent_rect.right() - r.width()))
        new_top = max(parent_rect.top(), min(r.top() + dy, parent_rect.bottom() - r.height()))

        self.setRect(QRectF(new_left, new_top, r.width(), r.height()))

    def mousePressEvent(self, event) -> None:  # type: ignore
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        # Begin drag
        self._is_dragging = True
        self._drag_start_scene = event.scenePos()
        self._drag_start_rect = QRectF(self._get_parent_rect() or self.rect())
        self._left_click_timestamp = QTimer().remainingTime()

        # Snapshot view-space press point (and ensure _view_rect is available)
        press_view_pt = self._snapshot_press_view_point(self.scene(), self._drag_start_scene)

        if self._view_rect is not None:
            self._start_view_rect = QRectF(self._view_rect)
            if press_view_pt is not None:
                self._grab_offset = QPointF(
                    press_view_pt.x() - self._view_rect.x(), press_view_pt.y() - self._view_rect.y()
                )
        else:
            self._start_view_rect = None
            self._grab_offset = None

        self._was_dragged = False
        self._last_action = "press"
        with contextlib.suppress(Exception):
            self.setCursor(Qt.ClosedHandCursor)

        # Console logging removed; use overlay for debug info

        # Disable view panning and grab mouse, storing previous state
        self._disable_view_panning()

        event.accept()

    def _compute_drag_target_view_rect(self, view, scene_pos) -> QRectF | None:
        cur_view_pt = view.mapFromScene(scene_pos)
        # Debug logging removed; overlay handles display

        width = (
            self._start_view_rect.width()
            if getattr(self, "_start_view_rect", None) is not None
            else self._view_rect.width()
            if getattr(self, "_view_rect", None) is not None
            else 0.0
        )
        height = (
            self._start_view_rect.height()
            if getattr(self, "_start_view_rect", None) is not None
            else self._view_rect.height()
            if getattr(self, "_view_rect", None) is not None
            else 0.0
        )

        if width <= 0 or height <= 0:
            _logger.debug("_compute_drag_target_view_rect: zero-sized rect, ignoring drag")
            return None

        if getattr(self, "_start_view_rect", None) is not None and getattr(self, "_grab_offset", None) is not None:
            target_x = float(cur_view_pt.x() - self._grab_offset.x())
            target_y = float(cur_view_pt.y() - self._grab_offset.y())
        elif getattr(self, "_start_view_rect", None) is not None:
            dx = float(cur_view_pt.x() - self._start_view_rect.x())
            dy = float(cur_view_pt.y() - self._start_view_rect.y())
            target_x = float(self._start_view_rect.x() + dx)
            target_y = float(self._start_view_rect.y() + dy)
        elif getattr(self, "_view_rect", None) is not None:
            dx = float(cur_view_pt.x() - self._view_rect.x())
            dy = float(cur_view_pt.y() - self._view_rect.y())
            target_x = float(self._view_rect.x() + dx)
            target_y = float(self._view_rect.y() + dy)
        else:
            _logger.debug("_compute_drag_target_view_rect: no view rect snapshot available")
            return None

        return QRectF(target_x, target_y, width, height)

    def _get_pixmap_view_rect(self, view) -> QRectF | None:
        parent_item = self.parentItem()
        if parent_item is None or view is None:
            return None
        try:
            tl_scene = parent_item.mapToScene(parent_item.boundingRect().topLeft())
            br_scene = parent_item.mapToScene(parent_item.boundingRect().bottomRight())
            tl_view = view.mapFromScene(tl_scene)
            br_view = view.mapFromScene(br_scene)
            return QRectF(
                float(tl_view.x()),
                float(tl_view.y()),
                float(br_view.x() - tl_view.x()),
                float(br_view.y() - tl_view.y()),
            )
        except Exception:
            return None

    def _clamp_to_viewport(self, view, target: QRectF) -> QRectF:
        pv = self._get_pixmap_view_rect(view)
        if pv is not None:
            w = min(target.width(), pv.width())
            h = min(target.height(), pv.height())
            left = max(pv.left(), min(target.x(), pv.right() - w))
            top = max(pv.top(), min(target.y(), pv.bottom() - h))
            return QRectF(left, top, w, h)

        vb = view.viewport().rect()
        w = min(target.width(), vb.width())
        h = min(target.height(), vb.height())
        left = max(vb.left(), min(target.x(), vb.right() - w))
        top = max(vb.top(), min(target.y(), vb.bottom() - h))
        return QRectF(left, top, w, h)

    def _update_scene(self) -> None:
        try:
            self.update()
            scene = self.scene()
            if scene is not None:
                scene.update()
        except Exception:
            pass

    def _handle_fallback_drag(self, scene_pos) -> None:
        parent_item = self.parentItem()
        if parent_item is None:
            return
        start_parent = parent_item.mapFromScene(self._drag_start_scene)
        cur_parent = parent_item.mapFromScene(scene_pos)
        dx = float(cur_parent.x() - start_parent.x())
        dy = float(cur_parent.y() - start_parent.y())

        start_rect = QRectF(self._drag_start_rect)
        parent_rect = parent_item.boundingRect()

        new_left = max(parent_rect.left(), min(start_rect.left() + dx, parent_rect.right() - start_rect.width()))
        new_top = max(parent_rect.top(), min(start_rect.top() + dy, parent_rect.bottom() - start_rect.height()))

        self.setRect(QRectF(new_left, new_top, start_rect.width(), start_rect.height()))
        self._update_scene()

    def _snapshot_press_view_point(self, scene, scene_pos) -> QPointF | None:
        """Return the view-space press point for a scene position, initializing _view_rect if needed."""
        if scene is None:
            return None
        views = scene.views()
        if not views:
            return None
        view = views[0]
        try:
            # Ensure _view_rect reflects current transform
            self._refresh_view_rect_from_parent()
            press_view_pt = QPointF(view.mapFromScene(scene_pos))
            if self._view_rect is None:
                parent_rect = QRectF(self._get_parent_rect() or self.rect())
                tl_scene = self.parentItem().mapToScene(parent_rect.topLeft())
                br_scene = self.parentItem().mapToScene(parent_rect.bottomRight())
                tl_view = view.mapFromScene(tl_scene)
                br_view = view.mapFromScene(br_scene)
                self._view_rect = QRectF(
                    float(tl_view.x()),
                    float(tl_view.y()),
                    float(br_view.x() - tl_view.x()),
                    float(br_view.y() - tl_view.y()),
                )
            return press_view_pt
        except Exception:
            return None

    def _disable_view_panning(self) -> None:
        """Attempt to disable view panning and grab the mouse on the viewport."""
        scene = self.scene()
        if scene is None:
            return
        views = scene.views()
        if not views:
            return
        view = views[0]
        try:
            self._prev_view_state = view.dragMode()
            view.setDragMode(QGraphicsView.DragMode.NoDrag)
            with contextlib.suppress(Exception):
                view.viewport().grabMouse()
        except Exception:
            self._prev_view_state = None

    def mouseMoveEvent(self, event) -> None:  # type: ignore
        if getattr(self, "_is_dragging", False):
            scene_pos = event.scenePos()
            scene = self.scene()

            if scene and scene.views():
                view = scene.views()[0]
                target = self._compute_drag_target_view_rect(view, scene_pos)

                if target is not None:
                    target = self._clamp_to_viewport(view, target)
                    # Debug logging removed; overlay shows drag state
                    self._view_rect = target
                    self._last_update_by = "view"
                    self._apply_view_rect_to_parent()
                    self._update_scene()
                    event.accept()
                    return

            # Fallback drag; console logging removed
            self._handle_fallback_drag(scene_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore
        if getattr(self, "_is_dragging", False):
            self._is_dragging = False
            scene = self.scene()
            # Console logging removed
            if scene is not None and hasattr(self, "_prev_view_state") and self._prev_view_state is not None:
                views = scene.views()
                if views:
                    view = views[0]
                    with contextlib.suppress(Exception):
                        view.setDragMode(self._prev_view_state)
                        with contextlib.suppress(Exception):
                            view.viewport().releaseMouse()

            with contextlib.suppress(Exception):
                self.releaseMouse()

            with contextlib.suppress(Exception):
                scene = self.scene()
                if scene and scene.views():
                    scene.views()[0].viewport().setCursor(Qt.CrossCursor)

            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def resize_handle_to(self, index: int, parent_x: float, parent_y: float, start_rect: QRectF | None = None) -> None:
        """Resize selection rectangle using a handle at `index`.

        parent_x/parent_y are in the parent (pixmap) coordinate system.
        ``start_rect`` is optional and used by HandleItem to pass the rect at drag start.
        """
        r = QRectF(start_rect if start_rect is not None else self.rect())

        min_size = 8

        left = r.left()
        top = r.top()
        right = r.right()
        bottom = r.bottom()

        parent_rect = self.parentItem().boundingRect()

        def clamp_x(x: float) -> float:
            return max(parent_rect.left(), min(x, parent_rect.right()))

        def clamp_y(y: float) -> float:
            return max(parent_rect.top(), min(y, parent_rect.bottom()))

        if index == self.TOP_CENTER:
            new_top = max(parent_rect.top(), min(parent_y, bottom - min_size))
            top = new_top
        elif index == self.RIGHT_CENTER:
            new_right = min(parent_x, parent_rect.right())
            right = max(left + min_size, new_right)
        elif index == self.BOTTOM_CENTER:
            new_bottom = min(parent_y, parent_rect.bottom())
            bottom = max(top + min_size, new_bottom)
        elif index == self.LEFT_CENTER:
            new_left = max(parent_rect.left(), min(parent_x, right - min_size))
            left = new_left
        elif index == self.TOP_LEFT:
            new_left = clamp_x(min(parent_x, right - min_size))
            new_top = clamp_y(min(parent_y, bottom - min_size))
            left = new_left
            top = new_top
        elif index == self.TOP_RIGHT:
            new_right = clamp_x(max(parent_x, left + min_size))
            new_top = clamp_y(min(parent_y, bottom - min_size))
            right = new_right
            top = new_top
        elif index == self.BOTTOM_RIGHT:
            new_right = clamp_x(max(parent_x, left + min_size))
            new_bottom = clamp_y(max(parent_y, top + min_size))
            right = new_right
            bottom = new_bottom
        elif index == self.BOTTOM_LEFT:
            new_left = clamp_x(min(parent_x, right - min_size))
            new_bottom = clamp_y(max(parent_y, top + min_size))
            left = new_left
            bottom = new_bottom

        if self._aspect_ratio:
            rect = QRectF(left, top, right - left, bottom - top)
            rect = self._apply_aspect_ratio(index, rect, min_size)
            left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()

        new_left, new_top, new_right, new_bottom = self._calc_clamped_rect(left, top, right, bottom, min_size)
        # Console logging removed; overlay shows handle position if VERBOSE_DRAG_LOG
        self._apply_new_rect(new_left, new_top, new_right, new_bottom, min_size)

    def _apply_aspect_ratio(self, index: int, rect: QRectF, min_size: int) -> QRectF:
        w_ratio, h_ratio = self._aspect_ratio  # type: ignore

        left = rect.left()
        top = rect.top()
        right = rect.right()
        bottom = rect.bottom()

        cur_w = right - left
        cur_h = bottom - top
        target_w = max(min_size, cur_h * (w_ratio / h_ratio))
        target_h = max(min_size, cur_w * (h_ratio / w_ratio))

        if index in (self.TOP_CENTER, self.BOTTOM_CENTER):
            new_w = target_w
            cx = (left + right) / 2
            left = cx - new_w / 2
            right = cx + new_w / 2
        elif index in (self.LEFT_CENTER, self.RIGHT_CENTER):
            new_h = target_h
            cy = (top + bottom) / 2
            top = cy - new_h / 2
            bottom = cy + new_h / 2
        elif index == self.TOP_LEFT:
            brx, bry = right, bottom
            target_h = max(min_size, (brx - left) * (h_ratio / w_ratio))
            top = bry - target_h
            left = brx - max(min_size, target_h * (w_ratio / h_ratio))
        elif index == self.TOP_RIGHT:
            blx, bly = left, bottom
            target_h = max(min_size, (right - blx) * (h_ratio / w_ratio))
            top = bly - target_h
            right = blx + max(min_size, target_h * (w_ratio / h_ratio))
        elif index == self.BOTTOM_RIGHT:
            tlx, tly = left, top
            target_h = max(min_size, (right - tlx) * (h_ratio / w_ratio))
            bottom = tly + target_h
            right = tlx + max(min_size, target_h * (w_ratio / h_ratio))
        elif index == self.BOTTOM_LEFT:
            trx, try_ = right, top
            target_h = max(min_size, (trx - left) * (h_ratio / w_ratio))
            bottom = try_ + target_h
            left = trx - max(min_size, target_h * (w_ratio / h_ratio))

        return QRectF(left, top, max(min_size, right - left), max(min_size, bottom - top))

        # Clamp to parent bounds
        parent_rect = self.parentItem().boundingRect()
        left = max(parent_rect.left(), left)
        top = max(parent_rect.top(), top)
        right = min(parent_rect.right(), right)
        bottom = min(parent_rect.bottom(), bottom)

        # Apply new rect
        new_rect = QRectF(left, top, max(min_size, right - left), max(min_size, bottom - top))
        self.setRect(new_rect)

    def setRect(self, *args) -> None:  # type: ignore
        """Override to update handles when rectangle changes.

        Avoid re-syncing from parent->view while we're actively updating view->parent to prevent
        oscillation.
        """
        if getattr(self, "_updating_parent_from_view", False):
            super().setRect(*args)
            self._update_handles()
            return

        pr = QRectF(*args) if len(args) == _RECT_ARGS_LEN else args[0]
        self._parent_rect = QRectF(float(pr.x()), float(pr.y()), float(pr.width()), float(pr.height()))

        super().setRect(*args)
        self._update_handles()

        scene = self.scene()
        if scene and scene.views():
            view = scene.views()[0]
            tl_scene = self.parentItem().mapToScene(pr.topLeft())
            br_scene = self.parentItem().mapToScene(pr.bottomRight())
            tl_view = view.mapFromScene(tl_scene)
            br_view = view.mapFromScene(br_scene)
            self._view_rect = QRectF(
                float(tl_view.x()),
                float(tl_view.y()),
                float(br_view.x() - tl_view.x()),
                float(br_view.y() - tl_view.y()),
            )
        self._last_update_by = "parent"

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore
        super().paint(painter, option, widget)

        r = self.rect()
        painter.setPen(QPen(QColor(255, 255, 255, 160), 2, Qt.PenStyle.DotLine))

        for i in range(1, self.GRID_LINES):
            x = r.left() + (r.width() * i / self.GRID_LINES)
            painter.drawLine(QLineF(x, r.top(), x, r.bottom()))

        for i in range(1, self.GRID_LINES):
            y = r.top() + (r.height() * i / self.GRID_LINES)
            painter.drawLine(QLineF(r.left(), y, r.right(), y))

    def set_aspect_ratio(self, ratio: tuple[int, int] | None) -> None:
        self._aspect_ratio = ratio
        if ratio:
            r = self.rect()
            w, h = ratio
            current_ratio = w / h
            new_width = r.height() * current_ratio
            r.setWidth(new_width)
            self.setRect(r)

    def _calc_clamped_rect(
        self, left: float, top: float, right: float, bottom: float, min_size: int
    ) -> tuple[float, float, float, float]:
        parent_rect = self.parentItem().boundingRect()
        left = max(parent_rect.left(), left)
        top = max(parent_rect.top(), top)
        right = min(parent_rect.right(), right)
        bottom = min(parent_rect.bottom(), bottom)
        return left, top, right, bottom

    def _apply_new_rect(self, left: float, top: float, right: float, bottom: float, min_size: int) -> None:
        new_rect = QRectF(left, top, max(min_size, right - left), max(min_size, bottom - top))
        self.setRect(new_rect)

    def get_crop_rect(self) -> tuple[int, int, int, int]:
        if getattr(self, "_parent_rect", None) is not None:
            pr = self._parent_rect
            return (round(pr.x()), round(pr.y()), round(pr.width()), round(pr.height()))

        parent_rect = self._get_parent_rect()
        if parent_rect is None:
            r = self.rect()
            return (round(r.x()), round(r.y()), round(r.width()), round(r.height()))

        return (
            round(parent_rect.x()),
            round(parent_rect.y()),
            round(parent_rect.width()),
            round(parent_rect.height()),
        )

    def _compute_parent_rect_from_view(self) -> QRectF | None:
        if self._view_rect is None:
            return None
        scene = self.scene()
        if scene is None or not scene.views():
            return None
        view = scene.views()[0]
        tl_view = self._view_rect.topLeft()
        br_view = self._view_rect.bottomRight()
        tl_scene = view.mapToScene(round(tl_view.x()), round(tl_view.y()))
        br_scene = view.mapToScene(round(br_view.x()), round(br_view.y()))
        tl_parent = self.parentItem().mapFromScene(tl_scene)
        br_parent = self.parentItem().mapFromScene(br_scene)
        return QRectF(
            float(tl_parent.x()),
            float(tl_parent.y()),
            float(br_parent.x() - tl_parent.x()),
            float(br_parent.y() - tl_parent.y()),
        )

    def _get_parent_rect(self) -> QRectF | None:
        if self._view_rect is None:
            return None

        if getattr(self, "_last_update_by", None) == "parent" and getattr(self, "_parent_rect", None) is not None:
            return QRectF(self._parent_rect)

        pr = self._compute_parent_rect_from_view()
        if pr is None:
            return None
        self._parent_rect = QRectF(float(pr.x()), float(pr.y()), float(pr.width()), float(pr.height()))
        self._last_update_by = "view"
        return QRectF(self._parent_rect)

    def _apply_view_rect_to_parent(self) -> None:
        pr = self._get_parent_rect()
        if pr is None:
            # No parent rect; console logging removed
            return
        parent_rect = self.parentItem().boundingRect()
        left = max(parent_rect.left(), min(pr.left(), parent_rect.right() - pr.width()))
        top = max(parent_rect.top(), min(pr.top(), parent_rect.bottom() - pr.height()))
        # Console logging removed; overlay shows state if needed
        self.setRect(QRectF(left, top, pr.width(), pr.height()))
