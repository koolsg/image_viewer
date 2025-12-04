"""Busy cursor context manager for long-running operations."""

from contextlib import contextmanager

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


@contextmanager
def busy_cursor():
    """Context manager for showing busy cursor (hourglass) during operations.

    Usage:
        with busy_cursor():
            # Long-running operation
            load_large_file()

    The cursor will automatically restore even if an exception occurs.
    """
    try:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()  # Immediately reflect cursor change
        yield
    finally:
        QApplication.restoreOverrideCursor()
