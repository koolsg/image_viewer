"""Compatibility shim.

The canonical WebP conversion controller lives in `image_viewer.ops.webp_converter`.
This module remains importable to avoid churn across the codebase.
"""

from image_viewer.ops.webp_converter import ConvertController, ConvertWorker

__all__ = ["ConvertController", "ConvertWorker"]
