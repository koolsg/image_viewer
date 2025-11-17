import os
import sys
from collections import OrderedDict
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QInputDialog,
    QMainWindow,
)

# Load from separated modules
_pkg_root = os.path.dirname(os.path.dirname(__file__))
if _pkg_root not in sys.path:
    sys.path.append(_pkg_root)
import contextlib

from image_viewer.decoder import decode_image
from image_viewer.display_controller import DisplayController
from image_viewer.explorer_mode_operations import toggle_view_mode, open_folder_at
from image_viewer.file_operations import delete_current_file
from image_viewer.loader import Loader
from image_viewer.logger import get_logger
from image_viewer.settings_manager import SettingsManager
from image_viewer.status_overlay import StatusOverlayBuilder
from image_viewer.strategy import DecodingStrategy, FastViewStrategy, FullStrategy
from image_viewer.trim_operations import start_trim_workflow
from image_viewer.ui_canvas import ImageCanvas
from image_viewer.ui_menus import build_menus
from image_viewer.ui_settings import SettingsDialog

# --- CLI logging options -----------------------------------------------------
# To prevent Qt from exiting due to unknown options, we preemptively parse
# our own options, reflect them in environment variables (IMAGE_VIEWER_LOG_LEVEL,
# IMAGE_VIEWER_LOG_CATS), and remove them from sys.argv.


def _apply_cli_logging_options() -> None:
    try:
        import argparse
        import os as _os
        import sys as _sys

        parser = argparse.ArgumentParser(description='Image Viewer', add_help=False)
        parser.add_argument('--log-level', help='Set log level')
        parser.add_argument('--log-cats', help='Set log categories')
        args, remaining = parser.parse_known_args()
        if args.log_level:
            _os.environ["IMAGE_VIEWER_LOG_LEVEL"] = args.log_level
        if args.log_cats:
            _os.environ["IMAGE_VIEWER_LOG_CATS"] = args.log_cats
        _sys.argv[:] = [_sys.argv[0]] + remaining
    except Exception:
        # Failing to set up logging should not prevent the app from running.
        pass


_apply_cli_logging_options()
logger = get_logger("main")


