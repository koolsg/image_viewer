import sys

# Use the crop dev helper to avoid instantiating the legacy UI in automation.
sys.path.insert(0, r"c:\Projects\image_viewer")
from image_viewer.crop.dev_helpers import make_test_pixmap


pm = make_test_pixmap(64, 48, 0x112233)

print("Created test pixmap; size=", pm.size())
