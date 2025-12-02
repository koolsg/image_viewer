"""Explorer mode operations: folder/image selection, UI setup."""

import contextlib
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStackedWidget

from .logger import get_logger
from .ui_canvas import ImageCanvas

_logger = get_logger("explorer_mode")


def toggle_view_mode(viewer) -> None:
    """Toggle between View Mode and Explorer Mode.

    Args:
        viewer: The ImageViewer instance
    """
    viewer.explorer_state.view_mode = not viewer.explorer_state.view_mode
    _update_ui_for_mode(viewer)
    _logger.debug("view_mode toggled: %s", viewer.explorer_state.view_mode)


def _update_ui_for_mode(viewer) -> None:
    """Rebuild UI based on current mode.

    Args:
        viewer: The ImageViewer instance
    """
    if viewer.explorer_state.view_mode:
        _setup_view_mode(viewer)
    else:
        _setup_explorer_mode(viewer)

    # Sync menu
    if hasattr(viewer, "explorer_mode_action"):
        viewer.explorer_mode_action.setChecked(not viewer.explorer_state.view_mode)


def _setup_view_mode(viewer) -> None:
    """Setup View Mode: show only canvas in fullscreen.

    Args:
        viewer: The ImageViewer instance
    """
    try:
        # Save current window state before switching to View Mode
        if not viewer.isFullScreen():
            viewer.explorer_state._saved_geometry = viewer.geometry()
            viewer.explorer_state._saved_maximized = viewer.isMaximized()
            _logger.debug("saved explorer window state: maximized=%s", viewer.explorer_state._saved_maximized)

        # Disconnect Explorer Grid loader (to prevent UI load after jump)
        try:
            grid = getattr(viewer.explorer_state, "_explorer_grid", None)
            if grid is not None:
                grid.set_loader(None)
        except Exception:
            pass

        current_widget = viewer.centralWidget()

        # Check if we're using the stacked widget architecture
        if isinstance(current_widget, QStackedWidget):
            # Good: stacked widget exists, just switch to canvas page (Index 0)
            try:
                current_widget.setCurrentIndex(0)
                _logger.debug("switched to View Mode via stacked widget")
            except Exception as e:
                _logger.warning("failed to switch stacked widget page: %s", e)
        else:
            # Fallback: manually set canvas as central widget
            try:
                # Verify canvas is valid
                if viewer.canvas:
                    viewer.canvas.parent()  # This will raise if C++ object deleted

                    # Set canvas as central widget
                    viewer.setCentralWidget(viewer.canvas)
                    viewer.canvas.show()
                    _logger.debug("switched to View Mode with existing canvas")
            except RuntimeError as e:
                # Canvas C++ object is deleted
                _logger.warning("canvas C++ object is invalid: %s", e)
                try:
                    viewer.canvas = ImageCanvas(viewer)
                    viewer.setCentralWidget(viewer.canvas)
                    _logger.warning("canvas recreated and set as central widget")
                except Exception as e2:
                    _logger.error("failed to recreate canvas: %s", e2)
            except Exception as e:
                _logger.warning("failed to set canvas as central widget: %s", e)
                try:
                    viewer.canvas = ImageCanvas(viewer)
                    viewer.setCentralWidget(viewer.canvas)
                    _logger.warning("canvas recreated and set as central widget")
                except Exception as e2:
                    _logger.error("failed to recreate canvas: %s", e2)

    except Exception as e:
        _logger.error("failed to setup view mode: %s", e)


