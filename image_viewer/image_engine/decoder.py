"""Image decoder using pyvips.

This module provides the core image decoding functionality using pyvips
for high-performance image loading and processing.
"""

import contextlib
import os
from pathlib import Path
from typing import Any

import numpy as np

from image_viewer.infra.logger import get_logger

_logger = get_logger("decoder")

# Constants
RGB_CHANNELS = 3

# Locate bundled libvips (for frozen exe/_MEIPASS and source tree)
_BASE_DIR = Path(getattr(os.sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
_LIBVIPS_DIR = _BASE_DIR / "libvips"
if os.name == "nt" and _LIBVIPS_DIR.exists():
    with contextlib.suppress(Exception):
        os.add_dll_directory(str(_LIBVIPS_DIR))


try:
    import pyvips  # type: ignore
except Exception:
    pyvips = None


def _get_pyvips_module() -> Any:
    """Return the pyvips module or raise ImportError if unavailable."""
    if pyvips is None:
        raise ImportError("pyvips is not available")
    return pyvips


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

    _logger.debug(
        "_decode_with_pyvips_from_file: path=%s target_width=%s target_height=%s size=%s",
        path,
        target_width,
        target_height,
        size,
    )

    if (target_width and target_width > 0) or (target_height and target_height > 0):
        tw = int(target_width or 0)
        th = int(target_height or 0)
        if tw > 0 and th > 0:
            _logger.debug("_decode_with_pyvips_from_file: using thumbnail(tw=%d, th=%d, size=%s)", tw, th, size)
            image = pyvips.Image.thumbnail(path, tw, height=th, size=size)
        elif tw > 0:
            _logger.debug("_decode_with_pyvips_from_file: using thumbnail(tw=%d, size=%s)", tw, size)
            image = pyvips.Image.thumbnail(path, tw, size=size)
        else:
            _logger.debug("_decode_with_pyvips_from_file: using new_from_file (no target height)")
            image = pyvips.Image.new_from_file(path, access="sequential")
    else:
        _logger.debug("_decode_with_pyvips_from_file: using new_from_file (no target size)")
        image = pyvips.Image.new_from_file(path, access="sequential")

    _logger.debug(
        "_decode_with_pyvips_from_file: image loaded bands=%d format=%s height=%d width=%d",
        image.bands,
        image.format,
        image.height,
        image.width,
    )

    with contextlib.suppress(Exception):
        image = image.copy_memory()
    with contextlib.suppress(Exception):
        image = image.colourspace("srgb")
    if image.hasalpha():
        _logger.debug("_decode_with_pyvips_from_file: flattening alpha channel")
        image = image.flatten(background=[0, 0, 0])
    if image.bands > RGB_CHANNELS:
        _logger.debug("_decode_with_pyvips_from_file: extracting RGB from %d bands", image.bands)
        image = image.extract_band(0, RGB_CHANNELS)
    elif image.bands < RGB_CHANNELS:
        _logger.debug("_decode_with_pyvips_from_file: bandjoin to create RGB from %d bands", image.bands)
        image = pyvips.Image.bandjoin([image] * RGB_CHANNELS)
    if image.format != "uchar":
        _logger.debug("_decode_with_pyvips_from_file: casting from %s to uchar", image.format)
        image = image.cast("uchar")

    _logger.debug("_decode_with_pyvips_from_file: writing to memory, final bands=%d", image.bands)
    mem = image.write_to_memory()
    array = np.frombuffer(mem, dtype=np.uint8).reshape(image.height, image.width, image.bands)
    array = array.copy()
    with contextlib.suppress(Exception):
        del image
    if array.shape[2] != RGB_CHANNELS:
        raise RuntimeError(f"Unsupported band count after conversion: {array.shape[2]}")
    _logger.debug("_decode_with_pyvips_from_file: decoded successfully shape=%s", array.shape)
    return array


def get_image_dimensions(file_path: str) -> tuple[int | None, int | None]:
    """Get image dimensions using libvips (faster than QImageReader).

    Returns (width, height) or (None, None) if failed.
    """
    try:
        pyvips = _get_pyvips_module()
        # Configure pyvips caches to avoid memory growth
        with contextlib.suppress(Exception):
            pyvips.cache_set_max(0)
            pyvips.cache_set_max_mem(0)
            pyvips.cache_set_max_files(0)

        # Use new_from_file with access="sequential" for header-only reading
        image = pyvips.Image.new_from_file(file_path, access="sequential")
        width = image.width
        height = image.height

        # Clean up
        with contextlib.suppress(Exception):
            del image

        return width, height
    except Exception as e:
        _logger.debug("get_image_dimensions failed for %s: %s", file_path, e)
        return None, None


def decode_image(
    file_path: str, target_width: int | None = None, target_height: int | None = None, size: str = "both"
) -> tuple[str, object | None, str | None]:
    """Decode image from file path into an RGB numpy array using pyvips only.

    Returns (path, array|None, error|None).
    """
    try:
        _logger.debug(
            "decode_image: starting for %s (target=%sx%s size=%s)",
            file_path,
            target_width,
            target_height,
            size,
        )
        array = _decode_with_pyvips_from_file(file_path, target_width, target_height, size)
        _logger.debug(
            "decode_image: success for %s shape=%s",
            file_path,
            array.shape if array is not None else None,
        )
        return file_path, array, None
    except Exception as e:
        _logger.error("decode_image: failed for %s: %s", file_path, e, exc_info=True)
        return file_path, None, str(e)


def encode_image_to_png(
    file_path: str, target_width: int | None = None, target_height: int | None = None, size: str = "both"
) -> tuple[str, object | None, str | None]:
    """Encode image from file path directly to PNG bytes using pyvips.

    Returns (path, png_bytes|None, error|None).
    """
    try:
        pyvips = _get_pyvips_module()
        # Configure pyvips caches to avoid memory growth
        with contextlib.suppress(Exception):
            pyvips.cache_set_max(0)
            pyvips.cache_set_max_mem(0)
            pyvips.cache_set_max_files(0)

        # Use thumbnail when a target size is requested to avoid full-file decode
        if (target_width and target_width > 0) or (target_height and target_height > 0):
            tw = int(target_width or 0)
            th = int(target_height or 0)
            if tw > 0 and th > 0:
                image = pyvips.Image.thumbnail(file_path, tw, height=th, size=size)
            elif tw > 0:
                image = pyvips.Image.thumbnail(file_path, tw, size=size)
            else:
                image = pyvips.Image.new_from_file(file_path, access="sequential")
        else:
            image = pyvips.Image.new_from_file(file_path, access="sequential")

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

        out = image.write_to_buffer(".png")
        if isinstance(out, bytes):
            return file_path, out, None
        return file_path, bytes(out), None
    except Exception as e:
        _logger.debug("encode to png failed: %s", e)
        return file_path, None, str(e)
