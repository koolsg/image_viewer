"""Common file operation utilities.

This module provides low-level file operation utilities used by:
- view_mode_operations.py: View Mode file deletion
- explorer_mode_operations.py: Explorer Mode file operations (copy/cut/paste/delete)
"""

import shutil
from pathlib import Path

from PySide6.QtWidgets import QMessageBox
from send2trash import send2trash

from .logger import get_logger

_logger = get_logger("file_operations")

# Shared stylesheet for delete confirmation dialogs
DELETE_DIALOG_STYLE = """
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


def show_delete_confirmation(parent, title: str, text: str, info: str) -> bool:
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
    msg_box.setStyleSheet(DELETE_DIALOG_STYLE)

    msg_box.exec()
    return msg_box.clickedButton() == yes_btn


def send_to_recycle_bin(path: str) -> None:
    """Send a single file to recycle bin.

    Uses send2trash library for cross-platform support.

    Args:
        path: File path to delete

    Raises:
        Exception: If operation fails
    """
    _logger.debug("sending to recycle bin: %s", path)
    try:
        send2trash(path)
        _logger.debug("recycle bin success: %s", path)
    except Exception as e:
        _logger.error("recycle bin failed: %s -> %s", path, e)
        raise


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


def copy_file(src: str, dest_dir: str) -> str:
    """Copy a file to destination directory.

    Args:
        src: Source file path
        dest_dir: Destination directory

    Returns:
        Target file path

    Raises:
        Exception: If copy fails
    """
    src_path = Path(src)
    target = generate_unique_filename(dest_dir, src_path.name)
    _logger.debug("copying file: %s -> %s", src, target)
    try:
        shutil.copy2(str(src_path), target)
        _logger.debug("copy success: %s -> %s", src, target)
        return target
    except Exception as e:
        _logger.error("copy failed: %s -> %s, error: %s", src, target, e)
        raise


def move_file(src: str, dest_dir: str) -> str:
    """Move a file to destination directory.

    Args:
        src: Source file path
        dest_dir: Destination directory

    Returns:
        Target file path

    Raises:
        Exception: If move fails
    """
    src_path = Path(src)
    target = generate_unique_filename(dest_dir, src_path.name)
    _logger.debug("moving file: %s -> %s", src, target)
    try:
        shutil.move(str(src_path), target)
        _logger.debug("move success: %s -> %s", src, target)
        return target
    except Exception as e:
        _logger.error("move failed: %s -> %s, error: %s", src, target, e)
        raise
