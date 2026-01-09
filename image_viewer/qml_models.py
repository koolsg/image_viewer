"""Compatibility shim.

The canonical QML models live in `image_viewer.ui.qml_models`.
This module remains importable to avoid churn across the codebase.
"""

from image_viewer.ui.qml_models import QmlImageEntry, QmlImageGridModel

__all__ = ["QmlImageEntry", "QmlImageGridModel"]
