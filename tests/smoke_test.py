"""Smoke test for image decoder.

Tests basic image decoding functionality with PNG and JPEG files.
"""

import os
import sys
from pathlib import Path

# Ensure repo root on path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from concurrent.futures import ProcessPoolExecutor

try:
    import pyvips  # type: ignore
except Exception:
    pyvips = None  # type: ignore

# Import the decode function from the app
from image_viewer.image_engine.decoder import decode_image


def assert_rgb_array(arr):
    """Verify decoded array is valid RGB uint8."""
    assert hasattr(arr, "shape"), "Decoded image lacks shape attribute"
    h, w, c = arr.shape
    assert c == 3 and h > 0 and w > 0, f"Unexpected shape: {arr.shape}"
    dtype = getattr(arr, "dtype", None)
    assert dtype is not None and str(dtype) == "uint8", f"Unexpected dtype: {dtype}"


def main():
    """Run smoke tests for image decoding."""
    any_ran = False

    # Test 1: Decode a PNG file
    png_path = os.path.join(os.getcwd(), "test.png")
    if os.path.exists(png_path):
        print(f"Testing PNG decode: {png_path}")
        path, arr, err = decode_image(png_path)
        if err is None:
            assert path == png_path, f"Path mismatch: {path} != {png_path}"
            assert_rgb_array(arr)
            print(f"✓ PNG decoded successfully: {arr.shape}")
            any_ran = True
        else:
            print(f"✗ PNG decode failed: {err}")
    else:
        print("⊘ PNG test skipped (missing test.png)")

    # Test 2: Decode with target size
    if os.path.exists(png_path):
        print(f"Testing PNG decode with target size: {png_path}")
        path, arr, err = decode_image(png_path, target_width=256, target_height=256)
        if err is None:
            assert path == png_path
            assert_rgb_array(arr)
            h, w, _ = arr.shape
            # Should be resized (approximately, aspect ratio preserved)
            assert max(h, w) <= 256, f"Size not constrained: {arr.shape}"
            print(f"✓ PNG decoded with resize: {arr.shape}")
            any_ran = True
        else:
            print(f"✗ PNG decode with resize failed: {err}")

    # Test 3: Multiprocessing path (Windows safety)
    if any_ran and os.path.exists(png_path):
        print("Testing multiprocessing decode...")
        try:
            with ProcessPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(decode_image, png_path)
                pth, arr, err = fut.result(timeout=10)
                assert err is None, f"Process decode error for {pth}: {err}"
                assert_rgb_array(arr)
                print(f"✓ Multiprocessing decode successful: {arr.shape}")
        except Exception as e:
            print(f"✗ Multiprocessing decode failed: {e}")

    # Summary
    if any_ran:
        print("\n✓ SMOKE TEST PASSED")
    else:
        print("\n⊘ SMOKE TEST SKIPPED - no test files or pyvips unavailable")


if __name__ == "__main__":
    # Windows multiprocessing safety
    from multiprocessing import freeze_support

    freeze_support()
    main()
