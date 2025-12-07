"""File operation handlers for both View and Explorer modes.

This module provides file operation functions that can be used by:
- View Mode: delete_current_file() - deletes currently displayed image
- Explorer Mode: copy/cut/paste/delete functions - operates on selected files
"""

import ctypes
import gc
import os
import shutil
import time as _time
from ctypes import wintypes
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from .busy_cursor import busy_cursor
from .logger import get_logger

_logger = get_logger("file_operations")

# Shared stylesheet for delete confirmation dialogs
_DELETE_DIALOG_STYLE = """
    QMessageBox {
        background-color: #2b2b2b;
    }
    QMessageBox QLabel {
        color: #ffffff;
        font-size: 13px;
    }
    QPushButton {
        min-width: 80px;
        min-height: 32px;
        padding: 6px 16px;
        font-size: 13px;
        font-weight: bold;
        border-radius: 4px;
        border: 2px solid transparent;
    }
    QPushButton[text="Delete"] {
        background-color: #d32f2f;
        color: #ffffff;
        border: 2px solid #f44336;
    }
    QPushButton[text="Delete"]:hover {
        background-color: #f44336;
        border: 2px solid #ff5252;
    }
    QPushButton[text="Delete"]:focus {
        border: 2px solid #ff5252;
        outline: none;
    }
    QPushButton[text="Cancel"] {
        background-color: #424242;
        color: #ffffff;
        border: 2px solid #616161;
    }
    QPushButton[text="Cancel"]:hover {
        background-color: #616161;
        border: 2px solid #757575;
    }
    QPushButton[text="Cancel"]:focus {
        border: 2px solid #4A90E2;
        outline: none;
    }
"""


# ============= View Mode Operations =============


def _show_delete_confirmation(parent, title: str, text: str, info: str) -> bool:
    """Show delete confirmation dialog with styled buttons.

    Args:
        parent: Parent widget for the dialog
        title: Dialog title
        text: Main text
        info: Informative text

    Returns:
        True if user confirmed deletion
    """
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.setText(text)
    msg_box.setInformativeText(info)

    yes_btn = msg_box.addButton("Delete", QMessageBox.ButtonRole.YesRole)
    no_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.NoRole)
    msg_box.setDefaultButton(no_btn)
    msg_box.setStyleSheet(_DELETE_DIALOG_STYLE)

    msg_box.exec()
    return msg_box.clickedButton() == yes_btn


def _switch_to_adjacent_image(viewer, del_path: str) -> None:
    """Switch viewer to an adjacent image before deletion.

    Args:
        viewer: The ImageViewer instance
        del_path: Path of file being deleted
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
        removed = viewer.pixmap_cache.pop(del_path, None) is not None
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
    if not _show_delete_confirmation(
        viewer, "Delete File", "Delete this file?", f"{base}\n\nIt will be moved to Recycle Bin."
    ):
        _logger.debug("[delete] user cancelled")
        return

    # Step 1: Switch to another image first
    _switch_to_adjacent_image(viewer, del_path)

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
        if hasattr(viewer, "loader"):
            viewer.loader.ignore_path(del_path)
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


# ============= Explorer Mode File Operations =============


def copy_files_to_clipboard(paths: list[str]) -> None:
    """Copy file paths to system clipboard.

    Args:
        paths: List of file paths to copy
    """
    try:
        mime = QMimeData()
        urls = [Path(p).as_uri() for p in paths]
        mime.setUrls([QUrl(u) for u in urls])
        QGuiApplication.clipboard().setMimeData(mime)
        _logger.debug("copied %d files to clipboard", len(paths))
    except Exception as exc:
        _logger.error("failed to copy to clipboard: %s", exc)


def cut_files_to_clipboard(paths: list[str]) -> None:
    """Cut file paths to system clipboard.

    Args:
        paths: List of file paths to cut
    """
    try:
        mime = QMimeData()
        urls = [Path(p).as_uri() for p in paths]
        mime.setUrls([QUrl(u) for u in urls])
        QGuiApplication.clipboard().setMimeData(mime)
        _logger.debug("cut %d files to clipboard", len(paths))
    except Exception as exc:
        _logger.error("failed to cut to clipboard: %s", exc)


def paste_files(
    dest_folder: str, clipboard_paths: list[str], mode: str
) -> tuple[int, list[str]]:
    """Paste files from clipboard to destination folder.

    Args:
        dest_folder: Destination folder path
        clipboard_paths: List of source file paths
        mode: "copy" or "cut"

    Returns:
        Tuple of (success_count, failed_paths)
    """
    dest_dir = Path(dest_folder)
    if not dest_dir.is_dir():
        _logger.warning("destination is not a directory: %s", dest_folder)
        return 0, clipboard_paths

    success_count = 0
    failed_paths = []

    for src in clipboard_paths:
        try:
            src_path = Path(src)
            if not src_path.exists():
                failed_paths.append(src)
                continue

            target = generate_unique_filename(str(dest_dir), src_path.name)

            if mode == "cut":
                shutil.move(str(src_path), target)
            else:
                shutil.copy2(str(src_path), target)

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


def delete_files_to_recycle_bin(
    paths: list[str], parent_widget=None
) -> tuple[int, list[str]]:
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
    if parent_widget and not _show_delete_confirmation(
        parent_widget,
        "Delete Files",
        f"Delete {len(paths)} item(s)?",
        "They will be moved to Recycle Bin when possible.",
    ):
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


def send_to_recycle_bin(path: str) -> None:
    """Send a single file to recycle bin (Windows).

    Args:
        path: File path to delete

    Raises:
        OSError: If operation fails
    """
    try:
        FO_DELETE = 3
        FOF_ALLOWUNDO = 0x40
        FOF_NOCONFIRMATION = 0x10

        class SHFILEOPSTRUCT(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [  # type: ignore[assignment]
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        p_from = f"{Path(path)}\0\0"
        op = SHFILEOPSTRUCT()
        op.wFunc = FO_DELETE
        op.pFrom = p_from
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if res != 0:
            raise OSError(f"SHFileOperation failed: {res}")
    except Exception:
        # Fallback to direct delete
        Path(path).unlink(missing_ok=True)


def generate_unique_filename(dest_dir: str, filename: str) -> str:
    """Generate unique filename if file already exists.

    Args:
        dest_dir: Destination directory
        filename: Original filename

    Returns:
        Unique filename path (e.g., "file - Copy (1).jpg")
    """
    dest = Path(dest_dir) / filename
    if not dest.exists():
        return str(dest)

    stem = dest.stem
    suffix = dest.suffix
    counter = 1

    while dest.exists():
        dest = Path(dest_dir) / f"{stem} - Copy ({counter}){suffix}"
        counter += 1

    return str(dest)
