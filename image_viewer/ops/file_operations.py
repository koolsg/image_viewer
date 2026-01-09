"""Common file operation utilities.

This module provides low-level *headless* file operation utilities.

UI concerns (confirmation dialogs, prompts) must live in QML.
"""

import shutil
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QGuiApplication
from send2trash import send2trash

from image_viewer.infra.logger import get_logger
from image_viewer.infra.path_utils import abs_path, abs_path_str

_logger = get_logger("file_operations")


# Clipboard helpers (moved from explorer_file_ops)
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


def paste_files(dest_folder: str, clipboard_paths: list[str], mode: str) -> tuple[int, list[str]]:
    """Paste files from clipboard to destination folder.

    Args:
        dest_folder: Destination folder path.
        clipboard_paths: List of source file paths.
        mode: "copy" or "cut".

    Returns:
        Tuple of (success_count, failed_paths)
    """

    dest_dir = abs_path(dest_folder)
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


def send_to_recycle_bin(path: str) -> None:
    """Send a single file to recycle bin.

    Uses send2trash library for cross-platform support.

    Args:
        path: File path to delete

    Raises:
        Exception: If operation fails
    """
    _logger.debug("sending to recycle bin: %s", path)
    abs_p: str | None = None
    try:
        abs_p = abs_path_str(path)
        send2trash(abs_p)
        _logger.debug("recycle bin success: %s", abs_p)
    except Exception as e:
        _logger.error("recycle bin failed: %s -> %s", abs_p or path, e)
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


def rename_file(path: str, new_name: str) -> str:
    """Rename a file within the same directory.

    Args:
        path: Existing file path.
        new_name: New file name (basename only, no directories).

    Returns:
        The new absolute path as a string.
    """
    src = Path(path)
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
