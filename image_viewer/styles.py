"""Compatibility shim.

The canonical styling helpers live in `image_viewer.ui.styles`.
This module remains importable to avoid churn across the codebase.
"""

from image_viewer.ui.styles import FluentColors, apply_dark_theme, apply_light_theme, apply_theme

__all__ = ["FluentColors", "apply_dark_theme", "apply_light_theme", "apply_theme"]