def _setup_explorer_mode(viewer) -> None:
    """Setup Explorer Mode: tree + grid layout.

    Args:
        viewer: The ImageViewer instance
    """
    try:
        # Restore saved window state if switching from fullscreen View Mode
        if viewer.isFullScreen():
            viewer.showNormal()
            viewer.menuBar().setVisible(True)
            if hasattr(viewer, "fullscreen_action"):
                viewer.fullscreen_action.setChecked(False)

        # Restore previous Explorer window state
        if hasattr(viewer.explorer_state, "_saved_geometry") and hasattr(viewer.explorer_state, "_saved_maximized"):
            if viewer.explorer_state._saved_maximized:
                viewer.showMaximized()
                _logger.debug("restored explorer window state: maximized")
            else:
                viewer.setGeometry(viewer.explorer_state._saved_geometry)
                _logger.debug("restored explorer window state: normal geometry")

        from image_viewer.ui_explorer_grid import ThumbnailGridWidget
        from image_viewer.ui_explorer_tree import FolderTreeWidget

        current_widget = viewer.centralWidget()
        stacked_widget = None

        if isinstance(current_widget, QStackedWidget):
            stacked_widget = current_widget
            _logger.debug("reusing existing stacked widget")
        else:
            stacked_widget = QStackedWidget()
            if isinstance(current_widget, ImageCanvas):
                viewer.takeCentralWidget()
                stacked_widget.addWidget(current_widget)
            elif viewer.canvas:
                stacked_widget.addWidget(viewer.canvas)
            viewer.setCentralWidget(stacked_widget)
            _logger.debug("created stacked widget for mode switching")

        # If Page 1 already exists, reuse it (preserve grid/tree/thumbnail cache)
        if stacked_widget.count() > 1:
            try:
                stacked_widget.widget(1)
                # If there's an existing grid reference, just reconnect the loader
                grid = getattr(viewer.explorer_state, "_explorer_grid", None)
                if grid is not None:
                    with contextlib.suppress(Exception):
                        grid.set_loader(viewer.thumb_loader)
                        grid.resume_pending_thumbnails()
            except Exception:
                pass
            stacked_widget.setCurrentIndex(1)
            _logger.debug("switched to existing Explorer page")
            return

        # Initial creation path
        from PySide6.QtWidgets import QSplitter

        splitter = QSplitter(Qt.Orientation.Horizontal)
        tree = FolderTreeWidget()
        grid = ThumbnailGridWidget()
        try:
            cache_name = str(viewer._settings_manager.get("thumbnail_cache_name", "image_viewer_thumbs"))
            grid.set_disk_cache_folder_name(cache_name)
        except Exception:
            pass

        try:
            grid.set_loader(viewer.thumb_loader)
        except Exception as ex:
            _logger.debug("failed to attach thumb_loader: %s", ex)

        # Apply settings
        try:
            if any(
                viewer._settings_manager.has(key)
                for key in ("thumbnail_width", "thumbnail_height", "thumbnail_size")
            ):
                use_size_only = (
                    viewer._settings_manager.has("thumbnail_size")
                    and not viewer._settings_manager.has("thumbnail_width")
                    and not viewer._settings_manager.has("thumbnail_height")
                )
                size = int(viewer._settings_manager.get("thumbnail_size"))
                width = (
                    size
                    if use_size_only
                    else int(viewer._settings_manager.get("thumbnail_width"))
                )
                height = (
                    size
                    if use_size_only
                    else int(viewer._settings_manager.get("thumbnail_height"))
                )
                if hasattr(grid, "set_thumbnail_size_wh"):
                    grid.set_thumbnail_size_wh(width, height)
                elif hasattr(grid, "set_thumbnail_size"):
                    grid.set_thumbnail_size(int(width))
            if viewer._settings_manager.has("thumbnail_hspacing"):
                grid.set_horizontal_spacing(
                    int(viewer._settings_manager.get("thumbnail_hspacing"))
                )
        except Exception as e:
            _logger.debug("failed to apply grid settings: %s", e)

        splitter.addWidget(tree)
        splitter.addWidget(grid)
        splitter.setSizes([300, 700])

        # Connect signals
        tree.folder_selected.connect(
            lambda p: _on_explorer_folder_selected(viewer, p, grid)
        )
        grid.image_selected.connect(lambda p: _on_explorer_image_selected(viewer, p))

        # Add Page 1 and switch to it
        stacked_widget.addWidget(splitter)
        stacked_widget.setCurrentIndex(1)

        viewer.explorer_state._explorer_tree = tree
        viewer.explorer_state._explorer_grid = grid

        # Auto-load current folder
        if viewer.image_files:
            current_dir = str(Path(viewer.image_files[0]).parent)
            tree.set_root_path(current_dir)
            grid.load_folder(current_dir)
            with contextlib.suppress(Exception):
                grid.resume_pending_thumbnails()

        _logger.debug("switched to Explorer Mode")
    except Exception as e:
        _logger.error("failed to setup explorer mode: %s", e)


