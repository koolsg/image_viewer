"""Common file operation utilities.

This module provides low-level file operation utilities used by:
- view_mode_operations.py: View Mode file deletion
- explorer_mode_operations.py: Explorer Mode file operations (copy/cut/paste/delete)
"""

import shutil
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
)
from send2trash import send2trash

from .logger import get_logger
from .path_utils import abs_path_str

_logger = get_logger("file_operations")


LUMINANCE_DARK_THRESHOLD = 128


def _is_palette_dark(pal: QPalette) -> bool:
    # Estimate whether a palette is dark by checking window color luminance
    w = pal.color(QPalette.Window)
    luminance = 0.299 * w.red() + 0.587 * w.green() + 0.114 * w.blue()
    return luminance < LUMINANCE_DARK_THRESHOLD


class DeleteConfirmationDialog(QDialog):
    def __init__(self, parent, title: str, text: str, info: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        # Main Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header Area (Icon + Main Text)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)

        # Icon
        icon_label = QLabel()
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        icon_label.setPixmap(icon.pixmap(QSize(48, 48)))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        icon_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        header_layout.addWidget(icon_label)

        # Text Container (Title + Info)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(8)

        # Main Title (Bold)
        title_label = QLabel(text)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        title_label.setWordWrap(True)
        text_layout.addWidget(title_label)

        # Detail Info (File path etc)
        info_label = QLabel(info)
        info_label.setWordWrap(True)
        # Use appropriate styling for secondary text if needed, or rely on global theme
        text_layout.addWidget(info_label)

        header_layout.addLayout(text_layout)
        layout.addLayout(header_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_yes = QPushButton("Yes(&Y)")
        self.btn_yes.setObjectName("button-yes")
        self.btn_yes.setMinimumWidth(80)

        self.btn_no = QPushButton("No(&N)")
        self.btn_no.setObjectName("button-no")
        self.btn_no.setMinimumWidth(80)

        btn_layout.addWidget(self.btn_yes)
        btn_layout.addWidget(self.btn_no)
        layout.addLayout(btn_layout)

        # Button connections
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)

        # Shortcuts
        pass  # Handle in keyPressEvent or shortcuts if standard mnemonics don't work well
        # Note: Mnemonics like &Yes work on button text automaticlly in some contexts, but let's be explicit if needed.
        # Shortcuts for Y/N
        self.btn_yes.setShortcut(QKeySequence("Y"))
        self.btn_no.setShortcut(QKeySequence("N"))

    def sizeHint(self):
        return QSize(550, 200)


def build_delete_dialog_style(theme: str | None = None) -> str:
    """Build a stylesheet for the delete confirmation dialog based on theme."""
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
    dlg = DeleteConfirmationDialog(parent, title, text, info)

    # Apply theme
    theme = None
    try:
        if hasattr(parent, "_settings_manager"):
            theme = parent._settings_manager.get("theme", None)
    except Exception:
        theme = None
    dlg.setStyleSheet(build_delete_dialog_style(theme))

    return dlg.exec() == QDialog.DialogCode.Accepted


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
        abs_p = abs_path_str(path)
        send2trash(abs_p)
        _logger.debug("recycle bin success: %s", abs_p)
    except Exception as e:
        _logger.error("recycle bin failed: %s -> %s", abs_p if "abs_p" in locals() else path, e)
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
