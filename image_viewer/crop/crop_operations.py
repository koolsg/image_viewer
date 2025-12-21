"""Crop workflow operations.

Bridges UI and backend for crop functionality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from image_viewer.logger import get_logger

from .crop import apply_crop_to_file
from .ui_crop import CropDialog

if TYPE_CHECKING:
    from image_viewer.main import ImageViewer

_logger = get_logger("crop_operations")


def start_crop_workflow(viewer: ImageViewer) -> None:
    """Start crop workflow from current displayed image.

    Args:
        viewer: Main ImageViewer instance
    """
    # Get current image
    if not viewer.image_files or viewer.current_index < 0:
        QMessageBox.warning(viewer, "No Image", "No image is currently displayed.")
        return

    current_path = viewer.image_files[viewer.current_index]

    # Get cached pixmap
    pixmap = viewer.engine.get_cached_pixmap(current_path)
    if pixmap is None:
        _logger.warning("No cached pixmap available for %s", current_path)
        QMessageBox.warning(viewer, "Error", "Could not load image from cache.")
        return

    _logger.debug("Starting crop workflow for: %s", current_path)

    # Open crop dialog
    dialog = CropDialog(viewer, current_path, pixmap)
    result = dialog.exec()
    _logger.debug("Crop dialog closed for %s, exec() returned %s", current_path, result)
    if result:
        # Check if user saved
        save_info = dialog.get_save_info()
        if save_info:
            crop_rect, save_path = save_info
            _logger.debug("User requested save: %s crop=%s", save_path, crop_rect)
            save_cropped_file(viewer, current_path, crop_rect, save_path)
        else:
            _logger.debug("Dialog accepted but no save info for %s", current_path)
    else:
        _logger.debug("User cancelled crop dialog for %s", current_path)


def save_cropped_file(
    viewer: ImageViewer,
    source_path: str,
    crop_rect: tuple[int, int, int, int],
    output_path: str,
) -> None:
    """Save cropped image to file.

    Args:
        viewer: Main ImageViewer instance
        source_path: Original image path
        crop_rect: (left, top, width, height) crop rectangle
        output_path: Destination file path
    """
    try:
        _logger.info("Saving cropped image: %s -> %s", source_path, output_path)

        # Use backend to perform crop and save
        result_path = apply_crop_to_file(source_path, crop_rect, output_path)

        # Show success message
        QMessageBox.information(
            viewer,
            "Crop Saved",
            f"Cropped image saved successfully to:\n{result_path}",
        )

        _logger.info("Crop saved successfully: %s", result_path)

        # Update engine caches and state
        try:
            viewer.engine.cancel_pending(source_path)
            viewer.engine.prefetch([result_path], None)
            _logger.debug("Requested engine cache update for new crop: %s", result_path)
        except Exception:
            _logger.debug("Engine cache update skipped or failed for %s", result_path, exc_info=True)

    except Exception as e:
        _logger.error("Failed to save crop: %s", e, exc_info=True)
        QMessageBox.critical(
            viewer,
            "Save Failed",
            f"Failed to save cropped image:\n{e}",
        )
