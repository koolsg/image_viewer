"""Explorer file operations shared by QWidget Explorer and QML shell.

This module intentionally contains *only* filesystem/clipboard operations that are
useful in Explorer-like UIs (copy/cut/paste/delete).

UI mode switching (View/Explorer stacking) lives elsewhere.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QGuiApplication

from .file_operations import copy_file, move_file, send_to_recycle_bin
from .logger import get_logger
from .path_utils import abs_dir, abs_path

_logger = get_logger("explorer_file_ops")


def _set_files_to_clipboard(paths: list[str], operation: str) -> None:
    """Set file paths to system clipboard (internal helper).

    Args:
        paths: List of file paths.
        operation: "copy" or "cut" (for logging).
    """
    if not paths:
        return

    mime = QMimeData()
    urls = [abs_path(p).as_uri() for p in paths]
    mime.setUrls([QUrl(u) for u in urls])

    cb = QGuiApplication.clipboard()
    if cb is None:
        _logger.warning("clipboard unavailable (%s %d paths)", operation, len(paths))
        return

    cb.setMimeData(mime)
    _logger.debug("%s %d files to clipboard", operation, len(paths))


def copy_files_to_clipboard(paths: list[str]) -> None:
    """Copy file paths to system clipboard."""

    _set_files_to_clipboard(paths, "copy")


def cut_files_to_clipboard(paths: list[str]) -> None:
    """Cut file paths to system clipboard."""

    _set_files_to_clipboard(paths, "cut")


def paste_files(dest_folder: str, clipboard_paths: list[str], mode: str) -> tuple[int, list[str]]:
    """Paste files from clipboard to destination folder.

    Args:
        dest_folder: Destination folder path.
        clipboard_paths: List of source file paths.
        mode: "copy" or "cut".

    Returns:
        Tuple of (success_count, failed_paths)
    """

    dest_dir = abs_dir(dest_folder)
    if not dest_dir.is_dir():
        _logger.warning("destination is not a directory: %s", dest_folder)
        return 0, list(clipboard_paths)

    success_count = 0
    failed_paths: list[str] = []

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


def get_files_from_clipboard() -> list[str] | None:
    """Get file paths from the system clipboard.

    Returns:
        List of file paths from clipboard, or None if clipboard doesn't contain files.
    """
    cb = QGuiApplication.clipboard()
    if cb is None:
        return None

    mime = cb.mimeData()
    if mime is None:
        return None

    if not mime.hasUrls():
        return None

    urls = mime.urls()
    if not urls:
        return None

    paths: list[str] = []
    for url in urls:
        if url.isLocalFile():
            paths.append(url.toLocalFile())

    return paths if paths else None


def rename_file(path: str, new_name: str) -> str:
    """Rename a file within the same directory.

    This is a pure filesystem operation intended to be called from QML UI flows.

    Args:
        path: Existing file path.
        new_name: New file name (basename only, no directories).

    Returns:
        The new absolute path as a string.
    """

    src = abs_path(path)
    nn = str(new_name).strip()
    if not nn:
        raise ValueError("new_name is empty")

    # Disallow path separators to avoid escaping the directory.
    if ("/" in nn) or ("\\" in nn):
        raise ValueError("new_name must be a basename (no path separators)")

    dest = src.with_name(nn)
    if dest.exists():
        raise FileExistsError(str(dest))

    _logger.debug("rename: %s -> %s", src, dest)
    dest2 = src.rename(dest)
    return str(dest2)


def delete_files_to_recycle_bin(paths: list[str]) -> tuple[int, list[str]]:
    """Delete files to recycle bin.

    Confirmation must be handled by the UI layer (QML).

    Returns:
        Tuple of (success_count, failed_paths)
    """

    if not paths:
        return 0, []

    success_count = 0
    failed_paths: list[str] = []

    for path in paths:
        try:
            send_to_recycle_bin(path)
            success_count += 1
        except Exception as exc:
            _logger.warning("delete failed for %s: %s", path, exc)
            failed_paths.append(path)

    _logger.debug("delete complete: %d success, %d failed", success_count, len(failed_paths))
    return success_count, failed_paths
