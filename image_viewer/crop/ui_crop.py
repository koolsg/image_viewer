"""Crop dialog UI components.

Interactive crop dialog with selection rectangle, zoom modes, and aspect ratio presets.
"""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGraphicsPixmapItem,
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

from image_viewer.infra.logger import get_logger
from image_viewer.infra.settings_manager import SettingsManager

# local imports (may be split out later)
try:
    from .crop_selection_debug import cursor_name, overlay_message
    from .ui_crop_debug_overlay import DebugOverlay, ViewportWatcher
except Exception:
    DebugOverlay = None  # type: ignore
    ViewportWatcher = None  # type: ignore
    overlay_message = None  # type: ignore
    cursor_name = None  # type: ignore

# Re-export SelectionRectItem from the new module for backwards compatibility with imports
from .ui_crop_selection import SelectionRectItem  # re-export

# Note: import DebugOverlay/ViewportWatcher lazily later when creating overlay instances

# Number of args used to construct QRectF from varargs in setRect override
_RECT_ARGS_LEN = 4

if TYPE_CHECKING:
    from PySide6.QtGui import QKeyEvent

_logger = get_logger("ui_crop")
_logger.debug("ui_crop module loaded")


class PresetDialog(QDialog):
    """Dialog for adding custom aspect ratio presets."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Crop Preset")
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
        name: str = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Input", "Please enter a preset name")
            return

        self.preset_data = {
            "name": name,
            "ratio": [self.width_spin.value(), self.height_spin.value()],
        }
        self.accept()


class _CropCursorResetFilter(QObject):
    """Viewport-level safety net to prevent sticky resize cursors.

    Hover leave transitions between child/parent QGraphicsItems (or leaving items quickly)
    are not always delivered in a way that guarantees the cursor gets restored.
    This filter unsets the viewport cursor whenever the mouse is not over the selection
    or its handles, allowing the view's base cursor (crosshair) to show.
    """

    def __init__(self, view: QGraphicsView, selection: SelectionRectItem):
        super().__init__(view.viewport())
        self._view = view
        self._selection = selection

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore  # noqa: PLR0912
        try:
            et = event.type()
            if et == QEvent.Leave:
                with contextlib.suppress(Exception):
                    self._view.viewport().unsetCursor()
                return False

            if et not in (QEvent.MouseMove, QEvent.HoverMove):
                return False

            pos = None
            if hasattr(event, "position"):
                posf = event.position()  # type: ignore[attr-defined]
                with contextlib.suppress(Exception):
                    pos = posf.toPoint()
            if pos is None and hasattr(event, "pos"):
                pos = event.pos()  # type: ignore[attr-defined]
            if pos is None:
                return False

            scene = self._view.scene()
            if scene is None:
                return False

            scene_pos = self._view.mapToScene(pos)
            items = scene.items(scene_pos)

            # Show mouse position and current cursor in overlay when available.
            with contextlib.suppress(Exception):
                ov = getattr(self._selection, "_debug_overlay", None)
                if ov is not None:
                    try:
                        cur_shape = self._view.viewport().cursor().shape()
                        cur_name = cursor_name(cur_shape) if callable(cursor_name) else str(cur_shape)
                        msg = {"mouse": f"{int(scene_pos.x())},{int(scene_pos.y())}", "cursor": cur_name}
                        debug_requested = getattr(self, "_debug_overlay_requested", False)
                        if ov is not None:
                            ov.show_message(msg)
                        elif not debug_requested:
                            _logger.debug("hover: %s", msg)
                        # else: debug was requested and overlay missing -> silent
                    except Exception:
                        pass

            if not any(self._is_selection_related(it) for it in items):
                with contextlib.suppress(Exception):
                    self._view.viewport().unsetCursor()
                    # Indicate cursor exit in overlay
                    ov = getattr(self._selection, "_debug_overlay", None)
                    if ov is not None:
                        with contextlib.suppress(Exception):
                            msg = {"mouse": f"{int(scene_pos.x())},{int(scene_pos.y())}", "cursor": "exit"}
                            debug_requested = getattr(self, "_debug_overlay_requested", False)
                            if ov is not None:
                                ov.show_message(msg)
                            elif not debug_requested:
                                _logger.debug("hover exit: %s", msg)
                            # else: debug requested and overlay missing -> silent
        except Exception:
            return False

        return False

    def _is_selection_related(self, item) -> bool:
        try:
            cur = item
            while cur is not None:
                if cur is self._selection:
                    return True
                cur = cur.parentItem()
        except Exception:
            return False
        return False


class _CropWheelEventFilter(QObject):
    """Forward viewport wheel events to the dialog's wheel handler."""

    def __init__(self, dialog: CropDialog):
        super().__init__(dialog)
        self._dialog = dialog

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore
        try:
            if event.type() == QEvent.Type.Wheel:
                self._dialog.wheelEvent(event)
                return True
        except Exception:
            return False
        return False


