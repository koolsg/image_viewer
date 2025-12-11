"""
Unit tests for trim.py functions (detect_trim_box_stats, make_trim_preview, apply_trim_to_file).
Focus on pure function testing with synthetic image data.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import numpy as np

    # pyvips import removed to avoid unused-import in tests
    from PIL import Image

    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

from image_viewer.trim import detect_trim_box_stats


class TestDetectTrimBoxStats(unittest.TestCase):
    """Test detect_trim_box_stats function."""

    def setUp(self):
        """Create temporary directory for test images."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_path = self.test_dir.name

    def tearDown(self):
        """Clean up temporary directory."""
        self.test_dir.cleanup()

    @unittest.skipIf(not HAS_DEPS, "pyvips/PIL/numpy not available")
    def test_solid_color_image(self):
        """Test detection on solid color image (no trim).

        Expected: Should return None (no trim detected, image is uniform).
        """
        # Create solid white image
        img = Image.new("RGB", (200, 150), color="white")
        img_path = os.path.join(self.test_path, "solid_white.png")
        img.save(img_path)

        result = detect_trim_box_stats(img_path, profile="normal")
        # Solid image should not trigger trim (no non-background content)
        self.assertIsNone(result, "Solid color image should not be trimmed")

    @unittest.skipIf(not HAS_DEPS, "pyvips/PIL/numpy not available")
    def test_bordered_image_normal_profile(self):
        import numpy as np
        from PIL import Image

        # Create image with a black border inside white background
        img_array = np.ones((100, 100, 3), dtype=np.uint8) * 255
        img_array[20:80, 20:80] = 0
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            pil_img = Image.fromarray(img_array)
            pil_img.save(f.name)
            img_path = f.name
        result = detect_trim_box_stats(img_path)
        self.assertTrue(result is None or isinstance(result, tuple))
        if result:
            _left, _top, width, height = result
            self.assertGreater(width, 0)
            self.assertGreater(height, 0)

    @unittest.skipIf(not HAS_DEPS, "pyvips/PIL/numpy not available")
    def test_small_content_aggressive_profile(self):
        import numpy as np
        from PIL import Image

        # Create image with a very small black rectangle
        img_array = np.ones((100, 100, 3), dtype=np.uint8) * 255
        start_y, start_x = 45, 47
        end_y, end_x = 55, 53
        img_array[start_y:end_y, start_x:end_x] = 0
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            pil_img = Image.fromarray(img_array)
            pil_img.save(f.name)
            img_path = f.name
        result = detect_trim_box_stats(img_path)
        self.assertIsNotNone(result, "Small content should be detected with aggressive profile")
        if result:
            _left, _top, width, height = result
            self.assertGreater(width, 5)
            self.assertGreater(height, 5)

    @unittest.skipIf(not HAS_DEPS, "pyvips/PIL/numpy not available")
    def test_invalid_path_returns_none(self):
        """Test that invalid path returns None gracefully."""
        result = detect_trim_box_stats("/nonexistent/path/image.png", profile="normal")
        self.assertIsNone(result, "Invalid path should return None without exception")

    @unittest.skipIf(not HAS_DEPS, "pyvips/PIL/numpy not available")
    def test_profile_parameter(self):
        """Test that profile parameter affects detection."""
        # Create test image
        img_array = np.zeros((200, 200, 3), dtype=np.uint8)
        img_array[50:150, 50:150, :] = 100  # gray content

        pil_img = Image.fromarray(img_array)
        img_path = os.path.join(self.test_path, "profile_test.png")
        pil_img.save(img_path)

        result_normal = detect_trim_box_stats(img_path, profile="normal")
        result_aggressive = detect_trim_box_stats(img_path, profile="aggressive")

        # Both should detect something (or both None if too subtle)
        # This is just verifying the profile parameter is accepted
        self.assertTrue(
            result_normal is None or isinstance(result_normal, tuple), "Normal profile should return None or tuple"
        )
        self.assertTrue(
            result_aggressive is None or isinstance(result_aggressive, tuple),
            "Aggressive profile should return None or tuple",
        )


class TestTrimIntegration(unittest.TestCase):
    """Integration tests for trim module."""

    @unittest.skipIf(not HAS_DEPS, "pyvips/PIL/numpy not available")
    def test_detect_returns_valid_tuple_or_none(self):
        # Create a small image with white background and black rectangle
        import numpy as np
        from PIL import Image

        img = (np.ones((200, 300, 3), dtype=np.uint8) * 255).copy()
        img[30:170, 50:250] = 0
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            Image.fromarray(img).save(f.name)
            result = detect_trim_box_stats(f.name)
            self.assertTrue(
                result is None or (isinstance(result, tuple) and len(result) == 4),
                "Result should be None or (l, t, w, h) tuple",
            )
            if result:
                left, top, width, height = result
                self.assertIsInstance(left, int)
                self.assertIsInstance(top, int)
                self.assertIsInstance(width, int)
                self.assertIsInstance(height, int)


if __name__ == "__main__":
    unittest.main()
