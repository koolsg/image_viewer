"""Compatibility shim.

The canonical file operation utilities live in `image_viewer.ops.file_operations`.
This module remains importable to avoid churn across the codebase.
"""

from image_viewer.ops.file_operations import (
    copy_file,
    copy_files_to_clipboard,
    cut_files_to_clipboard,
    delete_files_to_recycle_bin,
    generate_unique_filename,
    get_files_from_clipboard,
    move_file,
    paste_files,
    rename_file,
    send_to_recycle_bin,
)

__all__ = [
    "copy_file",
    "copy_files_to_clipboard",
    "cut_files_to_clipboard",
    "delete_files_to_recycle_bin",
    "generate_unique_filename",
    "get_files_from_clipboard",
    "move_file",
    "paste_files",
    "rename_file",
    "send_to_recycle_bin",
]
