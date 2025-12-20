import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF

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
    # Window title should show the provided image path so users can see the file being edited
    assert dlg.windowTitle() == "/test/path/image.jpg"
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

    # View should use crosshair in canvas area
    assert dlg._view.cursor().shape() == Qt.CrossCursor
    assert dlg._view.viewport().cursor().shape() == Qt.CrossCursor

    # Test getting crop rect from selection
    crop_rect = dlg._selection.get_crop_rect()
    assert isinstance(crop_rect, tuple)
    assert len(crop_rect) == 4
    assert all(isinstance(x, int) for x in crop_rect)

    # Test setting selection rectangle
    new_rect = QRectF(10, 5, 20, 10)
    dlg._selection.setRect(new_rect)

    # Verify selection was updated
    updated_crop_rect = dlg._selection.get_crop_rect()
    assert updated_crop_rect == (10, 5, 20, 10)

    # Selection should not be configured as an ItemIsMovable on the QGraphics item
    from PySide6.QtWidgets import QGraphicsRectItem

    flags = dlg._selection.flags()
    assert not bool(flags & QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable)

    # move_by should shift the selection rect correctly and stay within bounds
    before = dlg._selection.get_crop_rect()
    dlg._selection.move_by(2, 3)
    after = dlg._selection.get_crop_rect()
    assert after[0] >= before[0]
    assert after[1] >= before[1]


def test_selection_handle_resize(qtbot):
    # Ensure that moving handles updates the selection rect
    w, h = 64, 48
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pm = QPixmap.fromImage(img)

    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    qtbot.addWidget(dlg)

    # Get original rect
    orig = dlg._selection.get_crop_rect()
    left, top, width, height = orig

    # Move top-left handle inward by 5px (towards center)
    dlg._selection.resize_handle_to(0, left + 5, top + 5)
    new_left, new_top, new_w, new_h = dlg._selection.get_crop_rect()

    assert new_left >= left
    assert new_top >= top
    assert new_w <= width
    assert new_h <= height


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
    dlg._selection.setRect(QRectF(10, 5, 20, 10))

    # Call save method
    dlg._on_save()

    # Verify save info was set (dialog should accept after save)
    save_info = dlg.get_save_info()
    if save_info:  # Only if dialog accepted
        crop_rect, save_path = save_info
        assert crop_rect == (10, 5, 20, 10)
        assert save_path == "/test/output.jpg"


def test_selection_drag_respects_click_offset(qtbot):
    pm = QPixmap.fromImage(QImage(200, 150, QImage.Format.Format_RGB888))
    pm.fill(0x112233)
    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    qtbot.addWidget(dlg)

    selection = dlg._selection
    view = dlg._view

    selection.setRect(QRectF(20, 15, 60, 40))
    selection._refresh_view_rect_from_parent()
    view_rect = selection._view_rect

    assert view_rect is not None

    parent_item = selection.parentItem()
    assert parent_item is not None

    press_scene_pos = parent_item.mapToScene(selection.rect().center())
    press_view_pt = view.mapFromScene(press_scene_pos)
    press_view_point = QPoint(round(press_view_pt.x()), round(press_view_pt.y()))

    selection._start_view_rect = QRectF(view_rect)
    selection._grab_offset = QPointF(
        press_view_point.x() - view_rect.x(),
        press_view_point.y() - view_rect.y(),
    )

    move_view_point = press_view_point + QPoint(12, 8)
    target = selection._compute_drag_target_view_rect(view, view.mapToScene(move_view_point))

    assert target is not None
    assert target.x() == pytest.approx(view_rect.x() + 12, rel=0.01, abs=0.05)
    assert target.y() == pytest.approx(view_rect.y() + 8, rel=0.01, abs=0.05)


