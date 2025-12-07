"""View mode operations: file deletion for single image display."""

import gc
import os
import time as _time

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from .busy_cursor import busy_cursor
from .file_operations import send_to_recycle_bin, show_delete_confirmation
from .logger import get_logger

_logger = get_logger("view_mode")


def _switch_to_adjacent_image(viewer) -> None:
    """Switch viewer to an adjacent image before deletion.

    Args:
        viewer: The ImageViewer instance
    """
    if len(viewer.image_files) <= 1:
        _logger.debug("[delete] single image case: will clear view later")
        return

    if viewer.current_index < len(viewer.image_files) - 1:
        new_index = viewer.current_index + 1
    else:
        new_index = viewer.current_index - 1

    _logger.debug("[delete] switch image: %s -> %s", viewer.current_index, new_index)
    viewer.current_index = new_index
    try:
        viewer.display_image()
        viewer.maintain_decode_window()
    except Exception as ex:
        _logger.debug("[delete] switch image error: %s", ex)


def _cleanup_cache_and_settle(viewer, del_path: str) -> None:
    """Remove path from cache and allow system to settle.

    Args:
        viewer: The ImageViewer instance
        del_path: Path to remove from cache
    """
    try:
        removed = viewer.engine.remove_from_cache(del_path)
        _logger.debug("[delete] cache pop: removed=%s", removed)
    except Exception as ex:
        _logger.debug("[delete] cache pop error: %s", ex)

    try:
        QApplication.processEvents()
        gc.collect()
        _time.sleep(0.15)
        _logger.debug("[delete] settle phase done")
    except Exception as ex:
        _logger.debug("[delete] settle phase error: %s", ex)


def _update_image_list_after_delete(viewer, del_path: str) -> None:
    """Remove deleted file from image list and adjust index.

    Args:
        viewer: The ImageViewer instance
        del_path: Path that was deleted
    """
    try:
        del_pos = viewer.image_files.index(del_path)
        viewer.image_files.pop(del_pos)
        if del_pos <= viewer.current_index:
            old_idx = viewer.current_index
            viewer.current_index = max(0, viewer.current_index - 1)
            _logger.debug("[delete] index adjust: %s -> %s", old_idx, viewer.current_index)
    except ValueError:
        try:
            viewer.image_files.remove(del_path)
            _logger.debug("[delete] list remove by value: success")
        except Exception as ex:
            _logger.debug("[delete] list remove error: %s", ex)


def _clear_viewer_if_empty(viewer) -> bool:
    """Clear viewer display if no images remain.

    Args:
        viewer: The ImageViewer instance

    Returns:
        True if viewer was cleared (no images left)
    """
    if viewer.image_files:
        return False

    _logger.debug("[delete] list empty: clearing view")
    viewer.current_index = -1
    try:
        empty = QPixmap(1, 1)
        empty.fill(Qt.GlobalColor.transparent)
        viewer.canvas.set_pixmap(empty)
    except Exception as ex:
        _logger.debug("[delete] clear view error: %s", ex)
    viewer.setWindowTitle("Image Viewer")
    viewer._update_status()
    return True


def delete_current_file(viewer) -> None:
    """Delete the current file in View Mode and move to trash.

    This function is specifically designed for View Mode where a single image
    is displayed. It handles:
    - Switching to another image before deletion
    - Updating the image list and index
    - Clearing the canvas if no images remain

    Args:
        viewer: The ImageViewer instance (View Mode)
    """
    # Validate state
    if (
        not viewer.image_files
        or viewer.current_index < 0
        or viewer.current_index >= len(viewer.image_files)
    ):
        _logger.debug("[delete] abort: no images or invalid index")
        return

    del_path = viewer.image_files[viewer.current_index]
    abs_path = os.path.abspath(del_path)
    _logger.debug(
        "[delete] start: idx=%s, path=%s, total=%s",
        viewer.current_index,
        del_path,
        len(viewer.image_files),
    )

    # Show confirmation dialog
    base = os.path.basename(del_path)
    if not show_delete_confirmation(
        viewer, "Delete File", "Delete this file?", f"{base}\n\nIt will be moved to Recycle Bin."
    ):
        _logger.debug("[delete] user cancelled")
        return

    # Step 1: Switch to another image first
    _switch_to_adjacent_image(viewer)

    # Step 2: Cleanup cache and settle
    _cleanup_cache_and_settle(viewer, del_path)

    # Step 3: Move to trash
    with busy_cursor():
        try:
            send_to_recycle_bin(abs_path)
            _logger.debug("[delete] trash success")
        except Exception as e:
            _logger.debug("[delete] trash error: %s", e)
            QMessageBox.critical(
                viewer,
                "Move Failed",
                f"Failed to move file to trash.\n\nError: {e}\nPath: {abs_path}",
            )
            return

    # Step 4: Ignore path in loader
    try:
        viewer.engine.ignore_path(del_path)
    except Exception:
        pass

    # Step 5: Update image list
    _update_image_list_after_delete(viewer, del_path)

    # Step 6: Update display
    if _clear_viewer_if_empty(viewer):
        return

    try:
        _logger.debug("[delete] show current: idx=%s, total=%s", viewer.current_index, len(viewer.image_files))
        viewer.display_image()
        viewer.maintain_decode_window()
    except Exception as ex:
        _logger.debug("[delete] final display error: %s", ex)
