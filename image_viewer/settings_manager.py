"""Compatibility shim.

The canonical settings implementation lives in `image_viewer.infra.settings_manager`.
This module remains importable to avoid churn across the codebase.
"""

from image_viewer.infra.settings_manager import SettingsManager

__all__ = ["SettingsManager"]
