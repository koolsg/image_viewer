"""Compatibility shim.

The canonical path utilities live in `image_viewer.infra.path_utils`.
This module remains importable to avoid churn across the codebase.
"""

from image_viewer.infra.path_utils import abs_dir, abs_dir_str, abs_path, abs_path_str, db_key

__all__ = ["abs_dir", "abs_dir_str", "abs_path", "abs_path_str", "db_key"]
