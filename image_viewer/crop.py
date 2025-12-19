"""Image crop backend using pyvips.

Pure functions for cropping images, no Qt dependencies.
"""

import contextlib
from typing import Any

from image_viewer.logger import get_logger

_logger = get_logger("crop")

try:
    import pyvips  # type: ignore
except ImportError:
    pyvips = None  # type: ignore
    _logger.warning("pyvips is not available; crop functions will raise ImportError when used")


def _get_pyvips_module() -> Any:
    """Return the pyvips module or raise ImportError if unavailable."""
    if pyvips is None:
        _logger.error("pyvips requested but not available")
        raise ImportError("pyvips is not available")
    return pyvips


def validate_crop_bounds(img_width: int, img_height: int, crop: tuple[int, int, int, int]) -> bool:
    """Validate that crop rectangle is within image bounds.

    Args:
        img_width: Original image width
        img_height: Original image height
        crop: (left, top, width, height) crop rectangle

    Returns:
        True if crop is valid, False otherwise
    """
    left, top, width, height = crop
    if left < 0 or top < 0:
        return False
    if width <= 0 or height <= 0:
        return False
    if left + width > img_width:
        return False
    return not top + height > img_height


def apply_crop_to_file(source_path: str, crop: tuple[int, int, int, int], output_path: str) -> str:
    """Crop image and save to file using pyvips.

    Args:
        source_path: Path to source image file
        crop: (left, top, width, height) crop rectangle in original image coordinates
        output_path: Path to save cropped image

    Returns:
        Path to saved file (same as output_path)

    Raises:
        Exception: If crop operation fails
    """
    pyvips = _get_pyvips_module()

    # Configure pyvips caches to avoid memory growth
    with contextlib.suppress(Exception):
        pyvips.cache_set_max(0)
        pyvips.cache_set_max_mem(0)
        pyvips.cache_set_max_files(0)

    left, top, width, height = crop

    _logger.debug("Cropping %s: crop=%s -> %s", source_path, crop, output_path)

    # Load, crop, and save
    try:
        image = pyvips.Image.new_from_file(source_path, access="sequential")
    except Exception as e:
        _logger.error("Failed to open source image %s: %s", source_path, e, exc_info=True)
        raise

    # Validate bounds
    if not validate_crop_bounds(image.width, image.height, crop):
        _logger.error("Crop bounds %s invalid for image size %dx%d", crop, image.width, image.height)
        raise ValueError(f"Crop bounds {crop} invalid for image size {image.width}x{image.height}")

    try:
        cropped = image.crop(left, top, width, height)
        cropped.write_to_file(output_path)
    except Exception as e:
        _logger.error("Error during crop/write operation for %s -> %s: %s", source_path, output_path, e, exc_info=True)
        raise
    finally:
        # Clean up
        with contextlib.suppress(Exception):
            del image
        with contextlib.suppress(Exception):
            del cropped

    _logger.info("Crop saved: %s", output_path)
    return output_path
