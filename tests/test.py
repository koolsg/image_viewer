import sys
import os
import traceback

LIBVIPS_BIN = r"C:\Projects\libraries\vips-dev-8.17\bin"

def ensure_libvips_bin():
    if os.name == "nt":
        try:
            os.add_dll_directory(LIBVIPS_BIN)
            print(f"[INFO] Added DLL directory: {LIBVIPS_BIN}")
        except Exception as e:
            print(f"[WARN] add_dll_directory failed: {e}")

def print_env_info():
    print("--- ENV INFO ---")
    print(f"Python: {sys.executable}")
    try:
        import pyvips
        print(f"pyvips version: {getattr(pyvips, '__version__', 'unknown')}")
    except Exception as e:
        print(f"pyvips import failed: {e}")
        sys.exit(1)
    try:
        import pyvips
        v = getattr(pyvips, "vips_version", None)
        if callable(v):
            print(f"libvips version: {pyvips.vips_version()}")
    except Exception as e:
        print(f"[WARN] libvips version check failed: {e}")

def try_thumbnail_all(path: str, target_w: int = 1280, target_h: int = 720) -> bool:
    import pyvips
    print("\n--- thumbnail tests ---")
    print(f"input: {path}")
    # 1) option_string (most compatible)
    try:
        opt = f"height={target_h} size=both crop=centre"
        print(f">>> option_string: width={target_w}, option_string='{opt}'")
        im = pyvips.Image.thumbnail(path, target_w, option_string=opt)
        print(f"OK option_string -> {im.width}x{im.height}")
        return True
    except Exception as e:
        print(f"option_string failed: {e}")
    # 2) kwargs (preferred on recent pyvips/libvips)
    try:
        print(f">>> kwargs: width={target_w}, height={target_h}, size='both', crop='centre'")
        im = pyvips.Image.thumbnail(path, target_w, height=target_h, size="both", crop="centre")
        print(f"OK kwargs -> {im.width}x{im.height}")
        return True
    except Exception as e:
        print(f"kwargs failed: {e}")
    # 3) width-only fallback
    try:
        print(f">>> width-only: width={target_w}")
        im = pyvips.Image.thumbnail(path, target_w)
        print(f"OK width-only -> {im.width}x{im.height}")
        return True
    except Exception as e:
        print(f"width-only failed: {e}")
    return False

def main():
    if len(sys.argv) < 2:
        print("usage: python test.py <image_path>")
        sys.exit(2)
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"file not found: {path}")
        sys.exit(2)
    ensure_libvips_bin()
    print_env_info()
    try:
        ok = try_thumbnail_all(path)
        print("\nresult:", "OK" if ok else "FAIL")
    except Exception:
        print("fatal error:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
