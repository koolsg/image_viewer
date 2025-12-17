import pytest
pytest.importorskip("PySide6")

from PySide6.QtGui import QImage, QPixmap

from image_viewer.ui_crop import CropDialog


def test_crop_dialog_save_calls_backend(monkeypatch, qtbot):
    # Create a small pixmap and use as initial pixmap
    w, h = 64, 48
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pm = QPixmap.fromImage(img)

    called = {}

    def fake_apply(path, rect, overwrite=False, dest_path=None):
        called['args'] = (path, rect, overwrite, dest_path)
        return "/tmp/fake.jpg"

    # Patch the symbol used by the dialog (imported into ui_crop module)
    monkeypatch.setattr("image_viewer.ui_crop.apply_crop_to_file", fake_apply)

    dlg = CropDialog(None, "unused", initial_pixmap=pm)
    qtbot.addWidget(dlg)

    # Set a programmatic selection and ensure it's present
    dlg.canvas.set_selection_rect((10, 5, 20, 10))
    assert dlg.canvas.get_selection_in_image_coords() == (10, 5, 20, 10)

    # Call save and assert backend called
    dlg._on_save()

    assert 'args' in called, 'apply_crop_to_file was not called'
    path, rect, overwrite, dest = called['args']
    assert rect == (10, 5, 20, 10)