from __future__ import annotations

import contextlib
import os
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog

from .logger import get_logger
from .strategy import FastViewStrategy

_logger = get_logger("display_controller")


class DisplayController:
    def __init__(self, viewer):
        self.viewer = viewer

    def open_folder(self) -> None:
        viewer = self.viewer
        try:
            start_dir = viewer._load_last_parent_dir()
        except Exception:
            start_dir = os.path.expanduser("~")
        try:
            dir_path = QFileDialog.getExistingDirectory(
                viewer, "Open Folder", start_dir
            )
        except Exception:
            dir_path = None
        if not dir_path:
            return

        # If currently in Explorer mode, reuse the explorer workflow: open folder,
        # refresh tree/grid, and stop (no automatic fullscreen or image display).
        is_explorer_mode = not getattr(viewer.explorer_state, "view_mode", True)
        if is_explorer_mode:
            try:
                viewer.open_folder_at(dir_path)
            except Exception:
                return
            tree = getattr(viewer.explorer_state, "_explorer_tree", None)
            grid = getattr(viewer.explorer_state, "_explorer_grid", None)
            try:
                if tree is not None:
                    tree.set_root_path(dir_path)
            except Exception:
                pass
            try:
                if grid is not None:
                    grid.load_folder(dir_path)
                    with contextlib.suppress(Exception):
                        grid.resume_pending_thumbnails()
            except Exception:
                pass
            return

        try:
            if hasattr(viewer, "loader"):
                try:
                    viewer.loader._ignored.clear()
                    viewer.loader._pending.clear()
                    if hasattr(viewer.loader, "_latest_id"):
                        viewer.loader._latest_id.clear()
                except Exception:
                    pass
            viewer.pixmap_cache.clear()
            viewer.current_index = -1
            try:
                empty = QPixmap(1, 1)
                empty.fill(Qt.GlobalColor.transparent)
                viewer.canvas.set_pixmap(empty)
            except Exception:
                pass
        except Exception:
            pass

        # Setup QFileSystemModel watcher for auto-reload in View mode
        self._setup_fs_watcher(dir_path)

        # Initial file list load
        self._reload_image_files(dir_path)

        if not viewer.image_files:
            viewer.setWindowTitle("Image Viewer")
            viewer._update_status("No images found.")
            return

        viewer.current_index = 0
        viewer._save_last_parent_dir(dir_path)
        viewer.setWindowTitle(
            f"Image Viewer - {os.path.basename(viewer.image_files[viewer.current_index])}"
        )
        self.display_image()
        self.maintain_decode_window(back=0, ahead=5)
        try:
            if getattr(viewer.explorer_state, "view_mode", True):
                viewer.enter_fullscreen()
        except Exception:
            pass
        _logger.debug(
            "folder opened: %s, images=%d", dir_path, len(viewer.image_files)
        )

    def _setup_fs_watcher(self, dir_path: str) -> None:
        """Setup QFileSystemModel to watch for file changes in View mode."""
        from PySide6.QtWidgets import QFileSystemModel
        viewer = self.viewer
        try:
            # Clean up existing watcher
            if viewer.explorer_state._fs_watcher:
                with contextlib.suppress(Exception):
                    viewer.explorer_state._fs_watcher.directoryLoaded.disconnect()
                viewer.explorer_state._fs_watcher = None

            # Create new watcher
            fs_model = QFileSystemModel()
            fs_model.setRootPath(dir_path)

            # Connect to directory loaded signal for auto-reload
            def _on_dir_changed(path: str):
                if path == dir_path and getattr(viewer.explorer_state, "view_mode", True):
                    _logger.debug("fs watcher detected change: %s", path)
                    self._reload_image_files(dir_path, preserve_current=True)

            fs_model.directoryLoaded.connect(_on_dir_changed)
            viewer.explorer_state._fs_watcher = fs_model
            _logger.debug("fs watcher setup: %s", dir_path)
        except Exception as e:
            _logger.debug("failed to setup fs watcher: %s", e)

    def _reload_image_files(self, dir_path: str, preserve_current: bool = False) -> None:
        """Reload image file list from directory.

        Args:
            dir_path: Directory path to scan
            preserve_current: If True, try to maintain current image selection
        """
        viewer = self.viewer
        try:
            current_file = None
            if preserve_current and viewer.current_index >= 0 and viewer.current_index < len(viewer.image_files):
                current_file = viewer.image_files[viewer.current_index]

            files = []
            for name in os.listdir(dir_path):
                p = os.path.join(dir_path, name)
                if os.path.isfile(p):
                    lower = name.lower()
                    if lower.endswith(
                        (
                            ".jpg",
                            ".jpeg",
                            ".png",
                            ".bmp",
                            ".gif",
                            ".webp",
                            ".tif",
                            ".tiff",
                        )
                    ):
                        files.append(p)
            files.sort()
            viewer.image_files = files

            # Restore current index if possible
            if preserve_current and current_file:
                if current_file in viewer.image_files:
                    viewer.current_index = viewer.image_files.index(current_file)
                elif viewer.current_index >= len(viewer.image_files):
                    viewer.current_index = max(0, len(viewer.image_files) - 1)
                # Update display if we're viewing
                if viewer.current_index >= 0 and viewer.current_index < len(viewer.image_files):
                    viewer._update_status()

            _logger.debug("image files reloaded: %d files", len(viewer.image_files))
        except Exception as e:
            _logger.error("failed to reload image files: %s", e)

    def display_image(self) -> None:
        viewer = self.viewer
        if viewer.current_index == -1:
            return
        image_path = viewer.image_files[viewer.current_index]
        viewer.setWindowTitle(f"Image Viewer - {os.path.basename(image_path)}")
        _logger.debug("display_image: idx=%s path=%s", viewer.current_index, image_path)

        if image_path in viewer.pixmap_cache:
            pix = viewer.pixmap_cache.pop(image_path)
            viewer.pixmap_cache[image_path] = pix
            _logger.debug(
                "display_image: cache-hit(full) path=%s cache_size=%s",
                image_path,
                len(viewer.pixmap_cache),
            )
            viewer.update_pixmap(pix)
            return

        viewer._update_status("Loading...")
        target_w = target_h = None
        if isinstance(viewer.decoding_strategy, FastViewStrategy):
            screen = (
                viewer.windowHandle().screen()
                if viewer.windowHandle()
                else QApplication.primaryScreen()
            )
            if screen is not None:
                size = screen.size()
                target_w, target_h = viewer.decoding_strategy.get_target_size(
                    int(size.width()), int(size.height())
                )

        viewer.loader.request_load(image_path, target_w, target_h, "both")

    def on_image_ready(self, path: str, image_data: Any | None, error: Any | None) -> None:
        viewer = self.viewer
        try:
            if path not in viewer.image_files:
                _logger.debug("on_image_ready drop: path not in image_files: %s", path)
                return
        except Exception:
            pass
        if error:
            _logger.error("decode error for %s: %s", path, error)
            try:
                base = os.path.basename(path)
            except Exception:
                base = path
            viewer._overlay_info = f"Load failed: {base} - {error}"
            if hasattr(viewer, "canvas"):
                viewer.canvas.viewport().update()
            return

        if image_data is not None:
            try:
                height, width, _ = image_data.shape
                bytes_per_line = 3 * width
                q_image = QImage(
                    image_data.data,
                    width,
                    height,
                    bytes_per_line,
                    QImage.Format.Format_RGB888,
                )
                pixmap = QPixmap.fromImage(q_image)
            except Exception:
                _logger.debug("Failed to build pixmap for %s", path)
                return

            if path == viewer.image_files[viewer.current_index]:
                with contextlib.suppress(Exception):
                    viewer._current_decoded_size = (width, height)

            if path in viewer.pixmap_cache:
                viewer.pixmap_cache.pop(path)
            viewer.pixmap_cache[path] = pixmap
            if len(viewer.pixmap_cache) > viewer.cache_size:
                viewer.pixmap_cache.popitem(last=False)
            _logger.debug("on_image_ready cache_size=%s", len(viewer.pixmap_cache))

            if getattr(viewer.trim_state, "in_preview", False):
                _logger.debug("skipping screen update during trim preview")
                return
            if path == viewer.image_files[viewer.current_index]:
                viewer.update_pixmap(pixmap)

    def maintain_decode_window(self, back: int = 3, ahead: int = 5) -> None:
        viewer = self.viewer
        if not viewer.image_files:
            return
        n = len(viewer.image_files)
        i = viewer.current_index
        start = max(0, i - back)
        end = min(n - 1, i + ahead)
        _logger.debug("prefetch window: idx=%s range=[%s..%s]", i, start, end)
        for idx in range(start, end + 1):
            path = viewer.image_files[idx]
            if path not in viewer.pixmap_cache:
                target_w = target_h = None
                fast_view_action = getattr(viewer, "fast_view_action", None)
                fast_view_enabled = bool(
                    fast_view_action and fast_view_action.isChecked()
                )
                if fast_view_enabled and not viewer.decode_full:
                    screen = (
                        viewer.windowHandle().screen()
                        if viewer.windowHandle()
                        else QApplication.primaryScreen()
                    )
                    if screen is not None:
                        sz = screen.size()
                        target_w = int(sz.width())
                        target_h = int(sz.height())
                _logger.debug(
                    "prefetch request: path=%s target=(%s,%s)", path, target_w, target_h
                )
                viewer.loader.request_load(path, target_w, target_h, "both")
