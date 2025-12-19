"""Crop dialog UI components.

Interactive crop dialog with selection rectangle, zoom modes, and aspect ratio presets.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QCursor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from image_viewer.logger import get_logger
from image_viewer.settings_manager import SettingsManager

# Number of args used to construct QRectF from varargs in setRect override
_RECT_ARGS_LEN = 4

if TYPE_CHECKING:
    from PySide6.QtGui import QKeyEvent

_logger = get_logger("ui_crop")
_logger.debug("ui_crop module loaded")


class SelectionRectItem(QGraphicsRectItem):
    """Selection stored in VIEW coordinates for interaction; converted to parent coords for painting.

    We keep an internal rectangle (QRectF) in view-space named `_view_rect`. All user interactions
    (drag/resize) update `_view_rect` directly using view coordinates so interactions are smooth and
    independent of pixmap transforms. When painting or when the underlying pixmap changes we map
    `_view_rect` -> parent coordinates for display and eventual cropping via `map_view_rect_to_parent`.
    """

    """Interactive selection rectangle with resize handles and grid overlay."""

    HANDLE_SIZE = 10
    GRID_LINES = 4

    # Handle index constants
    TOP_LEFT = 0
    TOP_CENTER = 1
    TOP_RIGHT = 2
    RIGHT_CENTER = 3
    BOTTOM_RIGHT = 4
    BOTTOM_CENTER = 5
    BOTTOM_LEFT = 6
    LEFT_CENTER = 7

    class _HandleItem(QGraphicsRectItem):
        """Small handle item that delegates mouse movements back to the parent selection."""

        def __init__(self, index: int, parent: SelectionRectItem):
            super().__init__(parent)
            self._index = index
            self._selection = parent
            self.setBrush(QBrush(QColor(255, 255, 255, 255)))
            self.setPen(QPen(QColor(0, 0, 0, 255), 1))
            # Accept left-button mouse events and handle hover
            self.setAcceptedMouseButtons(Qt.LeftButton)
            # We implement our own drag; disable the built-in movable behavior
            self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
            self.setAcceptHoverEvents(True)

        def mousePressEvent(self, event) -> None:  # type: ignore
            # Disable view panning while dragging a handle so mouse moves are delivered to the handle
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

            # Record starting geometry (in view coordinates when possible)
            self._start_scene_pos = event.scenePos()
            scene = self.scene()
            if scene and scene.views():
                view = scene.views()[0]
                # Try to capture selection's view rect; if not present, derive from parent rect
                if getattr(self._selection, "_view_rect", None) is not None:
                    self._start_view_rect = QRectF(self._selection._view_rect)
                else:
                    # Map parent rect to view coords
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

            # Also snapshot the parent-space rect to use as the anchor during resize
            if getattr(self._selection, "_parent_rect", None) is not None:
                self._start_parent_rect = QRectF(self._selection._parent_rect)
            else:
                pr = self._selection._compute_parent_rect_from_view()
                self._start_parent_rect = QRectF(pr) if pr is not None else QRectF(self._selection.rect())

            # Log handle press details for debugging
            try:
                pos = event.scenePos()
                _logger.debug(
                    "Handle mousePress: idx=%s scenePos=(%.1f,%.1f) start_view_rect=%s start_parent_rect=%s",
                    self._index,
                    float(pos.x()),
                    float(pos.y()),
                    getattr(self, "_start_view_rect", None),
                    getattr(self, "_start_parent_rect", None),
                )
            except Exception:
                _logger.debug("Handle mousePress: idx=%s (failed to read positions)", self._index, exc_info=True)

            # Change cursor to indicate active drag and grab mouse to prevent view panning
            with contextlib.suppress(Exception):
                self.setCursor(Qt.ClosedHandCursor)
                # Grab mouse so the view does not start panning before item receives events
                with contextlib.suppress(Exception):
                    self.grabMouse()

            event.accept()

        def mouseMoveEvent(self, event) -> None:  # type: ignore
            # Map scene pos to the selection's parent (pixmap) coordinates
            scene_pos = event.scenePos()
            parent_item = self._selection.parentItem()
            if parent_item is None:
                return
            p = parent_item.mapFromScene(scene_pos)
            # Log handle move
            try:
                _logger.debug(
                    "Handle mouseMove: idx=%s scenePos=(%.1f,%.1f) parentPos=(%.1f,%.1f)",
                    self._index,
                    float(scene_pos.x()),
                    float(scene_pos.y()),
                    float(p.x()),
                    float(p.y()),
                )
            except Exception:
                _logger.debug("Handle mouseMove: idx=%s (failed to read positions)", self._index, exc_info=True)

            # Resize in real-time. Pass a parent-space starting rect to avoid recomputing ambiguous state.
            start_rect = getattr(self, "_start_parent_rect", QRectF(self._selection.rect()))
            self._selection.resize_handle_to(self._index, p.x(), p.y(), start_rect)
            # Ensure immediate repaint for smooth visual feedback
            try:
                self._selection.update()
                scene = self.scene()
                if scene is not None:
                    scene.update()
            except Exception:
                pass
            event.accept()

        def mouseReleaseEvent(self, event) -> None:  # type: ignore
            # Restore view drag mode if we changed it
            scene = self.scene()
            if scene is not None and hasattr(self, "_prev_view_state") and self._prev_view_state is not None:
                views = scene.views()
                if views:
                    view = views[0]
                    with contextlib.suppress(Exception):
                        view.setDragMode(self._prev_view_state)

            # Restore handle cursor and release mouse grab
            with contextlib.suppress(Exception):
                self.setCursor(Qt.CrossCursor)
                with contextlib.suppress(Exception):
                    self.releaseMouse()

            event.accept()

        def hoverMoveEvent(self, event) -> None:  # type: ignore
            # Show crosshair while hovering handles (consistent with resize cue)
            with contextlib.suppress(Exception):
                self.setCursor(Qt.CrossCursor)
            super().hoverMoveEvent(event)

    def __init__(self, parent: QGraphicsPixmapItem):
        super().__init__(parent)
        self._aspect_ratio: tuple[int, int] | None = None
        self._handles: list[SelectionRectItem._HandleItem] = []

        # NEW: store selection in view coordinates for smooth interactions
        self._view_rect: QRectF | None = None  # QRectF in VIEW coordinates
        self._start_view_rect: QRectF | None = None  # snapshot of view rect at drag start
        self._grab_offset: QPointF | None = None  # offset inside view rect where press occurred
        self._parent_rect: QRectF | None = None  # authoritative rect in parent (pixmap) coords
        self._updating_parent_from_view = False

        # Style
        self.setPen(QPen(QColor(255, 255, 255, 200), 2, Qt.PenStyle.SolidLine))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        # Do NOT set ItemIsMovable on the selection itself; it can steal events from handles.
        # We'll handle moving via explicit handlers so child handles reliably receive events.
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        # Accept hover events so we can show a move cursor when over the selection interior
        self.setAcceptHoverEvents(True)
        # Accept left-button mouse events on the selection so clicks/drag are handled
        self.setAcceptedMouseButtons(Qt.LeftButton)

        # Create handles so they're available before external callers (eg. CropDialog) call set_parent_rect
        self._create_handles()

        self.setAcceptedMouseButtons(Qt.LeftButton)

        # Track drag/click state for logging and visual feedback
        self._was_dragged = False
        # Last user action: 'press', 'drag', 'drag_end', 'click', 'resize_press', 'resize_move', 'resize_end'
        self._last_action: str | None = None

        # Track last user action for testing/inspection (press, drag, drag_end, click)
        self._last_action: str | None = None

        # Track last user action for testing/inspection (press, drag, drag_end, click)
        self._last_action: str | None = None

    def hoverEnterEvent(self, event) -> None:  # type: ignore
        try:
            self.setCursor(Qt.OpenHandCursor)
            scene = self.scene()
            if scene and scene.views():
                with contextlib.suppress(Exception):
                    view = scene.views()[0]
                    view.viewport().setCursor(Qt.OpenHandCursor)
            _logger.debug("Selection hoverEnter: OpenHandCursor")
        except Exception:
            _logger.debug("Selection hoverEnter: failed to set cursor", exc_info=True)
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event) -> None:  # type: ignore
        with contextlib.suppress(Exception):
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore
        try:
            self.unsetCursor()
            scene = self.scene()
            if scene and scene.views():
                view = scene.views()[0]
                view.viewport().setCursor(Qt.ArrowCursor)
            _logger.debug("Selection hoverLeave: cursor reset to Arrow")
        except Exception:
            _logger.debug("Selection hoverLeave: failed to reset cursor", exc_info=True)
        super().hoverLeaveEvent(event)

    def _create_handles(self) -> None:
        """Create 8 resize handles (corners + edges)."""
        # Ensure deterministic set of handles (exactly 8)
        self._handles = []
        for i in range(8):
            handle = SelectionRectItem._HandleItem(i, self)
            # Prepare a default rect for immediate hit testing; positions will be updated by _update_handles
            handle.setRect(0, 0, self.HANDLE_SIZE, self.HANDLE_SIZE)
            self._handles.append(handle)

    # New API: set selection based on parent-space rect (used by caller init)
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
            # Keep handle index in sync
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
            # Clamp to view bounds (scene view widget geometry)
            scene = self.scene()
            view = scene.views()[0] if scene and scene.views() else None
            if view is not None:
                vb = view.viewport().rect()
                # Ensure rect stays within viewport
                left = max(vb.left(), min(rect.left(), vb.right() - rect.width()))
                top = max(vb.top(), min(rect.top(), vb.bottom() - rect.height()))
                rect = QRectF(left, top, rect.width(), rect.height())
            self._view_rect = rect
            # mark that the view origin updated the rect so _get_parent_rect will compute from view
            self._last_update_by = "view"
            self._apply_view_rect_to_parent()
            return

        # Fallback: previous behavior in parent coords
        r = QRectF(self.rect())
        parent_rect = self.parentItem().boundingRect()

        new_left = max(parent_rect.left(), min(r.left() + dx, parent_rect.right() - r.width()))
        new_top = max(parent_rect.top(), min(r.top() + dy, parent_rect.bottom() - r.height()))

        self.setRect(QRectF(new_left, new_top, r.width(), r.height()))

    def mousePressEvent(self, event) -> None:  # type: ignore  # noqa: PLR0915
        # Start moving the selection if the press is inside the rect (not on a handle)
        if event.button() == Qt.LeftButton:
            # Left click inside the selection: begin drag
            self._is_dragging = True
            self._drag_start_scene = event.scenePos()
            self._drag_start_rect = QRectF(self._get_parent_rect() or self.rect())
            self._left_click_timestamp = QTimer().remainingTime()  # marker for click timing
            # Store grab offset in view coords so movement is based on where inside the box user clicked
            scene = self.scene()
            try:
                view = scene.views()[0] if scene and scene.views() else None
                press_view_pt: QPointF | None = None
                if view is not None:
                    # Refresh `_view_rect` so it reflects the current view transform (fit/zoom changes)
                    self._refresh_view_rect_from_parent()
                    press_view_pt = QPointF(view.mapFromScene(self._drag_start_scene))
                    if self._view_rect is None:
                        # If no view rect set, derive it from current parent rect
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

                # Snapshot start view rect for drag computations
                if self._view_rect is not None:
                    self._start_view_rect = QRectF(self._view_rect)
                    if press_view_pt is not None:
                        self._grab_offset = QPointF(
                            press_view_pt.x() - self._view_rect.x(),
                            press_view_pt.y() - self._view_rect.y(),
                        )
                else:
                    self._start_view_rect = None
                    self._grab_offset = None
            except Exception:
                self._grab_offset = None
                self._start_view_rect = None

            # Mark that a potential drag may begin and set cursor accordingly
            self._was_dragged = False
            self._last_action = "press"
            with contextlib.suppress(Exception):
                self.setCursor(Qt.ClosedHandCursor)
                # Prevent the view from initiating panning while dragging selection interior
                with contextlib.suppress(Exception):
                    self.grabMouse()

            _logger.debug(
                "Selection mousePress: BUTTON=Left scene=(%.1f,%.1f) drag_start_rect=%s view_rect=%s grab_offset=%s",
                float(self._drag_start_scene.x()),
                float(self._drag_start_scene.y()),
                getattr(self, "_drag_start_rect", None),
                getattr(self, "_view_rect", None),
                getattr(self, "_grab_offset", None),
            )

            # Disable view panning while dragging
            if scene is not None:
                views = scene.views()
                if views:
                    view = views[0]
                    try:
                        self._prev_view_state = view.dragMode()
                        view.setDragMode(QGraphicsView.DragMode.NoDrag)
                    except Exception:
                        self._prev_view_state = None

            # Logging: selection press
            try:
                pt = self._drag_start_scene
                _logger.debug(
                    "Selection mousePress: scene=(%.1f,%.1f) drag_start_rect=%s view_rect=%s grab_offset=%s",
                    float(pt.x()),
                    float(pt.y()),
                    getattr(self, "_drag_start_rect", None),
                    getattr(self, "_view_rect", None),
                    getattr(self, "_grab_offset", None),
                )
            except Exception:
                _logger.debug("Selection mousePress: (failed to read positions)", exc_info=True)

            event.accept()
        else:
            super().mousePressEvent(event)

    def _compute_drag_target_view_rect(self, view, scene_pos) -> QRectF | None:
        """Compute target rectangle for drag operation in view coordinates."""
        cur_view_pt = view.mapFromScene(scene_pos)
        try:
            _logger.debug(
                "_compute_drag_target_view_rect: scene_pos=(%.1f,%.1f) cur_view_pt=(%.1f,%.1f) "
                "start_view_rect=%s view_rect=%s",
                float(scene_pos.x()),
                float(scene_pos.y()),
                float(cur_view_pt.x()),
                float(cur_view_pt.y()),
                getattr(self, "_start_view_rect", None),
                getattr(self, "_view_rect", None),
            )
        except Exception:
            _logger.debug("_compute_drag_target_view_rect: (failed to log positions)", exc_info=True)

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
        """Return the pixmap's bounding rectangle in VIEW coordinates, or None if unavailable."""
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
        """Clamp target rectangle to the visible pixmap area (in view coords) where possible.

        Falls back to the viewport rectangle if the pixmap mapping isn't available.
        Also reduces width/height if they exceed the available area to ensure the selection remains
        completely inside the pixmap (or viewport).
        """
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
        """Force scene and item update."""
        try:
            self.update()
            scene = self.scene()
            if scene is not None:
                scene.update()
        except Exception:
            pass

    def _handle_fallback_drag(self, scene_pos) -> None:
        """Handle drag using parent coordinates as fallback."""
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

    def mouseMoveEvent(self, event) -> None:  # type: ignore
        if getattr(self, "_is_dragging", False):
            scene_pos = event.scenePos()
            scene = self.scene()

            # Try view-based movement first
            if scene and scene.views():
                view = scene.views()[0]
                target = self._compute_drag_target_view_rect(view, scene_pos)

                if target is not None:
                    target = self._clamp_to_viewport(view, target)
                    # Log computed target and clamp results
                    try:
                        _logger.debug(
                            "Selection mouseMove: scene=(%.1f,%.1f) computed_target_view=(%.1f,%.1f,%.1f,%.1f) "
                            "clamped_target=(%.1f,%.1f,%.1f,%.1f)",
                            float(scene_pos.x()),
                            float(scene_pos.y()),
                            float(target.x()),
                            float(target.y()),
                            float(target.width()),
                            float(target.height()),
                            float(target.x()),
                            float(target.y()),
                            float(target.width()),
                            float(target.height()),
                        )
                    except Exception:
                        _logger.debug("Selection mouseMove: (failed to log target)", exc_info=True)

                    self._view_rect = target
                    # Mark that this update originated from the view so parent mapping will be computed
                    self._last_update_by = "view"
                    self._apply_view_rect_to_parent()
                    self._update_scene()
                    event.accept()
                    return

            # Fallback to parent coordinate movement
            _logger.debug("Selection fallback drag: scene=(%.1f,%.1f)", float(scene_pos.x()), float(scene_pos.y()))
            self._handle_fallback_drag(scene_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore
        if getattr(self, "_is_dragging", False):
            self._is_dragging = False
            # Restore view drag mode if we changed it
            scene = self.scene()
            try:
                _logger.debug(
                    "Selection mouseRelease: restoring prev_view_state=%s", getattr(self, "_prev_view_state", None)
                )
            except Exception:
                _logger.debug("Selection mouseRelease: (failed to log prev state)", exc_info=True)
            if scene is not None and hasattr(self, "_prev_view_state") and self._prev_view_state is not None:
                views = scene.views()
                if views:
                    view = views[0]
                    with contextlib.suppress(Exception):
                        view.setDragMode(self._prev_view_state)

            # Release mouse grab in case we grabbed during press
            with contextlib.suppress(Exception):
                self.releaseMouse()

            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def resize_handle_to(  # noqa: PLR0915
        self, index: int, parent_x: float, parent_y: float, start_rect: QRectF | None = None
    ) -> None:
        """Resize selection rectangle using a handle at `index`.

        parent_x/parent_y are in the parent (pixmap) coordinate system.
        ``start_rect`` is optional and used by HandleItem to pass the rect at drag start.
        """
        r = QRectF(start_rect if start_rect is not None else self.rect())

        min_size = 8

        # Convert parent coords into new candidate coords for edges
        left = r.left()
        top = r.top()
        right = r.right()
        bottom = r.bottom()

        parent_rect = self.parentItem().boundingRect()

        def clamp_x(x: float) -> float:
            return max(parent_rect.left(), min(x, parent_rect.right()))

        def clamp_y(y: float) -> float:
            return max(parent_rect.top(), min(y, parent_rect.bottom()))

        # Edge handlers
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
        # Corner handlers
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

        # Maintain aspect ratio if set (delegated to helper to reduce complexity)
        if self._aspect_ratio:
            rect = QRectF(left, top, right - left, bottom - top)
            rect = self._apply_aspect_ratio(index, rect, min_size)
            left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()

        # Delegate remainder to helpers to keep this function < 50 statements
        new_left, new_top, new_right, new_bottom = self._calc_clamped_rect(left, top, right, bottom, min_size)
        try:
            _logger.debug(
                "resize_handle_to: index=%s parent_xy=(%.1f,%.1f) -> new_parent_rect=(%.1f,%.1f,%.1f,%.1f)",
                index,
                float(parent_x),
                float(parent_y),
                float(new_left),
                float(new_top),
                float(new_right - new_left),
                float(new_bottom - new_top),
            )
        except Exception:
            _logger.debug("resize_handle_to: (failed to log values)", exc_info=True)
        self._apply_new_rect(new_left, new_top, new_right, new_bottom, min_size)

    def _apply_aspect_ratio(self, index: int, rect: QRectF, min_size: int) -> QRectF:
        """Adjust rectangle edges to maintain the configured aspect ratio.

        Separated out to keep `resize_handle_to` small and readable.
        """
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

        # When setRect is called externally, assume caller is manipulating parent coords; update
        # authoritative parent rect and `_view_rect` to match so subsequent interactions remain view-based.
        pr = QRectF(*args) if len(args) == _RECT_ARGS_LEN else args[0]
        # Store authoritative parent rect exactly as provided
        self._parent_rect = QRectF(float(pr.x()), float(pr.y()), float(pr.width()), float(pr.height()))

        super().setRect(*args)
        self._update_handles()

        # Update view rect to reflect parent rect change (map parent->view)
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
        # Mark that the authoritative update originated from parent coords so subsequent calls
        # to _get_parent_rect can return the cached parent rect for consistency during immediate
        # handle updates.
        self._last_update_by = "parent"

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore
        """Draw selection rectangle with 4x4 grid overlay."""
        super().paint(painter, option, widget)

        # Draw grid lines with float coordinates for subpixel smoothing
        r = self.rect()
        painter.setPen(QPen(QColor(255, 255, 255, 160), 2, Qt.PenStyle.DotLine))

        # Vertical lines
        for i in range(1, self.GRID_LINES):
            x = r.left() + (r.width() * i / self.GRID_LINES)
            painter.drawLine(QLineF(x, r.top(), x, r.bottom()))

        # Horizontal lines
        for i in range(1, self.GRID_LINES):
            y = r.top() + (r.height() * i / self.GRID_LINES)
            painter.drawLine(QLineF(r.left(), y, r.right(), y))

    def set_aspect_ratio(self, ratio: tuple[int, int] | None) -> None:
        """Lock selection to specific aspect ratio."""
        self._aspect_ratio = ratio
        if ratio:
            # Adjust current rect to match ratio
            r = self.rect()
            w, h = ratio
            current_ratio = w / h
            new_width = r.height() * current_ratio
            r.setWidth(new_width)
            self.setRect(r)

    def _calc_clamped_rect(
        self, left: float, top: float, right: float, bottom: float, min_size: int
    ) -> tuple[float, float, float, float]:
        """Helper to clamp to parent bounds and ensure minimum size."""
        parent_rect = self.parentItem().boundingRect()
        left = max(parent_rect.left(), left)
        top = max(parent_rect.top(), top)
        right = min(parent_rect.right(), right)
        bottom = min(parent_rect.bottom(), bottom)
        return left, top, right, bottom

    def _apply_new_rect(self, left: float, top: float, right: float, bottom: float, min_size: int) -> None:
        """Helper to build and apply new QRectF to selection."""
        new_rect = QRectF(left, top, max(min_size, right - left), max(min_size, bottom - top))
        self.setRect(new_rect)

    def get_crop_rect(self) -> tuple[int, int, int, int]:
        """Get crop rectangle in parent pixmap coordinates.

        Prefer the authoritative `_parent_rect` if available (set by `setRect` or when applying
        a view rect), otherwise compute mapping from view coords as a fallback.
        Returns integer pixel coordinates (left, top, width, height).
        """
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
        """Compute parent rect from `_view_rect` WITHOUT mutating authoritative state."""
        if self._view_rect is None:
            return None
        scene = self.scene()
        if scene is None or not scene.views():
            return None
        view = scene.views()[0]
        tl_view = self._view_rect.topLeft()
        br_view = self._view_rect.bottomRight()
        # mapToScene doesn't accept QPointF in this PySide build; pass integer coordinates
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
        """Map current `_view_rect` into parent (pixmap) coordinates for painting and cropping.

        Use authoritative `_parent_rect` if the last update was parent-originating; otherwise compute from view
        and make that the authoritative `_parent_rect`.
        """
        if self._view_rect is None:
            return None

        # If a parent-originating update is authoritative, return it directly
        if getattr(self, "_last_update_by", None) == "parent" and getattr(self, "_parent_rect", None) is not None:
            return QRectF(self._parent_rect)

        # Compute from view and store as authoritative
        pr = self._compute_parent_rect_from_view()
        if pr is None:
            return None
        self._parent_rect = QRectF(float(pr.x()), float(pr.y()), float(pr.width()), float(pr.height()))
        self._last_update_by = "view"
        return QRectF(self._parent_rect)

    def _apply_view_rect_to_parent(self) -> None:
        """Apply `_view_rect` to the item's parent coordinates by setting the actual rect used
        by QGraphicsRectItem for display (calls setRect)."""
        pr = self._get_parent_rect()
        if pr is None:
            _logger.debug(
                "_apply_view_rect_to_parent: no parent rect (view_rect=%s)", getattr(self, "_view_rect", None)
            )
            return
        # Clamp to parent bounds
        parent_rect = self.parentItem().boundingRect()
        left = max(parent_rect.left(), min(pr.left(), parent_rect.right() - pr.width()))
        top = max(parent_rect.top(), min(pr.top(), parent_rect.bottom() - pr.height()))
        try:
            _logger.debug(
                "_apply_view_rect_to_parent: applying parent_rect=(%.1f,%.1f,%.1f,%.1f) clamped=(%.1f,%.1f)",
                float(pr.x()),
                float(pr.y()),
                float(pr.width()),
                float(pr.height()),
                float(left),
                float(top),
            )
        except Exception:
            _logger.debug("_apply_view_rect_to_parent: (failed to log rects)", exc_info=True)
        self.setRect(QRectF(left, top, pr.width(), pr.height()))


class PresetDialog(QDialog):
    """Dialog for adding custom aspect ratio presets."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add Crop Preset")
        self.setModal(True)

        self.preset_data: dict[str, list[int]] | None = None

        layout = QVBoxLayout(self)

        # Name input
        layout.addWidget(QLabel("Preset Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., 21:9")
        layout.addWidget(self.name_input)

        # Ratio inputs
        ratio_layout = QHBoxLayout()
        ratio_layout.addWidget(QLabel("Width:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 9999)
        self.width_spin.setValue(16)
        ratio_layout.addWidget(self.width_spin)

        ratio_layout.addWidget(QLabel("Height:"))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 9999)
        self.height_spin.setValue(9)
        ratio_layout.addWidget(self.height_spin)

        layout.addLayout(ratio_layout)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

    def _on_ok(self) -> None:
        """Validate and accept dialog."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Input", "Please enter a preset name")
            return

        self.preset_data = {
            "name": name,
            "ratio": [self.width_spin.value(), self.height_spin.value()],
        }
        self.accept()


