import sys

sys.path.insert(0, r"c:\Projects\image_viewer")
from image_viewer.crop.ui_crop import CropDialog
from PySide6.QtGui import QImage, QPixmap

img = QImage(64, 48, QImage.Format.Format_RGB888)
img.fill(0x112233)
pm = QPixmap.fromImage(img)

try:
    dlg = CropDialog(None, "/test/path", pm)
    print("Created dialog; has _setup_ui:", hasattr(dlg, "_setup_ui"))
    try:
        dlg._setup_ui()
        print("setup_ui succeeded")
        print("has preview_btn?", hasattr(dlg, "preview_btn"))
    except Exception:
        import traceback

        traceback.print_exc()
except Exception:
    import traceback

    traceback.print_exc()
