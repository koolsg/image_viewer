"""Explorer mode operations: folder/image selection, UI setup, file operations."""

import contextlib
import os
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QStackedWidget

from .file_operations import (
    copy_file,
    move_file,
    send_to_recycle_bin,
    show_delete_confirmation,
)
from .path_utils import abs_dir, abs_dir_str, abs_path, abs_path_str

# Re-export for backward compatibility (used by ui_explorer_grid)
__all__ = [
    "copy_files_to_clipboard",
    "cut_files_to_clipboard",
    "delete_files_to_recycle_bin",
    "paste_files",
]
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


def _setup_explorer_mode(viewer) -> None:  # noqa: PLR0912, PLR0915
    """Setup Explorer Mode: tree + grid layout.

    Args:
        viewer: The ImageViewer instance
    """
    try:
        # Restore previous Explorer window state (fullscreen should already be exited)
        if hasattr(viewer.explorer_state, "_saved_geometry") and hasattr(viewer.explorer_state, "_saved_maximized"):
            if viewer.explorer_state._saved_maximized:
                viewer.showMaximized()
                _logger.debug("restored explorer window state: maximized")
            else:
                viewer.setGeometry(viewer.explorer_state._saved_geometry)
                _logger.debug("restored explorer window state: normal geometry")

        from image_viewer.ui_explorer_grid import ThumbnailGridWidget  # noqa: PLC0415
        from image_viewer.ui_explorer_tree import FolderTreeWidget  # noqa: PLC0415

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
                        grid.resume_pending_thumbnails()
            except Exception:
                pass
            stacked_widget.setCurrentIndex(1)
            _logger.debug("switched to existing Explorer page")
            return

        # Initial creation path
        from PySide6.QtWidgets import QSplitter  # noqa: PLC0415

        splitter = QSplitter(Qt.Orientation.Horizontal)
        # Style will be applied by theme system
        splitter.setObjectName("explorerSplitter")
        splitter.setHandleWidth(1)
        tree = FolderTreeWidget()

        # Engine-backed explorer model (no QFileSystemModel)
        grid = ThumbnailGridWidget(engine=viewer.engine)

        # Apply settings
        try:
            if any(
                viewer._settings_manager.has(key) for key in ("thumbnail_width", "thumbnail_height", "thumbnail_size")
            ):
                use_size_only = (
                    viewer._settings_manager.has("thumbnail_size")
                    and not viewer._settings_manager.has("thumbnail_width")
                    and not viewer._settings_manager.has("thumbnail_height")
                )
                size = int(viewer._settings_manager.get("thumbnail_size"))
                width = size if use_size_only else int(viewer._settings_manager.get("thumbnail_width"))
                height = size if use_size_only else int(viewer._settings_manager.get("thumbnail_height"))
                if hasattr(grid, "set_thumbnail_size_wh"):
                    grid.set_thumbnail_size_wh(width, height)
                elif hasattr(grid, "set_thumbnail_size"):
                    grid.set_thumbnail_size(int(width))
            if viewer._settings_manager.has("thumbnail_hspacing"):
                grid.set_horizontal_spacing(int(viewer._settings_manager.get("thumbnail_hspacing")))
        except Exception as e:
            _logger.debug("failed to apply grid settings: %s", e)

        splitter.addWidget(tree)
        splitter.addWidget(grid)
        splitter.setSizes([300, 700])

        # Connect signals
        tree.folder_selected.connect(lambda p: _on_explorer_folder_selected(viewer, p, grid))
        grid.image_selected.connect(lambda p: _on_explorer_image_selected(viewer, p))

        # Add Page 1 and switch to it
        stacked_widget.addWidget(splitter)
        stacked_widget.setCurrentIndex(1)

        viewer.explorer_state._explorer_tree = tree
        viewer.explorer_state._explorer_grid = grid

        # Auto-load current folder from engine
        engine = viewer.engine
        current_folder = engine.get_current_folder()
        if current_folder:
            tree.set_root_path(current_folder)
            grid.load_folder(current_folder)
            with contextlib.suppress(Exception):
                grid.resume_pending_thumbnails()
        elif engine.get_file_count() > 0:
            # Fallback: use first image's parent folder
            first_file = engine.get_file_at_index(0)
            if first_file:
                current_dir = abs_dir_str(first_file)
                tree.set_root_path(current_dir)
                grid.load_folder(current_dir)
                with contextlib.suppress(Exception):
                    grid.resume_pending_thumbnails()

        # Force focus to grid to ensure keyboard navigation works immediately
        grid.setFocus()

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
        _logger.error("failed to load folder in explorer: %s, error=%s", folder_path, e)


