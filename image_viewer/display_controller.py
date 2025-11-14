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

        try:
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
        except Exception as e:
            _logger.error("failed to open_folder: %s, error=%s", dir_path, e)

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