class ViewState:
    """Encapsulates view-related state."""

    def __init__(self):
        self.preset_mode: str = "fit"  # "fit" or "actual"
        self.zoom: float = 1.0
        self.hq_downscale: bool = False
        self.press_zoom_multiplier: float = 2.0


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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Viewer")
        #self.resize(1024, 768)

        self.view_state = ViewState()
        self.trim_state = TrimState()
        self.explorer_state = ExplorerState()
        self.image_files: list[str] = []
        self.current_index = -1
        self.pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self.cache_size = 20
        self.decode_full = False
        self.decoding_strategy: DecodingStrategy = FullStrategy()

        self.canvas = ImageCanvas(self)
        self.setCentralWidget(self.canvas)

        self.loader = Loader(decode_image)
        self.loader.image_decoded.connect(self.on_image_ready)
        self.thumb_loader = Loader(decode_image)

        self._settings_path = os.path.join(os.path.dirname(__file__), "settings.json")
        self._settings_manager = SettingsManager(self._settings_path)
        self._settings: dict[str, Any] = self._settings_manager.data
        self._bg_color = self._settings_manager.determine_startup_background()

        if self._settings_manager.fast_view_enabled:
            self.decoding_strategy = FastViewStrategy()
        else:
            self.decoding_strategy = FullStrategy()

        build_menus(self)
        self._status_builder = StatusOverlayBuilder(self)
        self._display_controller = DisplayController(self)
        self._apply_background()

        # Load press zoom multiplier from settings
        try:
            zoom_val = float(self._settings_manager.get("press_zoom_multiplier"))
            self.set_press_zoom_multiplier(zoom_val)
        except Exception:
            pass

        self._overlay_title = ""
        self._overlay_info = "Ready"

    def _get_file_dimensions(self, file_path: str) -> tuple[int | None, int | None]:
        """Get the original dimensions of a file."""
        try:
            reader = QImageReader(file_path)
            size = reader.size()
            if size.width() > 0 and size.height() > 0:
                return size.width(), size.height()
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
            self._save_settings_key("last_parent_dir", parent_dir)
            logger.debug("last_parent_dir saved: %s", parent_dir)
        except Exception as e:
            logger.error("failed to save last_parent_dir: %s", e)

    def _save_settings_key(self, key: str, value):
        try:
            self._settings_manager.set(key, value)
        except Exception as e:
            logger.error("settings save failed: key=%s, error=%s", key, e)

    def open_folder(self):
        self._display_controller.open_folder()

    def display_image(self) -> None:
        self._display_controller.display_image()

    def on_image_ready(self, path, image_data, error):
        self._display_controller.on_image_ready(path, image_data, error)

    def update_pixmap(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            self.canvas.set_pixmap(pixmap)
            # The status is constructed from internal logic, so just call update without extra info
            self._update_status()
        else:
            self._update_status("Image load failed")

    def keyPressEvent(self, event):
        key = event.key()

        # F5 and F11 work even without images
        if key == Qt.Key.Key_F5:
            was_view_mode = getattr(self.explorer_state, "view_mode", True)
            self.toggle_view_mode()
            if was_view_mode:
                with contextlib.suppress(Exception):
                    self.exit_fullscreen()
            return
        elif key == Qt.Key.Key_F11:
            self.toggle_fullscreen()
            return

        # Other keys require images to be loaded
        if not self.image_files:
            super().keyPressEvent(event)
            return

        if key == Qt.Key.Key_Right:
            self.next_image()
        elif key == Qt.Key.Key_Left:
            self.prev_image()
        elif key == Qt.Key.Key_A:
            # Rotate 90 degrees to the left
            with contextlib.suppress(Exception):
                self.canvas.rotate_by(-90)
        elif key == Qt.Key.Key_D:
            # Rotate 90 degrees to the right
            with contextlib.suppress(Exception):
                self.canvas.rotate_by(90)
        elif key == Qt.Key.Key_Delete:
            self.delete_current_file()
        else:
            super().keyPressEvent(event)

    def maintain_decode_window(self, back: int = 3, ahead: int = 5):
        self._display_controller.maintain_decode_window(back, ahead)

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
                    if hasattr(self, "loader"):
                        self.loader.unignore_path(p)
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
            if current_path not in self.pixmap_cache:
                logger.debug("next_image: current image still loading, ignoring input")
                return
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
            if current_path not in self.pixmap_cache:
                logger.debug("prev_image: current image still loading, ignoring input")
                return
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
        self.loader.shutdown()
        event.accept()

    # View commands
    def toggle_fit(self):
        self.choose_fit()

    def zoom_by(self, factor: float):
        self.canvas.zoom_by(factor)

    def reset_zoom(self):
        self.canvas.reset_zoom()

    def choose_fit(self):
        self.canvas._preset_mode = "fit"
        if hasattr(self, "fit_action"):
            self.fit_action.setChecked(True)
        if hasattr(self, "actual_action"):
            self.actual_action.setChecked(False)
        self.canvas.apply_current_view()

    def choose_actual(self):
        self.canvas._preset_mode = "actual"
        self.canvas._zoom = 1.0
        if hasattr(self, "fit_action"):
            self.fit_action.setChecked(False)
        if hasattr(self, "actual_action"):
            self.actual_action.setChecked(True)
        self.canvas.apply_current_view()

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
            self.decoding_strategy = FastViewStrategy()
            logger.debug("switched to FastViewStrategy")
        else:
            self.decoding_strategy = FullStrategy()
            logger.debug("switched to FullStrategy")

        # Save setting: only save the thumbnail mode state
        self._save_settings_key("fast_view_enabled", is_fast_view)

        # Enable/disable high-quality downscale option based on the strategy
        self.hq_downscale_action.setEnabled(
            self.decoding_strategy.supports_hq_downscale()
        )
        if (
            not self.decoding_strategy.supports_hq_downscale()
            and self.hq_downscale_action.isChecked()
        ):
            self.hq_downscale_action.setChecked(False)
            self.canvas._hq_downscale = False

        # Clear the current cache to allow immediate comparison with the new strategy
        self.pixmap_cache.clear()
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
        current = getattr(self.canvas, "_press_zoom_multiplier", 2.0)
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
        from image_viewer.explorer_mode_operations import _update_ui_for_mode
        _update_ui_for_mode(self)

    def _setup_view_mode(self) -> None:
        """Set up View Mode: show only the central canvas"""
        from image_viewer.explorer_mode_operations import _setup_view_mode
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
        try:
            grid = getattr(self.explorer_state, "_explorer_grid", None)
            if width is not None:
                self._save_settings_key("thumbnail_width", int(width))
            if height is not None:
                self._save_settings_key("thumbnail_height", int(height))
            if grid:
                try:
                    if hasattr(grid, "set_thumbnail_size_wh") and (
                        width is not None or height is not None
                    ):
                        w = int(
                            width if width is not None else grid.get_thumbnail_size()[0]
                        )
                        h = int(
                            height
                            if height is not None
                            else grid.get_thumbnail_size()[1]
                        )
                        grid.set_thumbnail_size_wh(w, h)
                    elif (
                        hasattr(grid, "set_thumbnail_size")
                        and width is not None
                        and height is not None
                    ):
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
        from image_viewer.explorer_mode_operations import _on_explorer_folder_selected
        _on_explorer_folder_selected(self, folder_path, grid)

    def _on_explorer_image_selected(self, image_path: str) -> None:
        """Handle image selection in the explorer."""
        from image_viewer.explorer_mode_operations import _on_explorer_image_selected
        _on_explorer_image_selected(self, image_path)

    def open_folder_at(self, folder_path: str) -> None:
        """Open a specific folder directly (used in explorer mode)."""
        open_folder_at(self, folder_path)


if __name__ == "__main__":
    from multiprocessing import freeze_support
    from pathlib import Path
    import argparse

    freeze_support()

    # Parse optional start path (image file or folder) after logging options were
    # already stripped out by _apply_cli_logging_options().
    try:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("start_path", nargs="?", help="Image file or folder to open")
        args, _ = parser.parse_known_args()
        start_path_str = args.start_path
    except Exception:
        start_path_str = None

    start_path = Path(start_path_str) if start_path_str else None

    app = QApplication(sys.argv)
    viewer = ImageViewer()

    # Case 1: started with an image file → open its folder and show that image in
    # View mode, fullscreen.
    if start_path and start_path.is_file():
        folder = start_path.parent
        try:
            viewer.open_folder_at(str(folder))
            target = str(start_path)
            if target in viewer.image_files:
                viewer.current_index = viewer.image_files.index(target)
                viewer.display_image()
        except Exception:
            # Fall back to just showing the window if something goes wrong.
            pass
        viewer.show()
        with contextlib.suppress(Exception):
            viewer.enter_fullscreen()

    # Case 2: started with a folder path → open it and start in Explorer mode.
    elif start_path and start_path.is_dir():
        with contextlib.suppress(Exception):
            viewer.open_folder_at(str(start_path))
        try:
            viewer.explorer_state.view_mode = False
            viewer._update_ui_for_mode()
        except Exception:
            pass
        viewer.showMaximized()

    # Case 3: no path → normal launch: Explorer mode, maximized window.
    else:
        try:
            viewer.explorer_state.view_mode = False
            viewer._update_ui_for_mode()
        except Exception:
            pass
        viewer.showMaximized()

    sys.exit(app.exec())
