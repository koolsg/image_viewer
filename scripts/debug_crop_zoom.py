"""Debug script to test crop dialog pointer-centered zoom."""

import logging
import sys
from pathlib import Path

from image_viewer.crop.ui_crop import CropDialog
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

# Add the project to the path
sys.path.insert(0, str(Path(__file__).parent))


def debug_crop_zoom():
    """Test the crop dialog zoom with debug output."""

    app = QApplication(sys.argv)

    # Create a simple test image
    test_image = QPixmap(800, 600)
    test_image.fill(QColor(255, 0, 0))  # Red background

    # Create crop dialog
    dialog = CropDialog(None, "test_image.jpg", test_image)

    # Set up debug logging to see what happens during wheel events
    logging.basicConfig(level=logging.DEBUG)

    # Override the _handle_wheel_event to add debug output
    original_handle = dialog._handle_wheel_event

    def debug_handle_wheel_event(event):
        print(f"Wheel event received: angleDelta={event.angleDelta().y()}")

        viewport_pt = dialog._get_viewport_point_from_event(event)
        print(f"Viewport point: {viewport_pt}")

        try:
            scene_before = dialog._view.mapToScene(viewport_pt)
            print(f"Scene before: {scene_before}")
        except Exception as e:
            print(f"Error mapping to scene before: {e}")
            scene_before = None

        new_scale = dialog._compute_new_scale(event)
        print(f"New scale: {new_scale}")

        if new_scale is not None:
            # Call the original method
            original_handle(event)

            try:
                scene_after = dialog._view.mapToScene(viewport_pt)
                print(f"Scene after: {scene_after}")
            except Exception as e:
                print(f"Error mapping to scene after: {e}")
        else:
            print("No zoom action required")

    dialog._handle_wheel_event = debug_handle_wheel_event

    dialog.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    debug_crop_zoom()
