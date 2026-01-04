import pytest
import numpy as np

# Skip the test if pyvips is not available in this environment.
pytest.importorskip("pyvips")

from image_viewer.image_engine.engine_core import EngineCore


def test_vips_encode_odd_width():
    w = 3
    h = 5
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    # Fill with a simple gradient to avoid an all-black PNG that might be
    # aggressively optimized by some encoders.
    for x in range(w):
        arr[:, x, 0] = int(255 * x / max(1, w - 1))
        arr[:, x, 1] = int(255 * (w - 1 - x) / max(1, w - 1))

    out = EngineCore._numpy_to_png_bytes_vips(arr)
    assert out.startswith(b"\x89PNG"), "output does not start with PNG signature"
    assert len(out) > 64
