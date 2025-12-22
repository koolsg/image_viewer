"""Trim package public API.

Expose pure-backend trim helpers and operations as `image_viewer.trim`.
"""

from image_viewer.trim.trim import apply_trim_to_file, detect_trim_box_stats, make_trim_preview
from image_viewer.trim.trim_operations import start_trim_workflow

__all__ = [
    "apply_trim_to_file",
    "detect_trim_box_stats",
    "make_trim_preview",
    "start_trim_workflow",
]
