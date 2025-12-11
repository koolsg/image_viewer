import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import numpy as np
    import pyvips
    from PIL import Image

    HAS_DEPS = True
except Exception:
    HAS_DEPS = False

from image_viewer.trim import apply_trim_to_file, detect_trim_box_stats


class TestApplyTrimToFile(unittest.TestCase):
    @unittest.skipIf(not HAS_DEPS, "pyvips/PIL/numpy not available")
    def test_apply_trim_writes_cropped_dimensions(self):
        # Create an image with white background and black rectangle
        img = (np.ones((100, 120, 3), dtype=np.uint8) * 255).copy()
        # black rectangle from (20, 10) to (99, 89) (x: left..right, y: top..bottom)
        img[10:90, 20:100] = 0

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            Image.fromarray(img).save(f.name)
            path = f.name

        try:
            crop = detect_trim_box_stats(path, profile="normal")
            self.assertIsNotNone(crop, "Crop should be detected")
            _left, _top, width, height = crop

            out_path = apply_trim_to_file(path, crop, overwrite=False)

            # Read output via pyvips and verify dimensions
            out_img = pyvips.Image.new_from_file(out_path, access="sequential")
            self.assertEqual(out_img.width, width)
            self.assertEqual(out_img.height, height)
        finally:
            for p in (path, out_path):
                with contextlib.suppress(Exception):
                    os.remove(p)


if __name__ == "__main__":
    unittest.main()
