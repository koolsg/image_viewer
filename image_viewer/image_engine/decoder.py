"""Image decoder using pyvips.

This module provides the core image decoding functionality using pyvips
for high-performance image loading and processing.
"""

import contextlib
import os
from pathlib import Path
from typing import Any

import numpy as np

from image_viewer.logger import get_logger

_logger = get_logger("decoder")

# Constants
RGB_CHANNELS = 3

# Locate bundled libvips (for frozen exe/_MEIPASS and source tree)
_BASE_DIR = Path(getattr(os.sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
_LIBVIPS_DIR = _BASE_DIR / "libvips"
if os.name == "nt" and _LIBVIPS_DIR.exists():
    with contextlib.suppress(Exception):
        os.add_dll_directory(str(_LIBVIPS_DIR))


_pyvips: Any | None = None


def _get_pyvips_module() -> Any:
    global _pyvips
    if _pyvips is None:
        import pyvips  # type: ignore

        _pyvips = pyvips
    return _pyvips


def _decode_with_pyvips_from_file(
    path: str, target_width: int | None = None, target_height: int | None = None, size: str = "both"
) -> "np.ndarray":
    """Decode arbitrary image bytes into an RGB numpy array using pyvips."""
    pyvips = _get_pyvips_module()
    # Configure pyvips caches to avoid memory growth
    with contextlib.suppress(Exception):
        pyvips.cache_set_max(0)
        pyvips.cache_set_max_mem(0)
        pyvips.cache_set_max_files(0)

    if (target_width and target_width > 0) or (target_height and target_height > 0):
        tw = int(target_width or 0)
        th = int(target_height or 0)
        if tw > 0 and th > 0:
            image = pyvips.Image.thumbnail(path, tw, height=th, size=size)
        elif tw > 0:
            image = pyvips.Image.thumbnail(path, tw, size=size)
        else:
            image = pyvips.Image.new_from_file(path, access="sequential")
    else:
        image = pyvips.Image.new_from_file(path, access="sequential")

    with contextlib.suppress(Exception):
        image = image.copy_memory()
    with contextlib.suppress(Exception):
        image = image.colourspace("srgb")
    if image.hasalpha():
        image = image.flatten(background=[0, 0, 0])
    if image.bands > RGB_CHANNELS:
        image = image.extract_band(0, RGB_CHANNELS)
    elif image.bands < RGB_CHANNELS:
        image = pyvips.Image.bandjoin([image] * RGB_CHANNELS)
    if image.format != "uchar":
        image = image.cast("uchar")

    mem = image.write_to_memory()
    array = np.frombuffer(mem, dtype=np.uint8).reshape(image.height, image.width, image.bands)
    array = array.copy()
    with contextlib.suppress(Exception):
        del image
    if array.shape[2] != RGB_CHANNELS:
        raise RuntimeError(f"Unsupported band count after conversion: {array.shape[2]}")
    return array


def decode_image(
    file_path: str, target_width: int | None = None, target_height: int | None = None, size: str = "both"
) -> tuple[str, object | None, str | None]:
    """Decode image from file path into an RGB numpy array using pyvips only.

    Returns (path, array|None, error|None).
    """
    try:
        array = _decode_with_pyvips_from_file(file_path, target_width, target_height, size)
        return file_path, array, None
    except Exception as e:
        _logger.debug("decode failed: %s", e)
        return file_path, None, str(e)
