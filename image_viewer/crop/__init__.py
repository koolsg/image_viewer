"""Crop package public API.

Expose pure-backend crop helpers for external import as `image_viewer.crop`.
Keep this module lightweight to avoid importing Qt-heavy UI modules at package import time.
"""

from .crop import apply_crop_to_file, validate_crop_bounds

# Expose the pyvips module object at package-level to support tests that patch it
from . import crop as _crop

pyvips = getattr(_crop, "pyvips", None)


def _get_pyvips_module() -> object:
    """Return the package-level pyvips object or raise ImportError if unavailable.

    This wrapper exists so tests (and callers) can monkeypatch `image_viewer.crop.pyvips`
    on the package object and have `_get_pyvips_module` observe the change.
    """
    if pyvips is None:
        raise ImportError("pyvips is not available")
    return pyvips


__all__ = [
    "_get_pyvips_module",
    "apply_crop_to_file",
    "pyvips",
    "validate_crop_bounds",
]
