import os
from typing import Tuple, Optional

# --- Optional .env support to load LIBVIPS_BIN for Windows child processes ---
from typing import Optional, Tuple
from .logger import get_logger

_logger = get_logger("decoder")

def _load_env_file(env_path: str = ".env") -> None:
    try:
        if not os.path.exists(env_path):
            return
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k and v and k not in os.environ:
                    os.environ[k] = v
    except (OSError, UnicodeError) as e:
        # .env 로드 실패는 치명적이지 않음
        _logger.debug("env load skipped: %s", e)

_load_env_file()
_LIBVIPS_BIN = os.environ.get("LIBVIPS_BIN")
if _LIBVIPS_BIN and os.name == "nt":
    try:
        os.add_dll_directory(_LIBVIPS_BIN)
    except Exception:
        # Best-effort only; decoding will report import errors if any
        pass


def _decode_with_pyvips_from_file(path: str,
                                  target_width: Optional[int] = None,
                                  target_height: Optional[int] = None,
                                  size: str = "both") -> "np.ndarray":
    """Decode arbitrary image bytes into an RGB numpy array using pyvips."""
    try:
        import pyvips  # type: ignore
        try:
            pyvips.cache_set_max(0)
            pyvips.cache_set_max_mem(0)
            pyvips.cache_set_max_files(0)
        except Exception:
            pass
    except Exception as exc:
        raise RuntimeError(f"PyVips not available: {exc}") from exc
    try:
        import numpy as np  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"NumPy not available: {exc}") from exc

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

    try:
        image = image.copy_memory()
    except Exception:
        pass
    try:
        image = image.colourspace("srgb")
    except Exception:
        pass
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
    try:
        del image
    except Exception:
        pass
    if array.shape[2] != 3:
        raise RuntimeError(f"Unsupported band count after conversion: {array.shape[2]}")
    return array


def decode_image(file_path: str,
                 target_width: Optional[int] = None,
                 target_height: Optional[int] = None,
                 size: str = "both") -> Tuple[str, Optional[object], Optional[str]]:
    """Decode image from file path into an RGB numpy array using pyvips only.

    Returns (path, array|None, error|None).
    """
    try:
        array = _decode_with_pyvips_from_file(file_path, target_width, target_height, size)
        return file_path, array, None
    except Exception as e:
        _logger.debug("decode failed: %s", e)
        return file_path, None, str(e)
