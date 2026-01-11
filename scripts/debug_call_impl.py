import sys

# A lightweight script that avoids creating the legacy CropDialog and instead
# demonstrates the backend crop helper usage.
sys.path.insert(0, r"c:\Projects\image_viewer")
from image_viewer.crop.dev_helpers import make_test_pixmap, apply_crop_to_tempfile

pm = make_test_pixmap(64, 48, 0x112233)
print("Created test pixmap; size=", pm.size())

# Demonstrate apply_crop_to_tempfile (writes to temp file via backend)
out = apply_crop_to_tempfile("/nonexistent/source.png", (0, 0, 10, 10))
print("Crop output written to:", out)