def _on_explorer_image_selected(viewer, image_path: str) -> None:  # noqa: PLR0912, PLR0915
    """Handle image selection in explorer.

    Args:
        viewer: The ImageViewer instance
        image_path: Selected image path
    """
    engine = viewer.engine
    try:
        # Correlate logs for a single Explorer activation -> View display cycle.
        try:
            trace_id = int(getattr(viewer, "_trace_select_id", 0)) + 1
        except Exception:
            trace_id = 1
        with contextlib.suppress(Exception):
            viewer._trace_select_id = trace_id

        normalized_path = abs_path_str(image_path)

        # `QAbstractItemView.activated` and selection change can both fire for a
        # single user action. If we're already in View mode and this selection
        # matches the currently displayed file, ignore the duplicate.
        try:
            if viewer.explorer_state.view_mode:
                current_path = None
                if (
                    isinstance(getattr(viewer, "image_files", None), list)
                    and isinstance(getattr(viewer, "current_index", None), int)
                    and 0 <= viewer.current_index < len(viewer.image_files)
                ):
                    current_path = viewer.image_files[viewer.current_index]
                if current_path == normalized_path:
                    _logger.debug(
                        "explorer select[%s]: ignored duplicate selection for current image",
                        trace_id,
                    )
                    return
        except Exception:
            pass
        target_folder = abs_dir_str(normalized_path)
        _logger.debug(
            "explorer select[%s]: raw=%s norm=%s target_folder=%s",
            trace_id,
            image_path,
            normalized_path,
            target_folder,
        )
        with contextlib.suppress(Exception):
            cur_folder = engine.get_current_folder()
            _logger.debug("explorer select[%s]: engine.cur_folder=%s", trace_id, cur_folder)
            if cur_folder and abs_dir_str(cur_folder) != target_folder:
                _logger.debug("explorer select: switching folder via open_folder_at: %s", target_folder)
                open_folder_at(viewer, target_folder)
            elif not cur_folder:
                open_folder_at(viewer, target_folder)

        # Record the user's selection so View mode can restore correct index
        # once the async folder listing arrives.
        with contextlib.suppress(Exception):
            viewer._pending_select_path = normalized_path
            _logger.debug("explorer select[%s]: set pending_select=%s", trace_id, normalized_path)

        # If the engine already has the full file list for this folder, use it
        # immediately so navigation/prefetch works right away.
        files = []
        with contextlib.suppress(Exception):
            files = engine.get_image_files() or []

        _logger.debug(
            "explorer select[%s]: engine.get_image_files len=%d contains_selected=%s",
            trace_id,
            len(files),
            bool(files and normalized_path in files),
        )

        if files and normalized_path in files:
            viewer.image_files = list(files)
            viewer.current_index = files.index(normalized_path)
            _logger.debug(
                "explorer select[%s]: using engine list; current_index=%d/%d",
                trace_id,
                viewer.current_index,
                len(viewer.image_files),
            )
        else:
            # Fallback: display immediately using a minimal list. If the model
            # root path already points at this folder, the directory worker will
            # publish the full list soon and `_on_engine_folder_changed` will
            # resolve `viewer._pending_select_path`.
            viewer.image_files = [normalized_path]
            viewer.current_index = 0
            _logger.debug(
                "explorer select[%s]: fallback single-item list; will rely on folder_changed to restore index",
                trace_id,
            )

        # Switch to View Mode and display the image
        if not viewer.explorer_state.view_mode:
            viewer.explorer_state.view_mode = True
            # Only call the main viewer's method which will handle both UI and hover menu
            if hasattr(viewer, "_update_ui_for_mode"):
                viewer._update_ui_for_mode()
            else:
                # Fallback to the old function if method doesn't exist
                _update_ui_for_mode(viewer)

        # Clear canvas and show loading state before displaying the selected image
        if hasattr(viewer, "canvas") and viewer.canvas is not None:
            try:
                # Create a blank pixmap to clear old image
                blank = QPixmap(1, 1)
                blank.fill(Qt.GlobalColor.black)
                viewer.canvas.set_pixmap(blank)
                viewer._update_status("Loading...")
            except Exception:
                pass

        # Display the selected image
        viewer.display_image()

        # Ensure focus for immediate arrow key/shortcut response
        try:
            viewer.setFocus(Qt.FocusReason.OtherFocusReason)
            if hasattr(viewer, "canvas") and viewer.canvas is not None:
                viewer.canvas.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass

        with contextlib.suppress(Exception):
            viewer.enter_fullscreen()
        viewer.maintain_decode_window(back=3, ahead=5)
        _logger.debug("explorer image selected done[%s]: %s", trace_id, normalized_path)
    except Exception as e:
        _logger.error("failed to select image in explorer: %s, error=%s", image_path, e)


