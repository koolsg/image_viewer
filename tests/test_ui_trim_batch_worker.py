import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import numpy as np
    from PIL import Image

    HAS_DEPS = True
except Exception:
    HAS_DEPS = False

from image_viewer.ui_trim import TrimBatchWorker


class TestTrimBatchWorker(unittest.TestCase):
    @unittest.skipIf(not HAS_DEPS, "pyvips/PIL/numpy not available")
    def test_batch_worker_skips_full_size_crop(self):
        # Create an image that should detect a crop equal to the full image
        # A fully black image triggers a detection that covers the full extents
        img = (np.zeros((50, 60, 3), dtype=np.uint8)).copy()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            Image.fromarray(img).save(f.name)
            path = f.name

        try:
            worker = TrimBatchWorker([path], profile="normal")
            worker.run()
            # Check that no .trim file was created
            trim_path = os.path.splitext(path)[0] + ".trim" + os.path.splitext(path)[1]
            self.assertFalse(os.path.exists(trim_path), "Batch worker should skip creating identical .trim files")
        finally:
            for p in (path, os.path.splitext(path)[0] + ".trim" + os.path.splitext(path)[1]):
                with contextlib.suppress(Exception):
                    os.remove(p)

    @unittest.skipIf(not HAS_DEPS, "pyvips/PIL/numpy not available")
    def test_batch_worker_creates_trim_for_non_full_crop(self):
        # Create an image with a white background and central black rectangle
        img = (np.ones((60, 80, 3), dtype=np.uint8) * 255).copy()
        img[10:50, 20:70] = 0

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            Image.fromarray(img).save(f.name)
            path = f.name

        try:
            worker = TrimBatchWorker([path], profile="normal")
            worker.run()
            trim_path = os.path.splitext(path)[0] + ".trim" + os.path.splitext(path)[1]
            # Trim file should be created
            self.assertTrue(os.path.exists(trim_path), "Batch worker should create .trim file for a cropped image")
        finally:
            for p in (path, os.path.splitext(path)[0] + ".trim" + os.path.splitext(path)[1]):
                with contextlib.suppress(Exception):
                    os.remove(p)


if __name__ == "__main__":
    unittest.main()
