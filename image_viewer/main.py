import contextlib
import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QStandardPaths, Qt, QUrl
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtQuick import QQuickView
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from image_viewer.busy_cursor import busy_cursor
from image_viewer.explorer_mode_operations import open_folder_at, toggle_view_mode
from image_viewer.image_engine import ImageEngine
from image_viewer.image_engine.strategy import DecodingStrategy, FastViewStrategy
from image_viewer.logger import get_logger
from image_viewer.path_utils import abs_dir_str, abs_path_str
from image_viewer.qml_bridge import AppController, EngineImageProvider
from image_viewer.settings_manager import SettingsManager
from image_viewer.status_overlay import StatusOverlayBuilder
from image_viewer.trim import start_trim_workflow
from image_viewer.ui_canvas import ImageCanvas
from image_viewer.ui_convert_webp import WebPConvertDialog
from image_viewer.ui_hover_menu import HoverDrawerMenu
from image_viewer.ui_menus import build_menus
from image_viewer.ui_settings import SettingsDialog
from image_viewer.view_mode_operations import delete_current_file

from . import ui_shortcuts

_logger = get_logger("main")

# --- CLI logging options -----------------------------------------------------
# To prevent Qt from exiting due to unknown options, we preemptively parse
# our own options, reflect them in environment variables (IMAGE_VIEWER_LOG_LEVEL,
# IMAGE_VIEWER_LOG_CATS), and remove them from sys.argv.


def _apply_cli_logging_options() -> None:
    try:
        import argparse  # noqa: PLC0415
        import os as _os  # noqa: PLC0415
        import sys as _sys  # noqa: PLC0415

        parser = argparse.ArgumentParser(description="Image Viewer", add_help=False)
        parser.add_argument("--log-level", help="Set log level")
        parser.add_argument("--log-cats", help="Set log categories")
        args, remaining = parser.parse_known_args()
        if args.log_level:
            _os.environ["IMAGE_VIEWER_LOG_LEVEL"] = args.log_level
        if args.log_cats:
            _os.environ["IMAGE_VIEWER_LOG_CATS"] = args.log_cats
        _sys.argv[:] = [_sys.argv[0], *remaining]
    except Exception:
        # Failing to set up logging should not prevent the app from running.
        pass


_apply_cli_logging_options()
logger = get_logger("main")
_BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


class ViewState:
    """Encapsulates view-related state."""

    def __init__(self):
        self.preset_mode: str = "fit"  # "fit" or "actual"
        self.zoom: float = 1.0
        self.hq_downscale: bool = False
        # Note: press_zoom_multiplier is stored in canvas._press_zoom_multiplier


class TrimState:
    """Encapsulates trim workflow state."""

    def __init__(self):
        self.is_running: bool = False
        self.in_preview: bool = False


class ExplorerState:
    """Encapsulates explorer mode state."""

    def __init__(self):
        self.view_mode: bool = True  # True=View, False=Explorer
        self._explorer_tree: Any | None = None
        self._explorer_grid: Any | None = None