class CropDialog(QDialog):
    """Main crop dialog with interactive selection and preview."""

    def __init__(self, parent: QWidget | None, image_path: str, original_pixmap: QPixmap):
        super().__init__(parent)
        # Use the provided image path as the dialog title so the full file path is visible
        self.setWindowTitle(str(image_path) if image_path else "Crop Image")
        self.setModal(True)
        # Offer maximize/close hints; keep dialog modal for workflow requirements
        self.setWindowFlags(Qt.Window | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)

        self._init_window_state(image_path, original_pixmap)
        self._setup_graphics(original_pixmap)
        self._configure_view()

        self._viewer = parent
        self._engine = getattr(parent, "engine", None)
        self._pending_image_path: str | None = None
        self._nav_prev_btn: QPushButton | None = None
        self._nav_next_btn: QPushButton | None = None

        self._setup_ui()
        self._update_nav_buttons()
        self._apply_zoom_mode("fit")

        # Optionally enable the debug overlay when running in debug mode (env var or logger DEBUG)
        self._maybe_init_debug_overlay()
        self._subscribe_to_engine_signals()

        self.show()
        _logger.info("Opened crop dialog for: %s", image_path)

    def _init_window_state(self, image_path: str, original_pixmap: QPixmap) -> None:
        self._image_path = image_path
        self._original_pixmap = original_pixmap
        self._preview_mode = False
        self._zoom_mode = "fit"

    def _setup_graphics(self, original_pixmap: QPixmap) -> None:
        self._scene = QGraphicsScene()
        self._view = QGraphicsView(self._scene)
        self._pix_item = QGraphicsPixmapItem(original_pixmap)
        self._scene.addItem(self._pix_item)

        # Create selection item and set internal view rect via helper
        pixmap_rect = self._pix_item.boundingRect()
        initial_parent_rect = self._compute_initial_parent_rect(pixmap_rect)
        self._selection = SelectionRectItem(self._pix_item)
        self._selection.set_parent_rect(initial_parent_rect)

    def _compute_initial_parent_rect(self, pixmap_rect: QRectF) -> QRectF:
        """Return a default centered parent rect for selection based on `pixmap_rect`."""
        if pixmap_rect.width() <= 0 or pixmap_rect.height() <= 0:
            return QRectF()
        return QRectF(
            pixmap_rect.width() * 0.25,
            pixmap_rect.height() * 0.25,
            pixmap_rect.width() * 0.5,
            pixmap_rect.height() * 0.5,
        )

    def _set_view_pixmap(self, pixmap: QPixmap) -> None:
        """Safely set the current pixmap on the scene and reset positioning."""
        with contextlib.suppress(Exception):
            self._pix_item.setPixmap(pixmap)
            self._scene.setSceneRect(self._pix_item.boundingRect())
            self._pix_item.setPos(0, 0)
            self._pix_item.setOffset(0, 0)

    def _fit_or_reset_and_center(self, deferred: bool = True) -> None:
        """Apply zoom mode (fit or actual), center the view, optionally deferred via QTimer."""

        def _do() -> None:
            try:
                with contextlib.suppress(Exception):
                    self._scene.setSceneRect(self._pix_item.boundingRect())
                    self._pix_item.setPos(0, 0)
                if self._zoom_mode == "fit":
                    with contextlib.suppress(Exception):
                        self._view.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)
                else:
                    with contextlib.suppress(Exception):
                        self._view.resetTransform()
                with contextlib.suppress(Exception):
                    self._pix_item.setOffset(0, 0)
                with contextlib.suppress(Exception):
                    center_scene_pt = self._pix_item.mapToScene(self._pix_item.boundingRect().center())
                    self._view.centerOn(center_scene_pt)
            except Exception:
                _logger.debug("_fit_or_reset_and_center: error", exc_info=True)

        if deferred:
            with contextlib.suppress(Exception):
                QTimer.singleShot(0, _do)
        else:
            _do()

    def _configure_view(self) -> None:
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        try:
            self._view.setCursor(Qt.CrossCursor)
            self._view.viewport().setCursor(Qt.CrossCursor)
        except Exception:
            pass

        self._view.setMouseTracking(True)
        self._view.viewport().setMouseTracking(True)
        with contextlib.suppress(Exception):
            self._view.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            self._view.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        # Forward wheel events from the viewport to the dialog so zoom is reliable.
        with contextlib.suppress(Exception):
            self._wheel_filter = _CropWheelEventFilter(self)
            self._view.viewport().installEventFilter(self._wheel_filter)

        # Cursor authority safety net: ensure the viewport cursor is restored when the mouse is
        # no longer over the selection/handles (covers cases where hoverLeave isn't delivered).
        with contextlib.suppress(Exception):
            self._cursor_reset_filter = _CropCursorResetFilter(self._view, self._selection)
            self._view.viewport().installEventFilter(self._cursor_reset_filter)

        self._view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(640, 480)
        self._sized_shown = False

    def _maybe_init_debug_overlay(self) -> None:
        self._debug_overlay = None
        try:
            debug_env = os.getenv("IMAGE_VIEWER_DEBUG_OVERLAY", "").lower() in ("1", "true", "yes")
            debug_logger = _logger.isEnabledFor(logging.DEBUG)
            self._debug_overlay_requested = debug_env or debug_logger
            if (debug_env or debug_logger) and DebugOverlay is not None and ViewportWatcher is not None:
                try:
                    # Parent overlay to the left panel so it appears in the left panel's
                    # bottom-left instead of the canvas viewport
                    parent_for_overlay = getattr(self, "_left_panel", self._view.viewport())
                    self._debug_overlay = DebugOverlay(parent_for_overlay)
                    # Mark overlay with the requested state so it can persist visibility
                    self._debug_overlay._debug_requested = self._debug_overlay_requested
                    watcher = ViewportWatcher(self._debug_overlay)
                    # Watch parent resize events so overlay repositions correctly
                    parent_for_overlay.installEventFilter(watcher)
                    self._viewport_watcher = watcher
                    self._debug_overlay.reposition()
                    if getattr(self, "_selection", None) is not None:
                        self._selection._debug_overlay = self._debug_overlay
                        # Always communicate that debug mode was requested to the selection
                        self._selection._debug_overlay_requested = self._debug_overlay_requested
                except Exception:
                    _logger.debug("Failed to initialize debug overlay", exc_info=True)
            else:
                # Communicate debug-requested state to selection even when overlay init skipped
                try:
                    if getattr(self, "_selection", None) is not None:
                        self._selection._debug_overlay_requested = getattr(self, "_debug_overlay_requested", False)
                except Exception:
                    pass
        except Exception:
            pass

    def _setup_ui(self) -> None:
        """Setup dialog layout."""
        main_layout = QHBoxLayout(self)
        # Prevent side panels from collapsing to zero width on maximize/resize.
        # The center view has stretch=1; panels are fixed at stretch=0 with sensible minimums.
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Left panel: zoom + presets
        left_panel = self._create_left_panel()
        # Keep a reference so we can parent the debug overlay to the left panel (bottom-left)
        self._left_panel = left_panel
        main_layout.addWidget(left_panel, stretch=0)

        # Center: canvas
        main_layout.addWidget(self._view, stretch=1)

        # Right panel: action buttons
        right_panel = self._create_right_panel()
        main_layout.addWidget(right_panel, stretch=0)

        # Be explicit: center view consumes remaining space.
        main_layout.setStretch(0, 0)
        main_layout.setStretch(1, 1)
        main_layout.setStretch(2, 0)

    def _create_left_panel(self) -> QWidget:
        """Create left panel with zoom controls and presets."""
        panel = QWidget()
        # Ensure panel remains visible even when the view expands aggressively.
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(280)
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

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

        # Configure preset button
        configure_presets_btn = QPushButton("Configure Preset")
        configure_presets_btn.clicked.connect(self._on_configure_presets)
        layout.addWidget(configure_presets_btn)

        layout.addStretch()
        return panel

    def _create_right_panel(self) -> QWidget:
        """Create right panel with action buttons."""
        panel = QWidget()
        # Ensure panel remains visible even when the view expands aggressively.
        panel.setMinimumWidth(150)
        panel.setMaximumWidth(220)
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

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

        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)

        prev_btn = QPushButton("<")
        prev_btn.setToolTip("Load previous image")
        prev_btn.clicked.connect(self._on_prev_image)
        nav_layout.addWidget(prev_btn)

        next_btn = QPushButton(">")
        next_btn.setToolTip("Load next image")
        next_btn.clicked.connect(self._on_next_image)
        nav_layout.addWidget(next_btn)

        self._nav_prev_btn = prev_btn
        self._nav_next_btn = next_btn

        layout.addLayout(nav_layout)
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

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        """Filter wheel-like events from the viewport.

        Tests use a lightweight fake wheel event that is not a real Qt `QEvent`.
        Be permissive here: if an object has `angleDelta()`, forward it to
        `wheelEvent()` and report the event handled.
        """
        try:
            if hasattr(event, "angleDelta"):
                self.wheelEvent(event)  # type: ignore[arg-type]
                return True
        except Exception:
            return False
        # Avoid calling the Qt base implementation with non-QEvent objects.
        try:
            return super().eventFilter(obj, event)
        except TypeError:
            return False

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

    def _reset_selection_for_current_pixmap(self) -> None:
        pixmap_rect = self._pix_item.boundingRect()
        if pixmap_rect.width() <= 0 or pixmap_rect.height() <= 0:
            return
        parent_rect = self._compute_initial_parent_rect(pixmap_rect)
        self._selection.set_parent_rect(parent_rect)

    def _refresh_view_after_pixmap_update(self) -> None:
        # Defer to centralized helper which handles fit/reset, centering and safety
        self._fit_or_reset_and_center(deferred=True)

    def _update_nav_buttons(self) -> None:
        prev_btn = getattr(self, "_nav_prev_btn", None)
        next_btn = getattr(self, "_nav_next_btn", None)
        if prev_btn is None or next_btn is None:
            return

        viewer = getattr(self, "_viewer", None)
        image_files = getattr(viewer, "image_files", None) if viewer is not None else None
        if not viewer or not image_files:
            prev_btn.setEnabled(False)
            next_btn.setEnabled(False)
            return

        current_index = getattr(viewer, "current_index", -1)
        total = len(image_files)
        prev_btn.setEnabled(current_index > 0)
        next_btn.setEnabled(current_index < total - 1)

    def _reset_preview_state(self) -> None:
        self._preview_mode = False
        with contextlib.suppress(Exception):
            self.preview_btn.setVisible(True)
            self.preview_btn.setEnabled(True)
            self.cancel_btn.setVisible(False)

    def _on_prev_image(self) -> None:
        self._navigate_to_adjacent(-1)

    def _on_next_image(self) -> None:
        self._navigate_to_adjacent(1)

    def _navigate_to_adjacent(self, delta: int) -> None:
        viewer = getattr(self, "_viewer", None)
        if viewer is None:
            return
        image_files = getattr(viewer, "image_files", None)
        if not image_files:
            return

        target_index = viewer.current_index + delta
        if target_index < 0 or target_index >= len(image_files):
            return

        target_path = image_files[target_index]

        # IMPORTANT: set pending path BEFORE invoking navigation.
        # - If the engine emits signals synchronously, we won't miss them.
        # - If the navigation ends up being ignored (e.g., current image still loading),
        #   we clear the pending marker below.
        self._pending_image_path = target_path

        nav_method = viewer.prev_image if delta < 0 else viewer.next_image
        nav_method()

        if getattr(viewer, "current_index", None) != target_index:
            self._pending_image_path = None
            return

        # If the viewer hit its own pixmap cache, it will update itself without
        # going through engine.image_ready. In that case, we must refresh our
        # dialog from the engine cache immediately.
        engine = getattr(self, "_engine", None)
        if engine is not None:
            with contextlib.suppress(Exception):
                cached = engine.get_cached_pixmap(target_path)
                if cached is not None and not cached.isNull():
                    self._set_dialog_pixmap(target_path, cached)
                    return

        self._reset_preview_state()
        self._update_nav_buttons()

    def _on_engine_image_ready(self, path: str, pixmap: QPixmap, error: object) -> None:
        if path != getattr(self, "_pending_image_path", None):
            return
        if error is not None:
            self._pending_image_path = None
            return
        if pixmap is None or pixmap.isNull():
            self._pending_image_path = None
            return
        self._set_dialog_pixmap(path, pixmap)

    def _set_dialog_pixmap(self, path: str, pixmap: QPixmap) -> None:
        if not path or pixmap.isNull():
            return
        self._image_path = path
        self._original_pixmap = pixmap
        with contextlib.suppress(Exception):
            self.setWindowTitle(str(path))
        # Safely set pixmap and reset positioning using helper
        self._set_view_pixmap(pixmap)
        self._selection.setVisible(True)
        self._reset_selection_for_current_pixmap()
        # Defer fit/center to match previous semantics
        self._refresh_view_after_pixmap_update()
        self._reset_preview_state()
        self._pending_image_path = None
        self._update_nav_buttons()

    def _subscribe_to_engine_signals(self) -> None:
        engine = getattr(self, "_engine", None)
        if engine is None:
            return
        with contextlib.suppress(Exception):
            engine.image_ready.connect(self._on_engine_image_ready)

    def _apply_preset(self, ratio: tuple[int, int]) -> None:
        """Apply aspect ratio preset to selection."""
        _logger.info("Applying preset ratio: %s", ratio)
        self._selection.set_aspect_ratio(ratio)

    def _on_configure_presets(self) -> None:
        """Open dialog to configure (add) a new preset."""
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

        # Re-apply zoom and center the pixmap (deferred so pixmap update is settled)
        self._fit_or_reset_and_center(deferred=True)

    def _on_cancel_preview(self) -> None:
        """Restore original image."""
        _logger.info("Cancelling preview and restoring original image")
        self._pix_item.setPixmap(self._original_pixmap)
        self._selection.setVisible(True)

        # Update UI state
        self._reset_preview_state()

        # Re-apply zoom and center the pixmap (deferred so pixmap update is settled)
        self._fit_or_reset_and_center(deferred=True)

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

    def wheelEvent(self, event) -> None:
        """Handle mouse wheel for zoom in/out with 25% multiplication ratio.

        - Scroll up: 1.25x zoom in
        - Scroll down: 0.75x zoom out
        Zoom is applied to the view/scene scale directly.
        """
        try:
            if self._view is None or self._pix_item.pixmap().isNull():
                return

            angle = event.angleDelta().y()
            if angle == 0:
                return

            # Calculate zoom factor: 25% increment (1.25x or 0.75x)
            factor = 1.25 if angle > 0 else 0.75

            # Get current scale from view
            transform = self._view.transform()
            current_scale = transform.m11()  # Extract horizontal scale
            new_scale = current_scale * factor

            # Apply limits to prevent extreme zoom
            min_scale = 0.1
            max_scale = 10.0
            new_scale = max(min_scale, min(new_scale, max_scale))

            # Apply the new scale to the view
            self._view.resetTransform()
            self._view.scale(new_scale, new_scale)

            event.accept()
        except Exception as ex:
            _logger.debug("wheelEvent error: %s", ex)
            event.ignore()

    def keyPressEvent(self, arg__1: QKeyEvent) -> None:  # type: ignore
        """Handle ESC and Enter keys."""
        event = arg__1
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
