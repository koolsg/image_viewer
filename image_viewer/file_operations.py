"""Common file operation utilities.

This module provides low-level file operation utilities used by:
- view_mode_operations.py: View Mode file deletion
- explorer_mode_operations.py: Explorer Mode file operations (copy/cut/paste/delete)
"""

import contextlib
import shutil
from pathlib import Path

from PySide6.QtGui import QKeySequence, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox
from send2trash import send2trash

from .logger import get_logger

_logger = get_logger("file_operations")


LUMINANCE_DARK_THRESHOLD = 128


def _is_palette_dark(pal: QPalette) -> bool:
    # Estimate whether a palette is dark by checking window color luminance
    w = pal.color(QPalette.Window)
    luminance = 0.299 * w.red() + 0.587 * w.green() + 0.114 * w.blue()
    return luminance < LUMINANCE_DARK_THRESHOLD


def build_delete_dialog_style(theme: str | None = None) -> str:
    """Build a stylesheet for the delete confirmation dialog based on theme.

    If theme is None, determine from current QApplication palette.
    """
    if theme is None:
        try:
            app = QApplication.instance()
            theme = "dark" if _is_palette_dark(app.palette()) else "light"
        except Exception:
            theme = "dark"

    if theme == "light":
        cancel_bg = "#e0e0e0"
        cancel_text = "#000000"
        cancel_border = "#bdbdbd"
    else:
        cancel_bg = "#424242"
        cancel_text = "#ffffff"
        cancel_border = "#616161"

    # Colors for both themes - make Yes neutral (no red)
    delete_bg = cancel_bg
    delete_bg_hover = cancel_bg
    delete_border = cancel_border
    delete_text = cancel_text

    return (
        "QPushButton { min-width: 80px; min-height: 32px; padding: 6px 16px; font-size: 13px; "
        "font-weight: bold; border-radius: 4px; border: 2px solid transparent; }"
        f"\nQPushButton#button-yes {{ background-color: {delete_bg}; "
        f"color: {delete_text}; border: 2px solid {delete_border}; }}"
        f"\nQPushButton#button-yes:hover {{ background-color: {delete_bg_hover}; }}"
        "\nQPushButton#button-yes:focus, QPushButton#button-yes:default { "
        "border: 2px solid #4A90E2; outline: none; }"
        f"\nQPushButton#button-no {{ background-color: {cancel_bg}; "
        f"color: {cancel_text}; border: 2px solid {cancel_border}; }}"
        "\nQPushButton#button-no:hover { border: 2px solid #757575; }"
        "\nQPushButton#button-no:focus, QPushButton#button-no:default { "
        "border: 2px solid #4A90E2; outline: none; }"
        "\nQPushButton:default { outline: none; }"
    )


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

    # Use & for mnemonics (standard Windows behavior: underlines Y/N)
    yes_btn = msg_box.addButton("&Yes", QMessageBox.ButtonRole.YesRole)
    yes_btn.setObjectName("button-yes")
    # Allow simple Y shortcut (without Alt) for convenience
    with contextlib.suppress(Exception):
        yes_btn.setShortcut(QKeySequence("Y"))

    no_btn = msg_box.addButton("&No", QMessageBox.ButtonRole.NoRole)
    no_btn.setObjectName("button-no")
    with contextlib.suppress(Exception):
        no_btn.setShortcut(QKeySequence("N"))

    # Make Yes the default action
    msg_box.setDefaultButton(yes_btn)
    # Make Cancel the escape action
    msg_box.setEscapeButton(no_btn)

    # Apply theme
    theme = None
    try:
        if hasattr(parent, "_settings_manager"):
            theme = parent._settings_manager.get("theme", None)
    except Exception:
        theme = None
    msg_box.setStyleSheet(build_delete_dialog_style(theme))

    # Make the dialog wider
    # Using a spacer logic or minimum width.
    # QMessageBox layout is tricky, usually setMinimumWidth works if called before exec.
    # To ensure it looks wide enough for improved readability:
    msg_box.layout().setSpacing(20)  # Add some spacing
    msg_box.setMinimumWidth(500)

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

        dest_dir: Destination directory
        filename: Original filename

    Returns:
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
