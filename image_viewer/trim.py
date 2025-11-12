import os

import numpy as np
import pyvips  # type: ignore


def detect_trim_box_stats(path: str, profile: str | None = None) -> tuple[int, int, int, int] | None:
    """간단한 통계 기반 트림 박스 검출.

    이미지의 외곽 배경을 감안해 컨텐츠 최소 경계 사각형을 반환.
    실패 시 None.
    """
    try:
        img = pyvips.Image.new_from_file(path, access="sequential")
        img = img.colourspace("srgb") if hasattr(img, "colourspace") else img
        if img.hasalpha():
            img = img.flatten(background=[255, 255, 255])
        mem = img.write_to_memory()
        arr = np.frombuffer(mem, dtype=np.uint8).reshape(img.height, img.width, img.bands)
        gray = arr[..., :3].mean(axis=2)
        # 간단 임계값: 흰색 배경 가정
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


from .logger import get_logger

_logger = get_logger("trim")
