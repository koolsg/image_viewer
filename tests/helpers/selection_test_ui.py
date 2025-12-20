"""Test-only selection UI harness used by unit tests.

Provides a small window with a simple pixmap and a SelectionRectItem (from ui_crop)
that logs detailed debug messages to `ui_crop_test` logger for press/move/release of selection
and its handles.
"""
from __future__ import annotations

from typing import Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem, QVBoxLayout, QWidget

from image_viewer.ui_crop import SelectionRectItem
from image_viewer.logger import get_logger

_logger = get_logger("ui_crop_test")


class _DummyMouseEvent:
    """Minimal event with scenePos used by test simulations."""

    def __init__(self, x: float, y: float):
        self._pt = QPointF(float(x), float(y))

    def scenePos(self):
        return self._pt

    def button(self):
        # Simulate left-button press by default
        return Qt.LeftButton

    def accept(self):
        return None


class TestSelectionRectItem(SelectionRectItem):
    """Thin wrapper that exposes handles and adds logging for test introspection."""

    def get_handle(self, idx: int):
        return self._handles[idx]

    def mousePressEvent(self, event) -> None:  # type: ignore
        try:
            scene_pt = event.scenePos()
            view = self.scene().views()[0] if self.scene() and self.scene().views() else None
            view_pt = view.mapFromScene(scene_pt) if view is not None else None
            _logger.debug(
                "Selection mousePress: scene=(%.1f,%.1f) view=(%s,%s) view_rect=%s",
                float(scene_pt.x()),
                float(scene_pt.y()),
                getattr(view_pt, "x", lambda: None)() if view_pt is not None else None,
                getattr(view_pt, "y", lambda: None)() if view_pt is not None else None,
                getattr(self, "_view_rect", None),
            )
        except Exception:
            _logger.exception("Selection mousePress: logging failed")
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore
        try:
            scene_pt = event.scenePos()
            view = self.scene().views()[0] if self.scene() and self.scene().views() else None
            view_pt = view.mapFromScene(scene_pt) if view is not None else None
            _logger.debug(
                "Selection mouseMove: scene=(%.1f,%.1f) view=(%s,%s)",
                float(scene_pt.x()),
                float(scene_pt.y()),
                getattr(view_pt, "x", lambda: None)() if view_pt is not None else None,
                getattr(view_pt, "y", lambda: None)() if view_pt is not None else None,
            )
        except Exception:
            _logger.exception("Selection mouseMove: logging failed")
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore
        try:
            scene_pt = event.scenePos()
            view = self.scene().views()[0] if self.scene() and self.scene().views() else None
            view_pt = view.mapFromScene(scene_pt) if view is not None else None
            _logger.debug(
                "Selection mouseRelease: scene=(%.1f,%.1f) view=(%s,%s)",
                float(scene_pt.x()),
                float(scene_pt.y()),
                getattr(view_pt, "x", lambda: None)() if view_pt is not None else None,
                getattr(view_pt, "y", lambda: None)() if view_pt is not None else None,
            )
        except Exception:
            _logger.exception("Selection mouseRelease: logging failed")
        super().mouseReleaseEvent(event)

    def attach_handle_loggers(self) -> None:
        """Attach wrappers to handle events to log handle activity via ui_crop_test logger."""
        for h in getattr(self, "_handles", []):
            orig_press = h.mousePressEvent
            orig_move = h.mouseMoveEvent
            orig_release = h.mouseReleaseEvent

            def make_wrapper(orig, label, h=h):
                def wrapper(event):
                    try:
                        scene_pt = event.scenePos()
                        view = None
                        if self.scene() and self.scene().views():
                            view = self.scene().views()[0]
                        view_pt = view.mapFromScene(scene_pt) if view is not None else None
                        _logger.debug(
                            "Handle %s idx=%s scene=(%.1f,%.1f) view=(%s,%s)",
                            label,
                            getattr(h, "_index", None),
                            float(scene_pt.x()),
                            float(scene_pt.y()),
                            getattr(view_pt, "x", lambda: None)() if view_pt is not None else None,
                            getattr(view_pt, "y", lambda: None)() if view_pt is not None else None,
                        )
                    except Exception:
                        _logger.exception("Handle %s logging failed", label)
                    return orig(event)

                return wrapper

            h.mousePressEvent = make_wrapper(orig_press, "mousePress")
            h.mouseMoveEvent = make_wrapper(orig_move, "mouseMove")
            h.mouseReleaseEvent = make_wrapper(orig_release, "mouseRelease")


