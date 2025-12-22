import os

import numpy as np
import pyvips  # type: ignore

from image_viewer.logger import get_logger


def detect_trim_box_stats(path: str, profile: str | None = None) -> tuple[int, int, int, int] | None:
    """Detects a trim box based on simple statistics.

    Returns the minimum bounding box of the content, considering the outer background of the image.
    Returns None on failure.
    """
    try:
        img = pyvips.Image.new_from_file(path, access="sequential")
        img = img.colourspace("srgb") if hasattr(img, "colourspace") else img
        if img.hasalpha():
            img = img.flatten(background=[255, 255, 255])
        mem = img.write_to_memory()
        arr = np.frombuffer(mem, dtype=np.uint8).reshape(img.height, img.width, img.bands)
        gray = arr[..., :3].mean(axis=2)
        # Simple threshold: assumes a white background
        thresh = 250 if profile == "aggressive" else 245
        mask = gray < thresh
        if not mask.any():
            return None
        ys, xs = np.where(mask)
        top, bottom = int(ys.min()), int(ys.max())
        left, right = int(xs.min()), int(xs.max())
        return left, top, int(right - left + 1), int(bottom - top + 1)
    except Exception as e:
        _logger.debug("detect_trim_box_stats failed: %s", e)
        return None


def make_trim_preview(path: str, crop: tuple[int, int, int, int]) -> "np.ndarray | None":
    try:
        left, top, width, height = crop
        img = pyvips.Image.new_from_file(path, access="sequential")
        cropped = img.crop(left, top, width, height)
        mem = cropped.write_to_memory()
        arr = np.frombuffer(mem, dtype=np.uint8).reshape(cropped.height, cropped.width, cropped.bands)
        return arr.copy()
    except Exception as e:
        _logger.debug("make_trim_preview failed: %s", e)
        return None


def apply_trim_to_file(path: str, crop, overwrite: bool, alg: str | None = None) -> str:
    # crop: (left, top, width, height)
    left, top, width, height = crop
    # use pyvips to perform crop and write back
    image = pyvips.Image.new_from_file(path, access="sequential")
    image = image.crop(left, top, width, height)
    # Overwrite or write to new file
    if overwrite:
        out_path = path
    else:
        base, ext = os.path.splitext(path)
        out_path = f"{base}.trim{ext}"
    image.write_to_file(out_path)
    return out_path


_logger = get_logger("trim")