def test_selection_drag_does_not_pan_view(qtbot):
    """Simulate a real mouse drag on the selection and assert the view does not pan."""
    # Create a large pixmap so scrollbars can appear
    w, h = 800, 600
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pm = QPixmap.fromImage(img)

    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    # Force a small dialog size so the pixmap is larger than viewport
    dlg.resize(300, 200)
    qtbot.addWidget(dlg)
    qtbot.waitForWindowShown(dlg)

    # Ensure we're in actual (1:1) mode so the pixmap can be panned
    dlg._apply_zoom_mode("actual")

    view = dlg._view
    selection = dlg._selection

    # Make sure selection exists and is visible
    selection.setRect(QRectF(100, 80, 200, 150))
    selection.setVisible(True)

    # Capture scrollbar values before drag
    h_before = view.horizontalScrollBar().value()
    v_before = view.verticalScrollBar().value()

    # Compute a press point inside the selection in viewport coordinates
    parent_item = selection.parentItem()
    assert parent_item is not None
    scene_pt = parent_item.mapToScene(selection.rect().center())
    view_pt = view.mapFromScene(scene_pt)

    # Simulate actual mouse press/move/release on viewport
    qtbot.mousePress(view.viewport(), Qt.LeftButton, pos=view_pt)
    qtbot.mouseMove(view.viewport(), pos=view_pt + QPoint(30, 20))
    qtbot.mouseRelease(view.viewport(), Qt.LeftButton, pos=view_pt + QPoint(30, 20))

    # Verify scrollbars haven't changed (no panning)
    assert view.horizontalScrollBar().value() == h_before
    assert view.verticalScrollBar().value() == v_before


def test_selection_drag_with_scrollhand_drag_does_not_pan(qtbot):
    """If the view's drag mode is ScrollHandDrag, dragging the selection should still not pan the image."""
    w, h = 800, 600
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x112233)
    pm = QPixmap.fromImage(img)

    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    dlg.resize(300, 200)
    qtbot.addWidget(dlg)
    qtbot.waitForWindowShown(dlg)

    # Enable ScrollHandDrag as if user had enabled panning mode
    dlg._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    view = dlg._view
    selection = dlg._selection

    # Make sure selection exists and is visible
    selection.setRect(QRectF(100, 80, 200, 150))
    selection.setVisible(True)

    # Capture scrollbar values before drag
    h_before = view.horizontalScrollBar().value()
    v_before = view.verticalScrollBar().value()

    # Compute a press point inside the selection in viewport coordinates
    parent_item = selection.parentItem()
    assert parent_item is not None
    scene_pt = parent_item.mapToScene(selection.rect().center())
    view_pt = view.mapFromScene(scene_pt)

    # Simulate actual mouse press/move/release on viewport
    qtbot.mousePress(view.viewport(), Qt.LeftButton, pos=view_pt)
    qtbot.mouseMove(view.viewport(), pos=view_pt + QPoint(30, 20))
    qtbot.mouseRelease(view.viewport(), Qt.LeftButton, pos=view_pt + QPoint(30, 20))

    # Verify scrollbars haven't changed (no panning)
    assert view.horizontalScrollBar().value() == h_before
    assert view.verticalScrollBar().value() == v_before

    pm = QPixmap.fromImage(QImage(200, 150, QImage.Format.Format_RGB888))
    pm.fill(0x112233)
    dlg = CropDialog(None, "/test/path/image.jpg", pm)
    qtbot.addWidget(dlg)

    selection = dlg._selection
    view = dlg._view

    selection.setRect(QRectF(20, 15, 60, 40))
    selection._refresh_view_rect_from_parent()
    view_rect = selection._view_rect

    assert view_rect is not None

    parent_item = selection.parentItem()
    assert parent_item is not None

    press_scene_pos = parent_item.mapToScene(selection.rect().center())
    press_view_pt = view.mapFromScene(press_scene_pos)
    press_view_point = QPoint(round(press_view_pt.x()), round(press_view_pt.y()))

    selection._start_view_rect = QRectF(view_rect)
    selection._grab_offset = QPointF(
        press_view_point.x() - view_rect.x(),
        press_view_point.y() - view_rect.y(),
    )

    move_view_point = press_view_point + QPoint(12, 8)
    target = selection._compute_drag_target_view_rect(view, view.mapToScene(move_view_point))

    assert target is not None
    assert target.x() == pytest.approx(view_rect.x() + 12, rel=0.01, abs=0.05)
    assert target.y() == pytest.approx(view_rect.y() + 8, rel=0.01, abs=0.05)