def open_folder_at(viewer, folder_path: str) -> None:
    """Open a specific folder directly.

    Args:
        viewer: The ImageViewer instance
        folder_path: Path to the folder to open
    """
    engine = viewer.engine
    try:
        folder_path = abs_dir_str(folder_path)
        if not os.path.isdir(folder_path):
            _logger.warning("not a directory: %s", folder_path)
            return

        # Reset state
        viewer.current_index = -1

        # Open folder via engine (clears caches, sets root path)
        if not engine.open_folder(folder_path):
            viewer._update_status("Failed to open folder.")
            return

        # Folder listing is async; rely on engine.folder_changed to populate
        # viewer.image_files. Track this open so View mode can auto-display.
        with contextlib.suppress(Exception):
            viewer._pending_open_folder = folder_path
            viewer._pending_open_saw_empty = False
        viewer._save_last_parent_dir(folder_path)
        viewer._update_status("Scanning...")

        _logger.debug("folder open started (async): %s", folder_path)
    except Exception as e:
        _logger.error("failed to open_folder_at: %s, error=%s", folder_path, e)


# ============= Explorer Mode File Operations =============


def _set_files_to_clipboard(paths: list[str], operation: str) -> None:
    """Set file paths to system clipboard (internal helper).

    Args:
        paths: List of file paths
        operation: "copy" or "cut" (for logging)
    """
    try:
        mime = QMimeData()
        urls = [abs_path(p).as_uri() for p in paths]
        mime.setUrls([QUrl(u) for u in urls])
        QGuiApplication.clipboard().setMimeData(mime)
        _logger.debug("%s %d files to clipboard", operation, len(paths))
    except Exception as exc:
        _logger.error("failed to %s to clipboard: %s", operation, exc)


def copy_files_to_clipboard(paths: list[str]) -> None:
    """Copy file paths to system clipboard.

    Args:
        paths: List of file paths to copy
    """
    _set_files_to_clipboard(paths, "copy")


def cut_files_to_clipboard(paths: list[str]) -> None:
    """Cut file paths to system clipboard.

    Args:
        paths: List of file paths to cut
    """
    _set_files_to_clipboard(paths, "cut")


def paste_files(dest_folder: str, clipboard_paths: list[str], mode: str) -> tuple[int, list[str]]:
    """Paste files from clipboard to destination folder.

    Args:
        dest_folder: Destination folder path
        clipboard_paths: List of source file paths
        mode: "copy" or "cut"

    Returns:
        Tuple of (success_count, failed_paths)
    """
    dest_dir = abs_dir(dest_folder)
    if not dest_dir.is_dir():
        _logger.warning("destination is not a directory: %s", dest_folder)
        return 0, clipboard_paths

    success_count = 0
    failed_paths = []

    for src in clipboard_paths:
        try:
            src_path = abs_path(src)
            if not src_path.exists():
                failed_paths.append(src)
                continue

            if mode == "cut":
                move_file(str(src_path), str(dest_dir))
            else:
                copy_file(str(src_path), str(dest_dir))

            success_count += 1
        except Exception as exc:
            _logger.warning("paste failed for %s: %s", src, exc)
            failed_paths.append(src)

    _logger.debug(
        "paste complete: %d success, %d failed, mode=%s",
        success_count,
        len(failed_paths),
        mode,
    )
    return success_count, failed_paths


def delete_files_to_recycle_bin(paths: list[str], parent_widget=None) -> tuple[int, list[str]]:
    """Delete files to recycle bin with confirmation.

    Args:
        paths: List of file paths to delete
        parent_widget: Parent widget for confirmation dialog (optional)

    Returns:
        Tuple of (success_count, failed_paths)
    """
    if not paths:
        return 0, []

    # Confirmation dialog
    if parent_widget:
        if len(paths) == 1:
            # For single selections, show the filename for clarity (match View Mode)
            fname = str(Path(paths[0]).name)
            title = "Delete File"
            text = "Delete this file?"
            info = f"{fname}\n\nIt will be moved to Recycle Bin."
        else:
            title = "Delete Files"
            text = f"Delete {len(paths)} item(s)?"
            info = "They will be moved to Recycle Bin when possible."

        if not show_delete_confirmation(parent_widget, title, text, info):
            _logger.debug("delete cancelled by user")
            return 0, paths

    success_count = 0
    failed_paths = []

    for path in paths:
        try:
            send_to_recycle_bin(path)
            success_count += 1
        except Exception as exc:
            _logger.warning("delete failed for %s: %s", path, exc)
            failed_paths.append(path)

    _logger.debug("delete complete: %d success, %d failed", success_count, len(failed_paths))
    return success_count, failed_paths
