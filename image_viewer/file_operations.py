"""File operation handlers: delete, trim, etc."""
import gc
import os
import time as _time
import traceback as _tb

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox
from send2trash import send2trash

from .logger import get_logger

_logger = get_logger("file_operations")


def delete_current_file(viewer) -> None:
    """Delete the current file and move to trash.

    Args:
        viewer: The ImageViewer instance
    """
    # Move the current file to the trash (with a confirmation dialog).
    # UX: After confirming deletion, switch to another image first, then attempt the actual deletion.
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
        "[delete] start: idx=%s, del_path=%s, abs_path=%s, total=%s",
        viewer.current_index,
        del_path,
        abs_path,
        len(viewer.image_files),
    )

    # Confirmation dialog
    proceed = True
    base = os.path.basename(del_path)
    ret = QMessageBox.question(
        viewer,
        "Move to Trash",
        f"Are you sure you want to move this file to the trash?\n{base}",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    proceed = ret == QMessageBox.StandardButton.Yes
    _logger.debug("[delete] confirm: proceed=%s", proceed)
    if not proceed:
        _logger.debug("[delete] user cancelled")
        return

    # 1) Switch to another image to change the display reference
    if len(viewer.image_files) > 1:
        if viewer.current_index < len(viewer.image_files) - 1:
            new_index = viewer.current_index + 1
        else:
            new_index = viewer.current_index - 1
        _logger.debug(
            "[delete] switch image: %s -> %s", viewer.current_index, new_index
        )
        viewer.current_index = new_index
        try:
            viewer.display_image()
            viewer.maintain_decode_window()
        except Exception as ex:
            _logger.debug("[delete] switch image error: %s", ex)
    else:
        _logger.debug("[delete] single image case: will clear view later")

    # Remove the path from the screen/cache + stabilize with events/GC
    try:
        removed = viewer.pixmap_cache.pop(del_path, None) is not None
        _logger.debug("[delete] cache pop: removed=%s", removed)
    except Exception as ex:
        _logger.debug("[delete] cache pop error: %s", ex)
    try:
        QApplication.processEvents()
        _logger.debug("[delete] processEvents done")
        gc.collect()
        _logger.debug("[delete] gc.collect done")
        _time.sleep(0.15)
        _logger.debug("[delete] settle sleep done")
    except Exception as ex:
        _logger.debug("[delete] settle phase error: %s", ex)

    # 2) Actual move to trash (with retries)
    try:
        try:
            last_err = None
            for attempt in range(1, 4):
                try:
                    _logger.debug("[delete] trash attempt %s", attempt)
                    send2trash(abs_path)
                    last_err = None
                    _logger.debug("[delete] trash success")
                    break
                except Exception as ex:
                    last_err = ex
                    _logger.debug(
                        "[delete] trash failed attempt %s: %s", attempt, ex
                    )
                    _time.sleep(0.2)
            if last_err is not None:
                raise last_err
        except Exception:
            raise
    except Exception as e:
        _logger.debug("[delete] trash final error: %s", e)
        QMessageBox.critical(
            viewer,
            "Move Failed",
            (
                "An error occurred while moving the file to the trash.\n"
                "Please check your send2trash installation and the path.\n\n"
                f"Error: {e}\n"
                f"Original Path: {del_path}\n"
                f"Absolute Path: {abs_path}\n"
            ),
        )
        return

    # After confirming successful deletion, apply ignore to reliably ignore re-requests/completion signals
    try:
        if hasattr(viewer, "loader"):
            viewer.loader.ignore_path(del_path)
    except Exception:
        pass

    # 3) Remove from the list and clean up the index
    try:
        try:
            del_pos = viewer.image_files.index(del_path)
        except ValueError:
            del_pos = None
        _logger.debug("[delete] remove list: pos=%s", del_pos)
        if del_pos is not None:
            viewer.image_files.pop(del_pos)
            if del_pos <= viewer.current_index:
                old_idx = viewer.current_index
                viewer.current_index = max(0, viewer.current_index - 1)
                _logger.debug(
                    "[delete] index adjust: %s -> %s", old_idx, viewer.current_index
                )
    except Exception as ex:
        _logger.debug("[delete] list pop error, fallback remove: %s", ex)
        try:
            viewer.image_files.remove(del_path)
            _logger.debug("[delete] list remove by value: success")
        except Exception as ex2:
            _logger.debug("[delete] list remove by value error: %s", ex2)

    # 4) Final display/status update
    if not viewer.image_files:
        _logger.debug("[delete] list empty: clearing view")
        viewer.current_index = -1
        try:
            from PySide6.QtCore import Qt

            empty = QPixmap(1, 1)
            empty.fill(Qt.GlobalColor.transparent)
            viewer.canvas.set_pixmap(empty)
        except Exception as ex:
            _logger.debug("[delete] clear view error: %s", ex)
        viewer.setWindowTitle("Image Viewer")
        viewer._update_status()
        return
    try:
        _logger.debug(
            "[delete] show current: idx=%s, total=%s",
            viewer.current_index,
            len(viewer.image_files),
        )
        viewer.display_image()
        viewer.maintain_decode_window()
    except Exception as ex:
        _logger.debug("[delete] final display error: %s", ex)