class CropDialog(QDialog):
    """Main crop dialog with interactive selection and preview."""

    def __init__(self, parent: QWidget | None, image_path: str, original_pixmap: QPixmap):
        super().__init__(parent)
        # Use the provided image path as the dialog title so the full file path is visible
        self.setWindowTitle(str(image_path) if image_path else "Crop Image")
        self.setModal(True)
        # Offer maximize/close hints; keep dialog modal for workflow requirements
        self.setWindowFlags(Qt.Window | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)

        self._image_path = image_path
        self._original_pixmap = original_pixmap
        self._preview_mode = False
        self._zoom_mode = "fit"  # "fit" or "actual"

        # Graphics setup
        self._scene = QGraphicsScene()
        self._view = QGraphicsView(self._scene)
        self._pix_item = QGraphicsPixmapItem(original_pixmap)
        self._scene.addItem(self._pix_item)

        # Selection rectangle
        pixmap_rect = self._pix_item.boundingRect()
        # Initialize view-space rectangle to centered half-size of pixmap; map to view coords
        initial_parent_rect = QRectF(
            pixmap_rect.width() * 0.25,
            pixmap_rect.height() * 0.25,
            pixmap_rect.width() * 0.5,
            pixmap_rect.height() * 0.5,
        )
        # Create selection item and set internal view rect via helper
        self._selection = SelectionRectItem(self._pix_item)
        self._selection.set_parent_rect(initial_parent_rect)  # sets _view_rect internally

        # View settings - use NoDrag to allow selection rectangle to receive mouse events
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Use crosshair cursor in the canvas to indicate selection interactions
        try:
            self._view.setCursor(Qt.CrossCursor)
            self._view.viewport().setCursor(Qt.CrossCursor)
        except Exception:
            pass

        # Ensure viewport accepts mouse events so clicks reach items
        with contextlib.suppress(Exception):
            self._view.viewport().setAttribute(self._view.viewport().attribute(0), True)

        # Encourage expanding layout but defer final geometry until showEvent
        self._view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(640, 480)
        self._sized_shown = False

        self._setup_ui()
        self._apply_zoom_mode("fit")  # Start in fit mode

        # Defer sizing to showEvent (will size to screen available geometry)
        # Keep visible after construction to satisfy tests and callers that expect the dialog to be shown
        self.show()
        _logger.info("Opened crop dialog for: %s", image_path)

    def _setup_ui(self) -> None:
        """Setup dialog layout."""
        main_layout = QHBoxLayout(self)

        # Left panel: zoom + presets
        left_panel = self._create_left_panel()
        main_layout.addWidget(left_panel)

        # Center: canvas
        main_layout.addWidget(self._view, stretch=1)

        # Right panel: action buttons
        right_panel = self._create_right_panel()
        main_layout.addWidget(right_panel)

    def _create_left_panel(self) -> QWidget:
        """Create left panel with zoom controls and presets."""
        panel = QWidget()
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)

        # Zoom mode buttons
        layout.addWidget(QLabel("View Mode:"))

        self.fit_btn = QPushButton("Fit to Window")
        self.fit_btn.setCheckable(True)
        self.fit_btn.setChecked(True)
        self.fit_btn.clicked.connect(lambda: self._apply_zoom_mode("fit"))
        layout.addWidget(self.fit_btn)

        self.actual_btn = QPushButton("1:1 (Actual Pixels)")
        self.actual_btn.setCheckable(True)
        self.actual_btn.clicked.connect(lambda: self._apply_zoom_mode("actual"))
        layout.addWidget(self.actual_btn)

        layout.addSpacing(20)

        # Presets
        layout.addWidget(QLabel("Aspect Ratio Presets:"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumWidth(200)
        scroll.setMaximumHeight(300)

        preset_widget = QWidget()
        preset_layout = QVBoxLayout(preset_widget)

        # Load presets from settings
        settings_path = "settings.json"  # This will be passed from operations
        settings = SettingsManager(settings_path)
        presets = settings.get("crop_presets", [])

        for preset in presets:
            btn = QPushButton(preset["name"])
            ratio = tuple(preset["ratio"])
            btn.clicked.connect(lambda checked=False, r=ratio: self._apply_preset(r))
            preset_layout.addWidget(btn)

        # Free ratio button
        free_btn = QPushButton("Free (No Lock)")
        free_btn.clicked.connect(lambda: self._selection.set_aspect_ratio(None))
        preset_layout.addWidget(free_btn)

        preset_layout.addStretch()

        scroll.setWidget(preset_widget)
        layout.addWidget(scroll)

        # Add preset button
        add_preset_btn = QPushButton("Add Preset...")
        add_preset_btn.clicked.connect(self._on_add_preset)
        layout.addWidget(add_preset_btn)

        layout.addStretch()
        return panel

    def _create_right_panel(self) -> QWidget:
        """Create right panel with action buttons."""
        panel = QWidget()
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)

        layout.addStretch()

        # Preview button
        self.preview_btn = QPushButton("Preview")
        self.preview_btn.clicked.connect(self._on_preview)
        layout.addWidget(self.preview_btn)

        # Cancel button (hidden initially)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel_preview)
        self.cancel_btn.setVisible(False)
        layout.addWidget(self.cancel_btn)

        # Save button
        self.save_btn = QPushButton("Save...")
        self.save_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_btn)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)

        layout.addStretch()
        return panel

    def showEvent(self, event) -> None:  # type: ignore
        """Try to maximize with the OS, but fall back to available geometry if that fails.

        We attempt a real maximize (setWindowState(... | Qt.WindowMaximized)) shortly after show;
        if the window manager ignores the request (common for modal/transient windows on some
        platforms), we then size the dialog to the screen's available geometry with a small margin.
        Finally, re-fit the view after layout stabilizes.
        """
        super().showEvent(event)
        if getattr(self, "_sized_shown", False):
            return
        self._sized_shown = True

        def try_maximize() -> None:
            with contextlib.suppress(Exception):
                self.setWindowState(self.windowState() | Qt.WindowMaximized)

        def fallback_if_not_maximized() -> None:
            try:
                # If the widget is deleted or otherwise unavailable, accessing windowState may raise
                if not (self.windowState() & Qt.WindowMaximized):
                    screen = QGuiApplication.screenAt(QCursor.pos()) or self.screen() or QGuiApplication.primaryScreen()
                    if screen is None:
                        return

                    avail = screen.availableGeometry()
                    margin_w = max(24, int(avail.width() * 0.02))
                    margin_h = max(24, int(avail.height() * 0.02))

                    target = QRect(
                        avail.left() + margin_w,
                        avail.top() + margin_h,
                        avail.width() - (margin_w * 2),
                        avail.height() - (margin_h * 2),
                    )

                    self.setGeometry(target)
            except Exception:
                # Widget may have been deleted or window manager interaction failed; ignore
                _logger.debug("fallback_if_not_maximized: widget unavailable or error", exc_info=True)
                return
            finally:

                def _deferred_fit() -> None:
                    try:
                        if (
                            self._zoom_mode == "fit"
                            and getattr(self, "_view", None) is not None
                            and getattr(self, "_pix_item", None) is not None
                        ):
                            self._view.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)
                    except Exception:
                        _logger.debug("deferred fit failed (object may be deleted)", exc_info=True)

                QTimer.singleShot(0, _deferred_fit)

        # Ask for maximize immediately, then fall back after a short delay if maximize didn't take
        QTimer.singleShot(0, try_maximize)
        QTimer.singleShot(150, fallback_if_not_maximized)

    def _apply_zoom_mode(self, mode: str) -> None:
        """Apply zoom mode to view."""
        prev = getattr(self, "_zoom_mode", None)
        self._zoom_mode = mode
        _logger.debug("Zoom mode change: %s -> %s", prev, mode)

        if mode == "fit":
            self.fit_btn.setChecked(True)
            self.actual_btn.setChecked(False)
            self._view.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)
        else:  # actual
            self.fit_btn.setChecked(False)
            self.actual_btn.setChecked(True)
            self._view.resetTransform()

    def _apply_preset(self, ratio: tuple[int, int]) -> None:
        """Apply aspect ratio preset to selection."""
        _logger.info("Applying preset ratio: %s", ratio)
        self._selection.set_aspect_ratio(ratio)

    def _on_add_preset(self) -> None:
        """Open dialog to add new preset."""
        dialog = PresetDialog(self)
        if dialog.exec() and dialog.preset_data:
            # Save to settings
            settings = SettingsManager("settings.json")
            presets = settings.get("crop_presets", [])
            presets.append(dialog.preset_data)
            settings.set("crop_presets", presets)

            _logger.info("Added crop preset: %s", dialog.preset_data)

            # Recreate left panel to show new preset
            # (Simple approach: just add button dynamically)
            QMessageBox.information(self, "Preset Added", "Preset added successfully. Restart crop dialog to see it.")

    def _on_preview(self) -> None:
        """Show cropped preview."""
        crop_rect = self._selection.get_crop_rect()
        _logger.debug("Preview crop rect: %s", crop_rect)
        cropped_pix = self._original_pixmap.copy(QRect(*crop_rect))

        # Replace pixmap
        self._pix_item.setPixmap(cropped_pix)
        self._selection.setVisible(False)

        # Update UI state
        self._preview_mode = True
        # Hide the preview button and show the cancel button (preview no longer applicable)
        self.preview_btn.setVisible(False)
        self.preview_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)

        _logger.info("Preview mode enabled")

        # Re-apply zoom
        if self._zoom_mode == "fit":
            self._view.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _on_cancel_preview(self) -> None:
        """Restore original image."""
        _logger.info("Cancelling preview and restoring original image")
        self._pix_item.setPixmap(self._original_pixmap)
        self._selection.setVisible(True)

        # Update UI state
        self._preview_mode = False
        # Restore preview button visibility and enabled state
        self.preview_btn.setVisible(True)
        self.preview_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)

        # Re-apply zoom
        if self._zoom_mode == "fit":
            self._view.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _on_save(self) -> None:
        """Save cropped image."""
        crop_rect = self._selection.get_crop_rect()
        _logger.debug("Saving from dialog, crop_rect=%s", crop_rect)

        # Open save dialog with original filename as default
        original_path = Path(self._image_path)
        default_path = str(original_path)

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Cropped Image",
            default_path,
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All Files (*.*)",
        )

        if not save_path:
            _logger.debug("Save cancelled by user")
            return  # User cancelled

        _logger.info("User chose save path: %s", save_path)

        # Trigger save via operations
        self.accept()  # Close dialog
        # Parent will handle actual save via crop_operations.save_cropped_file
        self._saved_path = save_path
        self._crop_rect = crop_rect

    def get_save_info(self) -> tuple[tuple[int, int, int, int], str] | None:
        """Get crop rect and save path if user saved."""
        if hasattr(self, "_saved_path"):
            return (self._crop_rect, self._saved_path)
        return None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle ESC and Enter keys."""
        if event.key() == Qt.Key.Key_Escape:
            if self._preview_mode:
                # ESC in preview mode: restore original
                self._on_cancel_preview()
            else:
                # ESC in original mode: close dialog
                self.reject()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self._preview_mode:
                # Enter: trigger preview
                self._on_preview()
        else:
            super().keyPressEvent(event)
