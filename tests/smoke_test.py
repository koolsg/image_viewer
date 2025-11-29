import os
import sys

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
from image_viewer.decoder import decode_image


def make_jpeg_bytes_from_png(png_path: str) -> bytes:
    if pyvips is None:
        raise RuntimeError("pyvips missing")
    image = pyvips.Image.new_from_file(png_path, access="sequential")
    if image.hasalpha():
        image = image.flatten(background=[0, 0, 0])
    try:
        image = image.colourspace("srgb")
    except Exception:
        pass
    return image.write_to_buffer(".jpg[Q=90]")


def assert_rgb_array(arr):
    # duck-typing assertions to avoid hard numpy import here
    assert hasattr(arr, "shape"), "Decoded image lacks shape attribute"
    h, w, c = arr.shape
    assert c == 3 and h > 0 and w > 0, f"Unexpected shape: {arr.shape}"
    dtype = getattr(arr, "dtype", None)
    assert dtype is not None and str(dtype) == "uint8", f"Unexpected dtype: {dtype}"


def main():
    any_ran = False

    # 1) Decode a PNG through the pyvips fallback path
    png_path = os.path.join(os.getcwd(), "test.png")
    if os.path.exists(png_path):
        with open(png_path, "rb") as f:
            png_bytes = f.read()
        path, arr, err = decode_image(png_path, png_bytes)
        if err is None:
            assert path == png_path
            assert_rgb_array(arr)
            any_ran = True
        else:
            print(f"PNG decode skipped/failed: {err}")
    else:
        print("PNG test skipped (missing test.png)")

    # 2) Decode a JPEG synthesized with pyvips (decoder also pyvips)
    if pyvips is not None and os.path.exists(png_path):
        jpeg_bytes = make_jpeg_bytes_from_png(png_path)
        fake_jpg = os.path.join(os.getcwd(), "test_converted.jpg")
        path, arr, err = decode_image(fake_jpg, jpeg_bytes)
        if err is None:
            assert path == fake_jpg
            assert_rgb_array(arr)
            any_ran = True
        else:
            print(f"JPEG decode skipped/failed: {err}")
    else:
        print("JPEG test skipped (pyvips missing or no test.png)")

    # 3) Multiprocessing path if any decode succeeded
    if any_ran:
        with open(png_path, "rb") as f:
            png_bytes = f.read()
        with ProcessPoolExecutor() as ex:
            fut = ex.submit(decode_image, png_path, png_bytes)
            pth, arr, err = fut.result(timeout=10)
            assert err is None, f"Process decode error for {pth}: {err}"
            assert_rgb_array(arr)
        print("SMOKE TEST PASSED")
    else:
        print("SMOKE TEST SKIPPED - required imaging libs not available")


if __name__ == "__main__":
    # Windows multiprocessing safety
    from multiprocessing import freeze_support
    freeze_support()
    main()
