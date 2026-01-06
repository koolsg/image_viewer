"""Common file operation utilities.

This module provides low-level *headless* file operation utilities.

UI concerns (confirmation dialogs, prompts) must live in QML.
"""

import shutil
from pathlib import Path

from send2trash import send2trash

from .logger import get_logger
from .path_utils import abs_path_str

_logger = get_logger("file_operations")


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
