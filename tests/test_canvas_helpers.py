import pytest
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QImage

from image_viewer.ui_canvas import ImageCanvas


def test_canvas_pixmap_setting(qtbot):
    app = QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    qtbot.addWidget(canvas)

    w, h = 16, 12
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pix = QPixmap.fromImage(img)

    # Test setting pixmap
    canvas.set_pixmap(pix)

    # Verify pixmap was set
    assert canvas._pix_item.pixmap() is not None
    assert canvas._pix_item.pixmap().width() == w
    assert canvas._pix_item.pixmap().height() == h


def test_canvas_zoom_functionality(qtbot):
    app = QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    qtbot.addWidget(canvas)

    # Set a specific size for the canvas to ensure consistent behavior
    canvas.resize(400, 300)  # Set viewport size

    w, h = 32, 24
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pix = QPixmap.fromImage(img)
    canvas.set_pixmap(pix)

    # Initially in fit mode
    assert canvas._preset_mode == "fit"

    # Test zoom functionality
    canvas.zoom_by(2.0)

    # After zoom_by, should switch to actual mode
    assert canvas._preset_mode == "actual"
    # The zoom value should be based on fit scale * factor, clamped to max 20.0
    fit_scale = canvas.get_fit_scale()  # Should be around 300/24 = 12.5 or similar
    expected_zoom = min(fit_scale * 2.0, 20.0)
    assert canvas._zoom == expected_zoom

    # Test zoom reset
    canvas.reset_zoom()
    assert canvas._zoom == 1.0
    assert canvas._preset_mode == "actual"  # Should stay in actual mode
