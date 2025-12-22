import sys

sys.path.insert(0, r"c:\Projects\image_viewer")
import image_viewer.crop.ui_crop as impl
from image_viewer.crop.ui_crop import CropDialog
from PySide6.QtGui import QImage, QPixmap

img = QImage(64, 48, QImage.Format.Format_RGB888)
img.fill(0x112233)
pm = QPixmap.fromImage(img)

dlg = CropDialog(None, "/test/path", pm)
print("Before call, has preview_btn:", hasattr(dlg, "preview_btn"))
# Call impl._create_left_panel directly
try:
    panel = impl._create_left_panel(dlg)
    print("panel created, has preview_btn now:", hasattr(dlg, "preview_btn"))
    # inspect some attrs
    print("fit_btn present:", hasattr(dlg, "fit_btn"))
    if hasattr(dlg, "fit_btn"):
        print("fit_btn checked:", dlg.fit_btn.isChecked())
except Exception:
    import traceback

    traceback.print_exc()

# Now call impl._setup_ui
try:
    impl._setup_ui(dlg)
    print("after _setup_ui, has preview_btn:", hasattr(dlg, "preview_btn"))
except Exception:
    import traceback

    traceback.print_exc()
