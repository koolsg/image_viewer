"""Compatibility shim: provide `image_viewer.image_viewer` module for older imports.

Some tests and external callers import `image_viewer.image_viewer.<module>`; this file
re-exports commonly used modules from the package root to preserve compatibility.
"""

from . import explorer_mode_operations  # re-export for compatibility

__all__ = ["explorer_mode_operations"]