class SelectionTestWindow(QWidget):
    """Small test window containing a view, a pixmap, and a selection that can be moved/resized."""

    def __init__(self, w: int = 200, h: int = 150, parent=None):
        super().__init__(parent)
        app = QApplication.instance() or QApplication([])
        self._scene = QGraphicsScene(self)
        self.view = QGraphicsView(self._scene)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setCursor(Qt.CrossCursor)
        self.view.viewport().setCursor(Qt.CrossCursor)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view)

        # Simple pixmap for deterministic tests
        img = QImage(w, h, QImage.Format.Format_RGB888)
        img.fill(0x112233)
        pix = QPixmap.fromImage(img)
        self._pix_item = QGraphicsPixmapItem(pix)
        self._scene.addItem(self._pix_item)

        # Selection (test subclass)
        self.selection = TestSelectionRectItem(self._pix_item)
        initial_parent_rect = QRectF(w * 0.25, h * 0.25, w * 0.5, h * 0.5)
        self.selection.set_parent_rect(initial_parent_rect)
        # attach handle loggers so we get detailed handle events
        self.selection.attach_handle_loggers()

        # Make window size deterministic and show
        self.setMinimumSize(320, 240)

        # ESC shortcut to close demo quickly and reliably
        try:
            from PySide6.QtGui import QShortcut, QKeySequence

            QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.close)
        except Exception:
            _logger.debug("ESC shortcut not available in this environment", exc_info=True)

        self.show()
        _logger.debug("SelectionTestWindow created w=%s h=%s", w, h)

    def keyPressEvent(self, event) -> None:  # type: ignore
        """Allow ESC to close the window and log the action."""
        try:
            from PySide6.QtCore import Qt as _Qt

            if event.key() == _Qt.Key_Escape:  # pragma: no cover - interactive behavior
                _logger.info("SelectionTestWindow: ESC pressed, closing")
                self.close()
                return
        except Exception:
            _logger.debug("Failed to handle key press", exc_info=True)
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore
        _logger.info("SelectionTestWindow: closed by user or shortcut")
        super().closeEvent(event)

    # Deterministic simulator for handle drags
    def simulate_handle_drag(self, idx: int, start: Tuple[float, float], end: Tuple[float, float], intermediate: Sequence[Tuple[float, float]] | None = None) -> None:
        """Simulate press-move-release on a handle using scene coordinates.

        All coordinates are in scene space (pixmap at origin so parent coords == scene coords).
        """
        _logger.debug("simulate_handle_drag: idx=%s start=%s end=%s", idx, start, end)
        h = self.selection.get_handle(idx)

        # Press
        h.mousePressEvent(_DummyMouseEvent(*start))

        # Moves
        if intermediate:
            for pt in intermediate:
                h.mouseMoveEvent(_DummyMouseEvent(*pt))

        h.mouseMoveEvent(_DummyMouseEvent(*end))

        # Release
        h.mouseReleaseEvent(_DummyMouseEvent(*end))
        _logger.debug("simulate_handle_drag: finished idx=%s final_end=%s", idx, end)


    def simulate_selection_drag(self, start: Tuple[float, float], end: Tuple[float, float]) -> None:
        """Simulate clicking and dragging the selection interior in scene coords."""
        _logger.debug("simulate_selection_drag: start=%s end=%s", start, end)
        # Use SelectionRectItem.mousePressEvent/mouseMoveEvent with dummy scene events
        self.selection.mousePressEvent(_DummyMouseEvent(*start))
        self.selection.mouseMoveEvent(_DummyMouseEvent(*end))
        self.selection.mouseReleaseEvent(_DummyMouseEvent(*end))
        _logger.debug("simulate_selection_drag: finished start=%s end=%s", start, end)
