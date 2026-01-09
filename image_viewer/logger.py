"""Compatibility shim.

The canonical logger implementation lives in `image_viewer.infra.logger`.
This module remains importable to avoid churn across the codebase.
"""

from image_viewer.infra.logger import get_logger, setup_logger

__all__ = ["get_logger", "setup_logger"]
