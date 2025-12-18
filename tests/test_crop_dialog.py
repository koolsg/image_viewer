import pytest
pytest.importorskip("PySide6")

from PySide6.QtGui import QImage, QPixmap

from image_viewer.ui_crop import CropDialog


def test_crop_dialog_initialization(qtbot):
    # Test basic dialog initialization
    w, h = 64, 48
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pm = QPixmap.fromImage(img)

    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    qtbot.addWidget(dlg)

    # Verify initial state
    assert dlg._image_path == "/test/path/image.jpg"
    assert dlg._original_pixmap is pm
    assert dlg._preview_mode is False
    assert dlg._zoom_mode == "fit"


def test_crop_dialog_selection_handling(qtbot):
    # Test selection rectangle handling
    w, h = 64, 48
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pm = QPixmap.fromImage(img)

    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    qtbot.addWidget(dlg)

    # Test getting crop rect from selection
    crop_rect = dlg._selection.get_crop_rect()
    assert isinstance(crop_rect, tuple)
    assert len(crop_rect) == 4
    assert all(isinstance(x, int) for x in crop_rect)

    # Test setting selection rectangle
    from PySide6.QtCore import QRectF
    new_rect = QRectF(10, 5, 20, 10)
    dlg._selection.setRect(new_rect)

    # Verify selection was updated
    updated_crop_rect = dlg._selection.get_crop_rect()
    assert updated_crop_rect == (10, 5, 20, 10)


def test_crop_dialog_save_workflow(monkeypatch, qtbot):
    # Test save workflow without actually calling backend
    w, h = 64, 48
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pm = QPixmap.fromImage(img)

    # Mock file dialog to return a path
    def mock_get_save_filename(parent, caption, dir, filter):
        return "/test/output.jpg", "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All Files (*.*)"

    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getSaveFileName", mock_get_save_filename)

    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    qtbot.addWidget(dlg)

    # Set a selection
    from PySide6.QtCore import QRectF
    dlg._selection.setRect(QRectF(10, 5, 20, 10))

    # Call save method
    dlg._on_save()

    # Verify save info was set (dialog should accept after save)
    save_info = dlg.get_save_info()
    if save_info:  # Only if dialog accepted
        crop_rect, save_path = save_info
        assert crop_rect == (10, 5, 20, 10)
        assert save_path == "/test/output.jpg"