def _on_explorer_folder_selected(viewer, folder_path: str, grid) -> None:
    """Handle folder selection in explorer.

    Args:
        viewer: The ImageViewer instance
        folder_path: Selected folder path
        grid: The thumbnail grid widget
    """
    try:
        grid.load_folder(folder_path)
        _logger.debug("explorer folder selected: %s", folder_path)
    except Exception as e:
        _logger.error(
            "failed to load folder in explorer: %s, error=%s", folder_path, e
        )


def _on_explorer_image_selected(viewer, image_path: str) -> None:
    """Handle image selection in explorer.

    Args:
        viewer: The ImageViewer instance
        image_path: Selected image path
    """
    try:
        # Switch to View Mode and display the image
        if not viewer.explorer_state.view_mode:
            viewer.explorer_state.view_mode = True
            _update_ui_for_mode(viewer)

        # Ensure focus for immediate arrow key/shortcut response
        try:
            viewer.setFocus(Qt.FocusReason.OtherFocusReason)
            if hasattr(viewer, "canvas") and viewer.canvas is not None:
                viewer.canvas.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass

        # Calculate jump distance (for debugging)
        try:
            cur_idx = viewer.current_index
            tgt_idx = (
                viewer.image_files.index(image_path)
                if image_path in viewer.image_files
                else None
            )
            _logger.debug(
                "explorer select: cur=%s tgt=%s path=%s",
                cur_idx,
                tgt_idx,
                image_path,
            )
        except Exception:
            pass

        # Display image by image_path (normalize paths for comparison)
        normalized_path = str(Path(image_path).resolve())
        normalized_files = [str(Path(f).resolve()) for f in viewer.image_files]

        if normalized_path in normalized_files:
            viewer.current_index = normalized_files.index(normalized_path)
        else:
            # If it's a new folder, open it first
            new_folder = str(Path(image_path).parent)
            _logger.debug("explorer select: open_folder_at %s", new_folder)
            open_folder_at(viewer, new_folder)
            # Re-normalize after opening folder
            normalized_path = str(Path(image_path).resolve())
            normalized_files = [str(Path(f).resolve()) for f in viewer.image_files]
            if normalized_path in normalized_files:
                viewer.current_index = normalized_files.index(normalized_path)

        _logger.debug(
            "explorer select display: idx=%s path=%s",
            viewer.current_index,
            image_path,
        )
        viewer.display_image()
        with contextlib.suppress(Exception):
            viewer.enter_fullscreen()
        # Prevent excessive prefetching right after switching
        viewer.maintain_decode_window(back=0, ahead=1)
        _logger.debug("explorer image selected done: %s", image_path)
    except Exception as e:
        _logger.error(
            "failed to select image in explorer: %s, error=%s", image_path, e
        )


def open_folder_at(viewer, folder_path: str) -> None:
    """Open a specific folder directly.

    Args:
        viewer: The ImageViewer instance
        folder_path: Path to the folder to open
    """
    try:
        if not os.path.isdir(folder_path):
            _logger.warning("not a directory: %s", folder_path)
            return

        # Clear session state: Reset pending/ignore lists for both Viewer and Thumbnail loaders
        try:
            if hasattr(viewer, "loader"):
                viewer.loader._ignored.clear()
                viewer.loader._pending.clear()
                if hasattr(viewer.loader, "_latest_id"):
                    viewer.loader._latest_id.clear()
        except Exception:
            pass
        try:
            if hasattr(viewer, "thumb_loader") and viewer.thumb_loader is not None:
                viewer.thumb_loader._ignored.clear()
                viewer.thumb_loader._pending.clear()
                if hasattr(viewer.thumb_loader, "_latest_id"):
                    viewer.thumb_loader._latest_id.clear()
        except Exception:
            pass

        viewer.pixmap_cache.clear()
        viewer.current_index = -1

        # Rebuild image list
        files = []
        for name in os.listdir(folder_path):
            p = os.path.join(folder_path, name)
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
        viewer._save_last_parent_dir(folder_path)
        viewer.setWindowTitle(
            f"Image Viewer - {os.path.basename(viewer.image_files[viewer.current_index])}"
        )
        # Lightweight initial prefetch
        viewer.maintain_decode_window(back=0, ahead=3)

        _logger.debug(
            "folder opened: %s, images=%d", folder_path, len(viewer.image_files)
        )
    except Exception as e:
        _logger.error("failed to open_folder_at: %s, error=%s", folder_path, e)
