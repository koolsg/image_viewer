import io
import os
from typing import Tuple, Optional
dll_path = r'C:\libjpeg-turbo64\bin\turbojpeg.dll'
os.environ['TURBOJPEG_DLL_PATH'] = dll_path
try:
    from turbojpeg import TurboJPEG  # type: ignore
except Exception:  # TurboJPEG is optional at runtime
    TurboJPEG = None  # type: ignore


jpeg_decoder = None
if TurboJPEG is not None:
    try:
        jpeg_decoder = TurboJPEG()  # fast JPEG path when available
    except Exception:
        jpeg_decoder = None


def decode_image(file_path: str, file_bytes: bytes) -> Tuple[str, Optional[object], Optional[str]]:
    """Decode image bytes into an RGB numpy array.

    Falls back to Pillow for JPEG if TurboJPEG is unavailable.
    Returns (path, array|None, error|None).
    """
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".jpg", ".jpeg"] and jpeg_decoder is not None:
            bgr_array = jpeg_decoder.decode(file_bytes)  # uint8 BGR
            rgb_array = bgr_array[..., ::-1]
            return file_path, rgb_array, None
        else:
            try:
                from PIL import Image  # lazy import
            except Exception:
                return file_path, None, "Pillow not available for decoding"
            try:
                import numpy as np  # lazy import
            except Exception:
                return file_path, None, "NumPy not available for decoding"
            with Image.open(io.BytesIO(file_bytes)) as img:
                img_rgb = img.convert("RGB")
                return file_path, np.array(img_rgb), None
    except Exception as e:
        return file_path, None, str(e)