class ImageViewer(QMainWindow):
    def __init__(self):  # noqa: PLR0915
        super().__init__()
        self.setWindowTitle("Image Viewer")
        _logger.debug("ImageViewer initialization started")

        self.view_state = ViewState()
        self.trim_state = TrimState()
        self.explorer_state = ExplorerState()

        # ImageEngine: single entry point for all data/processing
        self.engine = ImageEngine(self)
        self.engine.image_ready.connect(self._on_engine_image_ready)
        self.engine.folder_changed.connect(self._on_engine_folder_changed)
        _logger.debug("ImageEngine connected")
        # Provide a status builder early so image_ready handlers can safely use it
        self._status_builder = StatusOverlayBuilder(self)

        self.image_files: list[str] = []  # Synced from engine
        self.current_index = -1
        # Menu/action placeholders (populated in build_menus)
        self.view_group = None
        self.fit_action = None
        self.actual_action = None
        self.hq_downscale_action = None
        self.fast_view_action = None
        self.bg_black_action = None
        self.bg_white_action = None
        self.fullscreen_action = None
        self.refresh_explorer_action = None
        self.convert_webp_action = None
        self.cache_size = 20
        self.decode_full = False
        # Use engine's default decoding strategy to avoid duplicate initialization
        self.decoding_strategy: DecodingStrategy = self.engine.get_decoding_strategy()

        self.canvas = ImageCanvas(self)

        # QML POC setup
        self.app_controller = AppController(self.engine, self)
        # Connect engine's image_ready to AppController for QML push
        self.engine.image_ready.connect(self.app_controller.on_engine_image_ready)

        # Use QQuickWidget (a QWidget) rather than QQuickView (a QWindow) so that
        # ownership/destruction is tied to the main window. This avoids intermittent
        # access violations at interpreter shutdown in the test environment.
        self.quick_view = None
        self.quick_widget = QQuickWidget()
        self.quick_widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)

        # QML loads asynchronously; ensure we force focus only once the root object exists.
        def _on_qml_status_changed(status) -> None:
            try:
                if status != QQuickWidget.Status.Ready:
                    return
                root = self.quick_widget.rootObject()
                if root is None:
                    return
                # Wire the controller via an explicit root property to avoid
                # relying on unqualified context properties in QML.
                with contextlib.suppress(Exception):
                    root.setProperty("appController", self.app_controller)
                if hasattr(root, "forceActiveFocus"):
                    root.forceActiveFocus()
                elif hasattr(root, "setProperty"):
                    root.setProperty("focus", True)
            except Exception:
                return

        with contextlib.suppress(Exception):
            self.quick_widget.statusChanged.connect(_on_qml_status_changed)
            self._qml_status_handler = _on_qml_status_changed

        # Register the custom image provider for "image://engine/..." URLs
        # NOTE: Do NOT share a single provider instance across multiple engines.
        self._qml_image_provider = EngineImageProvider(self.engine)
        self.quick_widget.engine().addImageProvider("engine", self._qml_image_provider)

        qml_path = _BASE_DIR / "qml" / "ViewerPage.qml"
        self.quick_widget.setSource(QUrl.fromLocalFile(str(qml_path)))

        # Preserve the public attribute used by explorer mode + tests.
        self.qml_container = self.quick_widget
        self.qml_container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.qml_container.setMinimumSize(1, 1)

        # Initially use the QML container for the POC
        self.setCentralWidget(self.qml_container)

        # In some environments (notably offscreen/headless test runs), QML Keys
        # handlers may not reliably receive key events. Forward the keybindings
        # on the container widget to the existing viewer actions.
        self._install_qml_key_filter()

        # Create status builder and menus so actions (e.g., fullscreen) exist for tests
        self._status_builder = StatusOverlayBuilder(self)
        build_menus(self)

        # Initialize settings (path, manager, defaults)
        self._initialize_settings()

        # View window reference (for QML top-level view mode)
        self._view_window = None
        self._current_app = None

        # Ensure settings exist early so startup code can read them
        try:
            self._initialize_settings()
        except Exception as ex:
            # Initialize fallback settings manager to avoid startup crashes
            logger.error("_initialize_settings failed: %s", ex)

            class _FallbackSettings:
                def __init__(self):
                    self.data = {}

                def get(self, k, default=None):
                    return default

                @property
                def fast_view_enabled(self):
                    return False

                def determine_startup_background(self):
                    return "dark"

            self._settings_path = abs_path_str(_BASE_DIR / "settings.json")
            self._settings_manager = _FallbackSettings()
            self._settings = self._settings_manager.data
            self._bg_color = self._settings_manager.determine_startup_background()

    def _initialize_settings(self) -> None:
        """Initialize settings path, manager, and UI defaults.

        This is safe to call multiple times; it will set up `_settings_manager`,
        `_settings` and `_bg_color` and apply decoding strategy defaults.
        """
        try:
            app_config = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
            if app_config:
                cfg_dir = Path(app_config) / "image_viewer"
                os.makedirs(cfg_dir, exist_ok=True)
                # Use project path normalization (OS-native absolute path)
                self._settings_path = abs_path_str(cfg_dir / "settings.json")
            else:
                self._settings_path = abs_path_str(_BASE_DIR / "settings.json")
        except Exception:
            self._settings_path = abs_path_str(_BASE_DIR / "settings.json")

        self._settings_manager = SettingsManager(self._settings_path)
        self._settings: dict[str, Any] = self._settings_manager.data
        self._bg_color = self._settings_manager.determine_startup_background()
        _logger.debug("Settings loaded from: %s", self._settings_path)

        # Apply decoding strategy preference from settings
        try:
            if self._settings_manager.fast_view_enabled:
                self.decoding_strategy = self.engine.get_fast_strategy()
            else:
                self.decoding_strategy = self.engine.get_decoding_strategy()
        except Exception:
            # Keep whatever decoding strategy was previously set
            pass

    def open_view_window(self, start_path: str | None = None) -> None:
        """Open an application-modal top-level window that hosts the QML Viewer."""
        dlg = getattr(self, "_view_window", None)
        if dlg is not None:
            with contextlib.suppress(Exception):
                dlg.raise_()
                dlg.activateWindow()
            return

        qml_path = _BASE_DIR / "qml" / "ViewerPage.qml"

        dlg, qwidget = self._create_view_dialog(qml_path)
        self._install_view_key_filter(dlg)

        # Mark as a separate top-level view so closing it does not alter
        # the main window's saved/explorer state unexpectedly.
        dlg._qml_widget = qwidget
        dlg._is_separate_view = True
        # Also keep a debug name for easier diagnostics
        dlg._debug_name = "separate_view_dialog"
        self._view_window = dlg
        dlg.destroyed.connect(lambda _: setattr(self, "_view_window", None))

        # Optionally set initial path
        if start_path:
            with contextlib.suppress(Exception):
                self.app_controller.setCurrentPathSlot(start_path)

    def _create_view_dialog(self, qml_path: Path):
        """Create and show the view dialog and return (dialog, qml_container_widget).

        NOTE: We intentionally use QQuickView + QWidget.createWindowContainer here
        instead of QQuickWidget. QQuickWidget has proven prone to native crashes
        (access violations) in the pytest offscreen environment on Windows when
        created/destroyed repeatedly across tests.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("Image Viewer - View Mode")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)

        quick_view = QQuickView()

        # Ensure we wire the controller via a root property once QML is ready.
        def _on_view_status_changed(status) -> None:
            if status != QQuickView.Status.Ready:
                return
            root = quick_view.rootObject()
            if root is None:
                return
            with contextlib.suppress(Exception):
                root.setProperty("appController", self.app_controller)

        # NOTE: Do NOT share a single provider instance across multiple engines.
        # Keep a strong Python ref tied to the dialog lifetime.
        dlg._qml_image_provider = EngineImageProvider(self.engine)  # type: ignore[attr-defined]
        quick_view.engine().addImageProvider("engine", dlg._qml_image_provider)  # type: ignore[attr-defined]
        with contextlib.suppress(Exception):
            quick_view.statusChanged.connect(_on_view_status_changed)
            dlg._qml_status_handler = _on_view_status_changed  # type: ignore[attr-defined]
        quick_view.setSource(QUrl.fromLocalFile(str(qml_path)))

        container = QWidget.createWindowContainer(quick_view, dlg)
        container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        container.setMinimumSize(1, 1)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(container)
        dlg.setLayout(layout)

        # Show non-blocking but application-modal
        dlg.show()
        container.setFocus()

        # Keep references for teardown
        dlg._quick_view = quick_view  # type: ignore[attr-defined]

        # Ensure root QML item receives focus (and controller wiring) as well
        with contextlib.suppress(Exception):
            root = quick_view.rootObject()
            if root is not None and hasattr(root, "setProperty"):
                root.setProperty("appController", self.app_controller)
                root.setProperty("focus", True)

        return dlg, container

    def _install_view_key_filter(self, dlg) -> None:
        """Attach an event filter to close the dialog on Enter/Escape.

        The filter closes the dialog directly (deferred) instead of invoking
        `ImageViewer.close_view_window()` so the main window's state is never
        toggled as a side-effect of handling the key event.
        """

        # Capture the ImageViewer instance for use inside the filter
        _viewer_self = self

        class ViewWindowKeyFilter(QObject):
            def __init__(self, qdialog):
                super().__init__(qdialog)
                self._dlg = qdialog
                self._close_scheduled = False

            def eventFilter(self, watched, event):
                if event.type() != QEvent.Type.KeyPress:
                    return False
                if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
                    return False

                # Immediately hide the dialog for instant user feedback and
                # schedule cleanup asynchronously so teardown work doesn't
                # impact perceived responsiveness.
                with contextlib.suppress(Exception):
                    self._dlg.hide()

                from PySide6.QtCore import QTimer  # noqa: PLC0415

                def _cleanup_later() -> None:
                    # Perform GUI-thread cleanup later; this keeps the UI
                    # responsive while resources are released.
                    with contextlib.suppress(Exception):
                        _viewer_self._teardown_qwidget(self._dlg)
                    with contextlib.suppress(Exception):
                        self._dlg.close()
                    with contextlib.suppress(Exception):
                        self._dlg.deleteLater()
                    # Clear reference on the viewer if it still points to this dlg
                    with contextlib.suppress(Exception):
                        if getattr(_viewer_self, "_view_window", None) is self._dlg:
                            _viewer_self._view_window = None

                # Schedule the cleanup on the event loop (background to the user)
                QTimer.singleShot(0, _cleanup_later)

                return True

        with contextlib.suppress(Exception):
            key_filter = ViewWindowKeyFilter(dlg)
            dlg.installEventFilter(key_filter)
            dlg._key_filter = key_filter
            # Also install on the QML container so keys pressed while QML has
            # focus still trigger close behavior.
            try:
                qcont = getattr(dlg, "_qml_widget", None)
                if qcont is not None:
                    qcont.installEventFilter(key_filter)
            except Exception:
                pass

    def _install_qml_key_filter(self) -> None:
        """Forward key events from the embedded QML widget to viewer actions.

        In offscreen/headless test runs, QML Keys handlers are not always
        reliable. This keeps keyboard navigation functional (and testable)
        without requiring QML focus semantics to work perfectly.
        """

        container = getattr(self, "qml_container", None)
        if container is None:
            return

        class _QmlKeyForwarder(QObject):
            def __init__(self, viewer):
                super().__init__(viewer)
                self._viewer = viewer

            def eventFilter(self, watched, event):
                if event.type() != QEvent.Type.KeyPress:
                    return False

                action_map = {
                    Qt.Key.Key_Right: self._viewer.next_image,
                    Qt.Key.Key_Left: self._viewer.prev_image,
                    Qt.Key.Key_End: self._viewer.last_image,
                    Qt.Key.Key_Home: self._viewer.first_image,
                    Qt.Key.Key_F11: self._viewer.toggle_fullscreen,
                }
                action = action_map.get(event.key())
                if action is None:
                    return False
                action()
                return True

        with contextlib.suppress(Exception):
            self._qml_key_filter = _QmlKeyForwarder(self)
            container.installEventFilter(self._qml_key_filter)

    def close_view_window(self) -> None:
        """Close the view window if it exists and cleanup.

        If the view window is a separate top-level dialog (created via
        `open_view_window`), we intentionally *do not* call
        `_restore_after_view_closed()` because that method mutates the
        main window's saved geometry/state and can unexpectedly resize
        the main window when a transient top-level view dialog is closed.
        """
        dlg = getattr(self, "_view_window", None)
        if dlg is None:
            return

        is_separate = getattr(dlg, "_is_separate_view", False)

        self._teardown_qwidget(dlg)
        self._close_and_cleanup(dlg)
        self._view_window = None

        # Only restore main-window view state when the closed view is not a
        # transient separate dialog. This preserves the main window geometry
        # when users open a top-level view window and then close it.
        if not is_separate:
            self._restore_after_view_closed()

    def _teardown_qwidget(self, dlg) -> None:
        """Attempt to clear QQuickWidget source to free resources."""
        with contextlib.suppress(Exception):
            quick_view = getattr(dlg, "_quick_view", None)
            if quick_view is not None and hasattr(quick_view, "setSource"):
                quick_view.setSource(QUrl())
            if quick_view is not None and hasattr(quick_view, "deleteLater"):
                quick_view.deleteLater()

    def _close_and_cleanup(self, dlg) -> None:
        """Close and schedule deletion of the dialog."""
        with contextlib.suppress(Exception):
            dlg.close()
            dlg.deleteLater()

    def _restore_after_view_closed(self) -> None:
        """Restore viewer state after the view window has been closed."""
        # Hover drawer menu for View mode
        # Parent the hover menu to the canvas viewport so the menu is above the image
        # and we can receive mouse move events from the viewport.
        self._hover_menu = HoverDrawerMenu(self.canvas.viewport())
        self._hover_menu.crop_requested.connect(self._on_hover_crop_requested)
        # Ensure viewport generates mouse move events even when no button is pressed
        try:
            self.canvas.viewport().setMouseTracking(True)
            self.canvas.viewport().installEventFilter(self)
        except Exception:
            pass

        # Use per-user application config directory for settings by default.
        # This avoids writing to protected installation directories like
        # Program Files and follows platform conventions (AppData on Windows).
        try:
            app_config = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
            if app_config:
                cfg_dir = Path(app_config) / "image_viewer"
                os.makedirs(cfg_dir, exist_ok=True)
                # Use project path normalization (OS-native absolute path)
                self._settings_path = abs_path_str(cfg_dir / "settings.json")
            else:
                self._settings_path = abs_path_str(_BASE_DIR / "settings.json")
        except Exception:
            self._settings_path = abs_path_str(_BASE_DIR / "settings.json")
        self._settings_manager = SettingsManager(self._settings_path)
        self._settings: dict[str, Any] = self._settings_manager.data
        self._bg_color = self._settings_manager.determine_startup_background()
        _logger.debug("Settings loaded from: %s", self._settings_path)

        # Apply hover menu hide delay from settings
        try:
            if hasattr(self, "_hover_menu") and hasattr(self, "_settings_manager"):
                delay = int(self._settings_manager.get("hover_hide_delay", 120))
                self._hover_menu.set_hide_delay(delay)
        except Exception:
            pass

        if self._settings_manager.fast_view_enabled:
            self.decoding_strategy = self.engine.get_fast_strategy()
        else:
            self.decoding_strategy = self.engine.get_decoding_strategy()

        build_menus(self)
        self._status_builder = StatusOverlayBuilder(self)
        self._apply_background()

        # Load press zoom multiplier from settings
        try:
            zoom_val = float(self._settings_manager.get("press_zoom_multiplier"))
            self.set_press_zoom_multiplier(zoom_val)
        except Exception:
            pass

        self._overlay_title = ""
        self._overlay_info = "Ready"
        self._convert_dialog: WebPConvertDialog | None = None

        # Folder listing is produced asynchronously by the engine.
        # Track pending folder opens so we can auto-display once files arrive.
        self._pending_open_folder: str | None = None
        self._pending_open_saw_empty: bool = False
        # When switching from Explorer -> View, keep the selected file so we can
        # restore a correct index once the async file list arrives.
        self._pending_select_path: str | None = None

    def _get_file_dimensions(self, file_path: str) -> tuple[int | None, int | None]:
        """Get the original dimensions of a file via engine (no direct file access)."""
        try:
            # Get dimensions only through engine - UI should never access files directly
            if hasattr(self, "engine") and self.engine:
                res = self.engine.get_resolution(file_path)
                if res is not None:
                    return res
            # If not in cache, return None - engine should have preloaded all metadata
        except Exception:
            pass
        return None, None

    def _get_decoded_dimensions(self) -> tuple[int | None, int | None]:
        """Get the most recently decoded dimensions."""
        try:
            return getattr(self, "_current_decoded_size", (None, None))
        except Exception:
            return None, None

    def _calculate_scale(self, width: int | None, height: int | None) -> float | None:
        """Calculate the scale ratio."""
        try:
            if not width or not height or width <= 0 or height <= 0:
                return None

            viewport_width = self.canvas.viewport().width()
            viewport_height = self.canvas.viewport().height()

            if self.canvas.is_fit():
                scale_x = max(1, viewport_width) / width
                scale_y = max(1, viewport_height) / height
                return min(scale_x, scale_y)
            else:
                return float(self.canvas._zoom)
        except Exception:
            return None

    def _build_status_parts(self) -> list[str]:
        return self._status_builder.build_parts()

    def _update_status(self, extra: str = ""):
        """Update the status overlay text."""
        if self.current_index == -1 or not self.image_files:
            self._overlay_title = ""
            self._overlay_info = "Ready · Press Ctrl+O to open folder"
            if hasattr(self, "canvas"):
                self.canvas.viewport().update()
            return

        fname = os.path.basename(self.image_files[self.current_index])
        idx = self.current_index + 1
        total = len(self.image_files)

        # Create status parts
        parts = self._build_status_parts()

        if extra:
            parts.append(str(extra))

        # Set overlay information
        self._overlay_title = fname
        if parts:
            self._overlay_info = f"({idx}/{total})  {'  '.join(parts)}"
        else:
            self._overlay_info = f"({idx}/{total})"

        if hasattr(self, "canvas"):
            self.canvas.viewport().update()

    def _load_last_parent_dir(self):
        # Pull start folder from settings manager
        val = self._settings_manager.last_parent_dir
        if val:
            return val
        try:
            return os.path.expanduser("~")
        except Exception:
            return os.getcwd()

    def _save_last_parent_dir(self, parent_dir: str):
        try:
            parent_dir = abs_dir_str(parent_dir)
            self._save_settings_key("last_parent_dir", parent_dir)
            logger.debug("last_parent_dir saved: %s", parent_dir)
        except Exception as e:
            logger.error("failed to save last_parent_dir: %s", e)

    def _save_settings_key(self, key: str, value):
        try:
            self._settings_manager.set(key, value)
        except Exception as e:
            logger.error("settings save failed: key=%s, error=%s", key, e)

    def _open_folder_in_explorer_mode(self, dir_path: str) -> None:
        """Handle folder opening when in Explorer mode."""
        try:
            self.open_folder_at(dir_path)
        except Exception:
            return
        tree = getattr(self.explorer_state, "_explorer_tree", None)
        grid = getattr(self.explorer_state, "_explorer_grid", None)
        with contextlib.suppress(Exception):
            if tree is not None:
                tree.set_root_path(dir_path)
        with contextlib.suppress(Exception):
            if grid is not None:
                grid.load_folder(dir_path)
                grid.resume_pending_thumbnails()

        # Save last opened folder so Open dialog starts here next time
        with contextlib.suppress(Exception):
            self._save_last_parent_dir(dir_path)

    def _open_folder_in_view_mode(self, dir_path: str) -> None:
        """Handle folder opening when in View mode."""
        # Reset state and clear canvas
        self.current_index = -1
        with contextlib.suppress(Exception):
            empty = QPixmap(1, 1)
            empty.fill(Qt.GlobalColor.transparent)
            self.canvas.set_pixmap(empty)

        # Open folder via engine
        if not self.engine.open_folder(dir_path):
            self._update_status("Failed to open folder.")
            return

        # Folder listing is async; wait for engine.folder_changed.
        with contextlib.suppress(Exception):
            dir_path = abs_dir_str(dir_path)
        self._pending_open_folder = dir_path
        self._pending_open_saw_empty = False
        self._save_last_parent_dir(dir_path)
        self._update_status("Scanning...")

        logger.debug("folder open started (async): %s", dir_path)

    def open_folder(self) -> None:
        """Open folder dialog and load images."""
        start_dir = self._load_last_parent_dir() or os.path.expanduser("~")
        dir_path = QFileDialog.getExistingDirectory(self, "Open Folder", start_dir)
        if not dir_path:
            return

        is_explorer_mode = not getattr(self.explorer_state, "view_mode", True)
        if is_explorer_mode:
            self._open_folder_in_explorer_mode(dir_path)
        else:
            self._open_folder_in_view_mode(dir_path)

    def display_image(self) -> None:
        """Display the current image."""
        with busy_cursor():
            if self.current_index == -1:
                return
            image_path = self.image_files[self.current_index]
            self.setWindowTitle(f"Image Viewer - {os.path.basename(image_path)}")
            logger.debug("display_image: idx=%s path=%s", self.current_index, image_path)

            # Update QML POC path BEFORE engine request to let QML decide if it needs cached version
            if hasattr(self, "app_controller"):
                self.app_controller.setCurrentPathSlot(image_path)

            # Calculate target size for FastView strategy

            target_size = None
            if isinstance(self.decoding_strategy, FastViewStrategy):
                screen = self.windowHandle().screen() if self.windowHandle() else QApplication.primaryScreen()
                if screen is not None:
                    size = screen.size()
                    tw, th = self.decoding_strategy.get_target_size(int(size.width()), int(size.height()))
                    target_size = (tw, th)

            # Check cache first
            cached = self.engine.get_cached_pixmap(image_path)
            if cached is not None:
                logger.debug("display_image: cache-hit path=%s", image_path)
                self.update_pixmap(cached)
                return

            # Request decode via engine
            self._update_status("Loading...")
            self.engine.request_decode(image_path, target_size)

    def open_convert_dialog(self) -> None:
        try:
            # Get current folder from shared model
            start_folder = None
            try:
                current_folder = self.engine.get_current_folder()
                if current_folder:
                    start_folder = Path(current_folder)
            except Exception:
                start_folder = None

            if self._convert_dialog is None:
                self._convert_dialog = WebPConvertDialog(self, start_folder=start_folder)
            elif start_folder:
                self._convert_dialog.folder_edit.setText(str(start_folder))
            self._convert_dialog.show()
            self._convert_dialog.raise_()
            self._convert_dialog.activateWindow()
        except Exception as ex:
            logger.error("failed to open convert dialog: %s", ex)

    def refresh_explorer(self) -> None:
        """Refresh explorer view by reloading current folder."""
        try:
            if getattr(self.explorer_state, "view_mode", True):
                return
            grid = getattr(self.explorer_state, "_explorer_grid", None)
            tree = getattr(self.explorer_state, "_explorer_tree", None)
            current_folder = None
            if grid and hasattr(grid, "get_current_folder"):
                current_folder = grid.get_current_folder()
            if not current_folder:
                try:
                    if tree and hasattr(tree, "current_path"):
                        current_folder = tree.current_path()
                except Exception:
                    current_folder = None
            if not current_folder:
                return
            if tree and hasattr(tree, "set_root_path"):
                with contextlib.suppress(Exception):
                    tree.set_root_path(current_folder)
            if grid:
                with contextlib.suppress(Exception):
                    grid.load_folder(current_folder)
                    grid.resume_pending_thumbnails()
            logger.debug("explorer refreshed: %s", current_folder)
        except Exception as ex:
            logger.debug("refresh_explorer failed: %s", ex)

    def _on_engine_image_ready(self, path: str, pixmap: QPixmap, error) -> None:
        """Handle image decoded signal from ImageEngine.

        Args:
            path: Image file path
            pixmap: Decoded QPixmap (empty if error)
            error: Error message or None
        """
        try:
            if path not in self.image_files:
                logger.debug("_on_engine_image_ready drop: path not in image_files: %s", path)
                return
        except Exception:
            pass

        if error:
            logger.error("decode error for %s: %s", path, error)
            try:
                base = os.path.basename(path)
            except Exception:
                base = path
            self._overlay_info = f"Load failed: {base} - {error}"
            if hasattr(self, "canvas"):
                self.canvas.viewport().update()
            return

        if pixmap and not pixmap.isNull():
            # Store decoded size for status display
            if path == self.image_files[self.current_index]:
                with contextlib.suppress(Exception):
                    self._current_decoded_size = (pixmap.width(), pixmap.height())

            # Skip screen update during trim preview
            if getattr(self.trim_state, "in_preview", False):
                logger.debug("skipping screen update during trim preview")
                return

            # Update canvas if this is the current image
            if path == self.image_files[self.current_index]:
                self.update_pixmap(pixmap)

    def _on_engine_folder_changed(self, path: str, files: list[str]) -> None:  # noqa: PLR0912, PLR0915
        """Handle folder changed signal from ImageEngine.

        Args:
            path: Folder path
            files: List of image file paths
        """
        try:
            prev_len = len(self.image_files) if getattr(self, "image_files", None) is not None else -1
            prev_idx = getattr(self, "current_index", None)
            pending_sel = getattr(self, "_pending_select_path", None)

            # Get current file before update
            current_file = None
            if self.current_index >= 0 and self.current_index < len(self.image_files):
                current_file = self.image_files[self.current_index]

            logger.debug(
                "folder_changed: path=%s files=%d (prev_len=%s prev_idx=%s current_file=%s pending_select=%s)",
                path,
                len(files),
                prev_len,
                prev_idx,
                current_file,
                pending_sel,
            )

            # Update file list
            self.image_files = files

            # Restore current index if file still exists
            if current_file and current_file in files:
                self.current_index = files.index(current_file)
            elif self.current_index >= len(files):
                self.current_index = max(0, len(files) - 1) if files else -1

            # Update status display
            if self.current_index >= 0:
                self._update_status()

            logger.debug("folder changed in view mode: %d files, current_index=%d", len(files), self.current_index)

            # If a selection was made from Explorer while the engine list was
            # still loading, resolve it now so navigation/prefetch works.
            try:
                pending = getattr(self, "_pending_select_path", None)
                if pending and files and pending in files:
                    if self.current_index != files.index(pending):
                        logger.debug(
                            "folder_changed: resolve pending_select -> idx %d/%d: %s",
                            files.index(pending),
                            len(files),
                            pending,
                        )
                        self.current_index = files.index(pending)
                        self.display_image()
                    # Warm neighboring decodes once we have the full list.
                    self.maintain_decode_window(back=0, ahead=5)
                    self._pending_select_path = None
            except Exception:
                pass

            # If we initiated a folder open in View mode, auto-display once the
            # async file list arrives. Note: the engine emits an immediate empty
            # list first; ignore that until we get real files.
            pending_open = getattr(self, "_pending_open_folder", None)
            if pending_open and path == pending_open:
                # Use safe accessors in case the attribute initialization hasn't
                # completed yet (race during startup or when signals arrive early).
                pending_saw_empty = getattr(self, "_pending_open_saw_empty", False)
                if files and self.current_index == -1:
                    self.current_index = 0
                    with contextlib.suppress(Exception):
                        self.setWindowTitle(f"Image Viewer - {os.path.basename(files[self.current_index])}")
                    self.display_image()
                    self.maintain_decode_window(back=0, ahead=5)

                    with contextlib.suppress(Exception):
                        if getattr(self.explorer_state, "view_mode", True):
                            self.enter_fullscreen()

                    # Clear pending state
                    try:
                        self._pending_open_folder = None
                        self._pending_open_saw_empty = False
                    except Exception:
                        pass
                elif not files:
                    # The engine emits an immediate empty list first. Treat the
                    # second empty (after the directory worker completes) as
                    # "no images" and clear the pending state.
                    if not pending_saw_empty:
                        with contextlib.suppress(Exception):
                            self._pending_open_saw_empty = True
                    else:
                        self.setWindowTitle("Image Viewer")
                        self._update_status("No images found.")
                        try:
                            self._pending_open_folder = None
                            self._pending_open_saw_empty = False
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("_on_engine_folder_changed failed: %s", e)

    def on_image_ready(self, path, image_data, error):
        """Legacy handler - kept for backward compatibility."""
        # Now handled by _on_engine_image_ready via engine.image_ready signal
        logger.debug("on_image_ready (legacy): path=%s error=%s", path, error)

    def update_pixmap(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            self.canvas.set_pixmap(pixmap)
            # The status is constructed from internal logic, so just call update without extra info
            self._update_status()
        else:
            self._update_status("Image load failed")

    def keyPressEvent(self, event) -> None:
        """Handle key press events."""
        key = event.key()

        # F5 refreshes explorer, F11 fullscreen
        if key == Qt.Key.Key_F5:
            self.refresh_explorer()
            return
        elif key == Qt.Key.Key_F11:
            self.toggle_fullscreen()
            return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Enter key: toggle between View and Explorer mode
            is_view_mode = getattr(self.explorer_state, "view_mode", True)
            if is_view_mode:
                # In View Mode: 1) Exit fullscreen first, 2) Then switch to Explorer Mode
                if self.isFullScreen():
                    self.exit_fullscreen()
                self.toggle_view_mode()
                return
            else:
                # In Explorer Mode: let the grid handle Enter (for image activation)
                # Don't consume the event, pass it to child widgets
                super().keyPressEvent(event)
                return

        # Other keys require images to be loaded
        # Centralized key dispatching via ui_shortcuts
        # This handles View vs Explorer mode logic (e.g. allowing Arrows in Explorer)
        try:
            if ui_shortcuts.dispatch_key_event(self, event):
                event.accept()
                return
        except Exception as ex:
            _logger.error("key dispatch failed: %s", ex)

        with contextlib.suppress(Exception):
            super().keyPressEvent(event)

    def maintain_decode_window(self, back: int = 3, ahead: int = 5) -> None:
        """Prefetch images around the current index."""
        if not self.image_files:
            return
        n = len(self.image_files)
        i = self.current_index

        # Compare list/index state with engine cache to pinpoint divergence.
        try:
            current_path = self.image_files[i] if 0 <= i < n else (self.image_files[0] if self.image_files else None)
            eng_files = self.engine.get_image_files() if hasattr(self, "engine") and self.engine else []
            eng_n = len(eng_files)
            eng_i = self.engine.get_file_index(current_path) if current_path else -1
        except Exception:
            current_path = self.image_files[0] if self.image_files else None
            eng_n = -1
            eng_i = -1

        if n == 1 or (eng_n >= 0 and eng_n != n) or (current_path and eng_i not in (-1, i)):
            logger.debug(
                "prefetch state: viewer(n=%d idx=%s) engine(n=%s idx=%s) path=%s",
                n,
                i,
                eng_n,
                eng_i,
                current_path,
            )
        start = max(0, i - back)
        end = min(n - 1, i + ahead)
        logger.debug("prefetch window: idx=%s range=[%s..%s]", i, start, end)

        # Calculate target size for FastView strategy
        target_size = None
        fast_view_action = getattr(self, "fast_view_action", None)
        fast_view_enabled = bool(fast_view_action and fast_view_action.isChecked())
        if fast_view_enabled and not self.decode_full:
            screen = self.windowHandle().screen() if self.windowHandle() else QApplication.primaryScreen()
            if screen is not None:
                sz = screen.size()
                target_size = (int(sz.width()), int(sz.height()))

        # Collect paths to prefetch (skip current image - already requested by display_image)
        current_path = self.image_files[i] if 0 <= i < n else None
        paths_to_prefetch = []
        for idx in range(start, end + 1):
            path = self.image_files[idx]
            # Skip current image (already requested) and cached images
            if path == current_path:
                continue
            if not self.engine.is_cached(path):
                paths_to_prefetch.append(path)

        if paths_to_prefetch:
            logger.debug("prefetch %d images, target=%s", len(paths_to_prefetch), target_size)
            self.engine.prefetch(paths_to_prefetch, target_size)

    def _unignore_decode_window(self, back: int = 1, ahead: int = 4) -> None:
        try:
            if not self.image_files:
                return
            n = len(self.image_files)
            i = self.current_index
            start = max(0, i - back)
            end = min(n - 1, i + ahead)
            for idx in range(start, end + 1):
                try:
                    p = self.image_files[idx]
                    self.engine.unignore_path(p)
                except Exception:
                    pass
        except Exception:
            pass

    # Navigation
    def next_image(self):
        if not self.image_files:
            return
        n = len(self.image_files)
        if self.current_index >= n - 1:
            # If it's the last image, do nothing (no wraparound)
            return
        # If the current image is still loading, ignore the input
        if self.current_index >= 0 and self.current_index < len(self.image_files):
            current_path = self.image_files[self.current_index]
            if not self.engine.is_cached(current_path):
                logger.debug("next_image: current image still loading, ignoring input")
                return
        with busy_cursor():
            self.current_index += 1
            self.display_image()
            self.maintain_decode_window()

    def prev_image(self):
        if not self.image_files:
            return
        if self.current_index <= 0:
            # If it's the first image, do nothing (no wraparound)
            return
        # If the current image is still loading, ignore the input
        if self.current_index >= 0 and self.current_index < len(self.image_files):
            current_path = self.image_files[self.current_index]
            if not self.engine.is_cached(current_path):
                logger.debug("prev_image: current image still loading, ignoring input")
                return
        with busy_cursor():
            self.current_index -= 1
            self.display_image()
            self.maintain_decode_window()

    def first_image(self):
        if not self.image_files:
            return
        self.current_index = 0
        self.display_image()
        self.maintain_decode_window()

    def last_image(self):
        if not self.image_files:
            return
        self.current_index = len(self.image_files) - 1
        self.display_image()
        self.maintain_decode_window()

    def delete_current_file(self):
        """Delete the current file to trash."""
        delete_current_file(self)

    def closeEvent(self, event):
        self.engine.shutdown()
        event.accept()

    def resizeEvent(self, event):
        """Handle window resize to update hover menu position."""
        super().resizeEvent(event)
        if hasattr(self, "_hover_menu"):
            # Use viewport size for hover menu positioning when parented to the viewport
            try:
                vw = self.canvas.viewport().width()
                vh = self.canvas.viewport().height()
            except Exception:
                vw = event.size().width()
                vh = event.size().height()
            try:
                prev = getattr(self, "_hover_menu_parent_size", None)
                if prev == (vw, vh):
                    return
                self._hover_menu_parent_size = (vw, vh)
            except Exception:
                pass
            self._hover_menu.set_parent_size(vw, vh)
            _logger.debug("hover menu position updated: %dx%d", vw, vh)

    def mouseMoveEvent(self, event):
        """Handle mouse move to show/hide hover menu in View mode."""
        super().mouseMoveEvent(event)

        # Only show hover menu in View mode
        if hasattr(self, "explorer_state") and not self.explorer_state.view_mode:
            return

        # Forward main window mouse move handling to hover menu as a fallback (in case
        # the viewport doesn't install an event filter). If the canvas consumes events
        # we rely on the eventFilter installed on the viewport.
        if hasattr(self, "_hover_menu"):
            try:
                pos = event.position().toPoint()
            except Exception:
                pos = event.pos()
            self._hover_menu.check_hover_zone(pos.x(), pos.y(), self.rect())

    def eventFilter(self, obj, event):
        """Intercept mouse move events from the canvas viewport and show/hide
        the hover menu accordingly."""
        try:
            if event.type() == QEvent.MouseMove and hasattr(self, "_hover_menu"):
                # Only show hover menu in View mode
                if hasattr(self, "explorer_state") and not self.explorer_state.view_mode:
                    return super().eventFilter(obj, event)

                # Map event pos (viewport coords) to viewport-local QPoint
                try:
                    pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                except Exception:
                    pos = event.pos() if hasattr(event, "pos") else None

                if pos is not None:
                    # If hover menu is parented to the viewport, use viewport rect
                    parent_rect = obj.rect() if hasattr(obj, "rect") else self.rect()
                    self._hover_menu.check_hover_zone(pos.x(), pos.y(), parent_rect)
        except Exception:
            pass
        return super().eventFilter(obj, event)

    # View commands
    def toggle_fit(self):
        self.choose_fit()

    def zoom_by(self, factor: float):
        self.canvas.zoom_by(factor)
        if hasattr(self, "app_controller"):
            self.app_controller._set_zoom(self.canvas._zoom)

    def reset_zoom(self):
        self.canvas.reset_zoom()
        if hasattr(self, "app_controller"):
            self.app_controller._set_zoom(1.0)

    def choose_fit(self):
        self.canvas._preset_mode = "fit"
        if hasattr(self, "fit_action"):
            self.fit_action.setChecked(True)
        if hasattr(self, "actual_action"):
            self.actual_action.setChecked(False)
        self.canvas.apply_current_view()
        if hasattr(self, "app_controller"):
            self.app_controller._set_fit_mode(True)

    def choose_actual(self):
        self.canvas._preset_mode = "actual"
        self.canvas._zoom = 1.0
        if hasattr(self, "fit_action"):
            self.fit_action.setChecked(False)
        if hasattr(self, "actual_action"):
            self.actual_action.setChecked(True)
        self.canvas.apply_current_view()
        if hasattr(self, "app_controller"):
            self.app_controller._set_fit_mode(False)
            self.app_controller._set_zoom(1.0)

    def toggle_hq_downscale(self):
        if hasattr(self, "hq_downscale_action"):
            enabled = self.hq_downscale_action.isChecked()
            self.canvas._hq_downscale = enabled
            self.canvas._hq_pixmap = None
            if self.canvas.is_fit():
                self.canvas.apply_current_view()

    # Toggle decoding strategy: thumbnail mode on/off (checked = thumbnail)
    def toggle_fast_view(self):
        is_fast_view = self.fast_view_action.isChecked()
        # Switch strategy
        if is_fast_view:
            self.decoding_strategy = self.engine.get_fast_strategy()
            logger.debug("switched to FastViewStrategy (reused instance)")
        else:
            self.decoding_strategy = self.engine.get_full_strategy()
            logger.debug("switched to FullStrategy (reused instance)")

        # Update engine's strategy
        self.engine.set_decoding_strategy(self.decoding_strategy)

        # Save setting: only save the thumbnail mode state
        self._save_settings_key("fast_view_enabled", is_fast_view)

        # Enable/disable high-quality downscale option based on the strategy
        self.hq_downscale_action.setEnabled(self.decoding_strategy.supports_hq_downscale())
        if not self.decoding_strategy.supports_hq_downscale() and self.hq_downscale_action.isChecked():
            self.hq_downscale_action.setChecked(False)
            self.canvas._hq_downscale = False

        # Clear the current cache to allow immediate comparison with the new strategy
        self.engine.clear_cache()
        # Redisplay the current image and re-request prefetching
        self.display_image()
        self.maintain_decode_window()

    def snap_to_global_view(self):
        if hasattr(self, "fit_action") and self.fit_action.isChecked():
            self.choose_fit()
        else:
            self.choose_actual()

    # Set/sync background color
    def _apply_background(self):
        with contextlib.suppress(Exception):
            self.canvas.setBackgroundBrush(self._bg_color)

    def _sync_bg_checks(self):
        try:
            is_black = self._bg_color == QColor(0, 0, 0)
            is_white = self._bg_color == QColor(255, 255, 255)
            if hasattr(self, "bg_black_action"):
                self.bg_black_action.setChecked(bool(is_black))
            if hasattr(self, "bg_white_action"):
                self.bg_white_action.setChecked(bool(is_white))
        except Exception:
            pass

    def _save_bg_color(self):
        try:
            c = self._bg_color
            hexcol = f"#{c.red():02x}{c.green():02x}{c.blue():02x}"
            self._save_settings_key("background_color", hexcol)
        except Exception:
            pass

    def set_background_qcolor(self, color: QColor):
        try:
            if not isinstance(color, QColor):
                return
            if not color.isValid():
                return
            self._bg_color = color
            self._apply_background()
            self._sync_bg_checks()
            self._save_bg_color()
        except Exception:
            pass

    def choose_background_custom(self):
        try:
            col = QColorDialog.getColor(self._bg_color, self, "Select Background Color")
        except Exception:
            col = None
        if col and col.isValid():
            self.set_background_qcolor(col)

    # Settings: Press zoom multiplier
    def set_press_zoom_multiplier(self, value: float):
        try:
            v = float(value)
        except Exception:
            return
        v = max(0.1, min(v, 10.0))
        self.canvas._press_zoom_multiplier = v
        self._save_settings_key("press_zoom_multiplier", v)

    def prompt_custom_multiplier(self):
        try:
            pass
        except Exception:
            return
        current = getattr(self.canvas, "_press_zoom_multiplier", 3.0)
        val, ok = QInputDialog.getDouble(
            self,
            "Press Zoom Multiplier",
            "Enter multiplier (1.0-10.0):",
            float(current),
            0.1,
            10.0,
            1,
        )
        if ok:
            self.set_press_zoom_multiplier(val)

    # ---------------- Trim Workflow ----------------
    def start_trim_workflow(self):
        """Start the trim workflow."""
        start_trim_workflow(self)

    def enter_fullscreen(self):
        # Save current geometry before entering fullscreen
        self._normal_geometry = self.geometry()
        self.menuBar().setVisible(False)
        self.showFullScreen()
        if hasattr(self, "fullscreen_action"):
            self.fullscreen_action.setChecked(True)
        self.canvas.apply_current_view()

    def exit_fullscreen(self):
        # Exit fullscreen and restore previous geometry
        self.showNormal()
        if hasattr(self, "_normal_geometry") and not self._normal_geometry.isNull():
            self.setGeometry(self._normal_geometry)
        self.menuBar().setVisible(True)
        if hasattr(self, "fullscreen_action"):
            self.fullscreen_action.setChecked(False)
        self.canvas.apply_current_view()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()

    # --------------- Explorer Mode ----------------
    def toggle_view_mode(self) -> None:
        """Toggle between View Mode <-> Explorer Mode"""
        toggle_view_mode(self)

    def _update_ui_for_mode(self) -> None:
        """Reconfigure UI based on the current mode"""
        from image_viewer.explorer_mode_operations import _update_ui_for_mode  # noqa: PLC0415

        _update_ui_for_mode(self)

        # Show/hide hover menu based on mode
        if hasattr(self, "_hover_menu"):
            if self.explorer_state.view_mode:  # View mode (view_mode = True)
                try:
                    vw = self.canvas.viewport().width()
                    vh = self.canvas.viewport().height()
                except Exception:
                    vw = self.width()
                    vh = self.height()
                self._hover_menu.show()
                self._hover_menu.set_parent_size(vw, vh)
                self._hover_menu.raise_()
                _logger.debug("hover menu shown for View mode")
            else:  # Explorer mode (view_mode = False)
                self._hover_menu.hide()
                _logger.debug("hover menu hidden for Explorer mode")

    def _setup_view_mode(self) -> None:
        """Set up View Mode: show only the central canvas"""
        from image_viewer.explorer_mode_operations import _setup_view_mode  # noqa: PLC0415

        _setup_view_mode(self)

    def open_settings(self):
        try:
            dlg = SettingsDialog(self, self)
            dlg.exec()
        except Exception as e:
            logger.error("failed to open settings: %s", e)

    def apply_thumbnail_settings(
        self,
        width: int | None = None,
        height: int | None = None,
        hspacing: int | None = None,
    ) -> None:
        with busy_cursor():
            try:
                grid = getattr(self.explorer_state, "_explorer_grid", None)
                if width is not None:
                    self._save_settings_key("thumbnail_width", int(width))
                if height is not None:
                    self._save_settings_key("thumbnail_height", int(height))
                if grid:
                    try:
                        if hasattr(grid, "set_thumbnail_size_wh") and (width is not None or height is not None):
                            w = int(width if width is not None else grid.get_thumbnail_size()[0])
                            h = int(height if height is not None else grid.get_thumbnail_size()[1])
                            grid.set_thumbnail_size_wh(w, h)
                        elif hasattr(grid, "set_thumbnail_size") and width is not None and height is not None:
                            # Fallback: square
                            grid.set_thumbnail_size(int(width))
                    except Exception:
                        pass
                if hspacing is not None:
                    self._save_settings_key("thumbnail_hspacing", int(hspacing))
                    if grid and hasattr(grid, "set_horizontal_spacing"):
                        grid.set_horizontal_spacing(int(hspacing))
            except Exception as e:
                logger.debug("apply_thumbnail_settings failed: %s", e)

    def _on_explorer_folder_selected(self, folder_path: str, grid) -> None:
        """Handle folder selection in the explorer."""
        from image_viewer.explorer_mode_operations import _on_explorer_folder_selected  # noqa: PLC0415

        _on_explorer_folder_selected(self, folder_path, grid)

    def _on_explorer_image_selected(self, image_path: str) -> None:
        """Handle image selection in the explorer."""
        from image_viewer.explorer_mode_operations import _on_explorer_image_selected  # noqa: PLC0415

        _on_explorer_image_selected(self, image_path)

    def _on_hover_crop_requested(self) -> None:
        """Handle crop request from hover menu."""
        try:
            from image_viewer.crop.crop_operations import start_crop_workflow  # noqa: PLC0415

            start_crop_workflow(self)
        except Exception as ex:
            _logger.error("Crop workflow failed: %s", ex, exc_info=True)

    def open_folder_at(self, folder_path: str) -> None:
        """Open a specific folder directly (used in explorer mode)."""
        open_folder_at(self, folder_path)

    def apply_theme(self, theme: str, font_size: int = 10) -> None:
        """Apply a theme and save to settings.

        Args:
            theme: Theme name ("dark" or "light")
            font_size: Base font size in points (default: 10)
        """
        try:
            from image_viewer.styles import apply_theme  # noqa: PLC0415

            app = getattr(self, "_current_app", None)
            if app is None:
                from PySide6.QtWidgets import QApplication  # noqa: PLC0415

                app = QApplication.instance()

            if app:
                apply_theme(app, theme, font_size)
                self._save_settings_key("theme", theme)
                self._save_settings_key("font_size", int(font_size))
                logger.debug("theme applied: %s, font_size=%d", theme, font_size)
        except Exception as e:
            logger.error("failed to apply theme: %s", e)


def run(argv: list[str] | None = None) -> int:
    """Application entrypoint (packaging-friendly)."""
    import argparse  # noqa: PLC0415
    from multiprocessing import freeze_support  # noqa: PLC0415

    freeze_support()
    _logger.debug("Application startup initiated")

    if argv is None:
        argv = sys.argv

    # Parse optional start path (image file or folder) after logging options were
    # already stripped out by _apply_cli_logging_options().
    try:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("start_path", nargs="?", help="Image file or folder to open")
        args, _ = parser.parse_known_args(argv[1:])
        start_path_str = args.start_path
    except Exception:
        start_path_str = None

    start_path = Path(start_path_str) if start_path_str else None
    if start_path:
        _logger.debug("Start path provided: %s", start_path)

    # QML-first application shell:
    # - QML owns the UI and navigation.
    # - Python owns AppController + ImageEngine and exposes state/commands.
    app = QApplication(argv)

    # Apply theme from settings (default: dark). Keep this QWidget-side so QML
    # inherits palette + base font.
    from image_viewer.path_utils import abs_path_str  # noqa: PLC0415
    from image_viewer.settings_manager import SettingsManager  # noqa: PLC0415
    from image_viewer.styles import apply_theme  # noqa: PLC0415

    settings_path = abs_path_str(_BASE_DIR / "settings.json")
    settings = SettingsManager(settings_path)
    theme = settings.get("theme", "dark")
    font_size = int(settings.get("font_size", 10))
    apply_theme(app, theme, font_size)
    _logger.debug("Theme applied: %s, font_size=%d", theme, font_size)

    from PySide6.QtCore import QUrl  # noqa: PLC0415
    from PySide6.QtQml import QQmlApplicationEngine  # noqa: PLC0415

    from image_viewer.image_engine.engine import ImageEngine  # noqa: PLC0415
    from image_viewer.qml_bridge import AppController  # noqa: PLC0415

    engine = ImageEngine()
    controller = AppController(engine)

    qml_engine = QQmlApplicationEngine()
    qml_engine.addImageProvider("engine", controller.image_provider)
    qml_engine.addImageProvider("thumb", controller.thumb_provider)

    qml_url = QUrl.fromLocalFile(str(_BASE_DIR / "qml" / "App.qml"))
    qml_engine.load(qml_url)
    if not qml_engine.rootObjects():
        _logger.error("Failed to load QML root: %s", qml_url.toString())
        return 1

    root = qml_engine.rootObjects()[0]
    root.setProperty("appController", controller)

    # Startup path behavior:
    # - file: open its folder, select it, enter Viewer page
    # - folder: open it, stay in Explorer page
    if start_path and start_path.exists():
        if start_path.is_file():
            controller._pending_select_path = abs_path_str(start_path)
            controller.openFolder(str(start_path.parent))
            controller._set_view_mode(True)
        elif start_path.is_dir():
            controller.openFolder(str(start_path))
            controller._set_view_mode(False)

    return app.exec()


if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    sys.exit(run())
