import contextlib
import os
from typing import Any

import numpy as np

# --- Optional .env support to load LIBVIPS_BIN for Windows child processes ---
from image_viewer.logger import get_logger

_logger = get_logger("decoder")


def _load_env_file(env_path: str = ".env") -> None:
    try:
        if not os.path.exists(env_path):
            return
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k and v and k not in os.environ:
                    os.environ[k] = v
    except (OSError, UnicodeError) as e:
        # .env load failure is not critical
        _logger.debug("env load skipped: %s", e)


_load_env_file()
_LIBVIPS_BIN = os.environ.get("LIBVIPS_BIN")
if _LIBVIPS_BIN and os.name == "nt":
    # Best-effort only; decoding will report import errors if any
    with contextlib.suppress(Exception):
        os.add_dll_directory(_LIBVIPS_BIN)


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
    if image.bands > 3:
        image = image.extract_band(0, 3)
    elif image.bands < 3:
        image = pyvips.Image.bandjoin([image] * 3)
    if image.format != "uchar":
        image = image.cast("uchar")

    mem = image.write_to_memory()
    array = np.frombuffer(mem, dtype=np.uint8).reshape(image.height, image.width, image.bands)
    array = array.copy()
    with contextlib.suppress(Exception):
        del image
    if array.shape[2] != 3:
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
