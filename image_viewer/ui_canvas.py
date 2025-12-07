# NOTE: This file contains the ImageCanvas class moved from main.py.
import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from .logger import get_logger

try:
    import pyvips  # type: ignore
except Exception:
    pyvips = None  # type: ignore
import contextlib
from math import pow

_logger = get_logger("ui_canvas")

# Constants for rotation normalization
ROTATION_MAX = 360.0
ROTATION_MIN = -360.0

# Floating point comparison tolerance
FLOAT_EPSILON = 1e-6

# Luminance threshold for text color contrast
LUMINANCE_THRESHOLD = 0.5

# sRGB linearization threshold
SRGB_LINEAR_THRESHOLD = 0.04045

# File size thresholds for display formatting
KB_THRESHOLD = 1024
MB_THRESHOLD = 1024 * 1024

# Image channel count
RGB_CHANNELS = 3


class ImageCanvas(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pix_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pix_item)
        try:
            self.setFrameShape(QFrame.NoFrame)
            self.setFrameShadow(QFrame.Plain)
            self.setLineWidth(0)
            self.setViewportMargins(0, 0, 0, 0)
            self.setStyleSheet("QGraphicsView { border: none; }")
        except Exception:
            pass
        self._zoom = 1.0
        self._preset_mode = "fit"
        self._hq_downscale = False
        self._hq_pixmap = None
        self._zoom_saved = None
        self._press_zoom_multiplier = 3.0
        self._rotation = 0.0
        # Right-click drag state
        self._rc_drag_active = False
        self._rc_drag_start_view = None
        self._rc_drag_start_h = 0
        self._rc_drag_start_v = 0

        self.setRenderHints(self.renderHints())
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    # The following methods reference the implementation in main.py.
    def get_fit_scale(self) -> float:
        pix = self._pix_item.pixmap()
        if pix.isNull():
            return 1.0
        pw = max(1, pix.width())
        ph = max(1, pix.height())
        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())
        sx = vw / pw
        sy = vh / ph
        return min(sx, sy)

    def get_current_scale_factor(self) -> float:
        try:
            if self._preset_mode == "fit":
                return float(self.get_fit_scale())
            return float(self._zoom)
        except Exception:
            return 1.0

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pix_item.setPixmap(pixmap)
        self._pix_item.setOffset(0, 0)
        self._rotation = 0.0
        try:
            pm_rect = QRectF(pixmap.rect())
            self._pix_item.setTransformOriginPoint(pm_rect.center())
            self._pix_item.setRotation(self._rotation)
            self._scene.setSceneRect(pm_rect)
        except Exception:
            self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._hq_pixmap = None
        self.apply_current_view()

    def wheelEvent(self, event) -> None:
        if self._pix_item.pixmap().isNull():
            return
        try:
            if event.modifiers() & Qt.ControlModifier:
                angle = event.angleDelta().y()
                factor = 1.25 if angle > 0 else 0.8
                self.zoom_by(factor)
            else:
                angle = event.angleDelta().y()
                viewer = self.window()
                if angle > 0 and hasattr(viewer, "prev_image"):
                    viewer.prev_image()
                    event.accept()
                elif angle < 0 and hasattr(viewer, "next_image"):
                    viewer.next_image()
                    event.accept()
                else:
                    super().wheelEvent(event)
        except Exception as ex:
            _logger.debug("wheelEvent fallback due to error: %s", ex)
            with contextlib.suppress(Exception):
                super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        try:
            key = event.key() if hasattr(event, "key") else None
        except Exception:
            key = None
        if key in (Qt.Key_Left, Qt.Key_Right):
            viewer = self.window()
            try:
                if key == Qt.Key_Left and hasattr(viewer, "prev_image"):
                    viewer.prev_image()
                    event.accept()
                    return
                if key == Qt.Key_Right and hasattr(viewer, "next_image"):
                    viewer.next_image()
                    event.accept()
                    return
            except Exception:
                pass
        with contextlib.suppress(Exception):
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        try:
            btn = event.button() if hasattr(event, "button") else None
            btns = event.buttons() if hasattr(event, "buttons") else None
        except Exception as ex:
            _logger.debug("mousePressEvent button read error: %s", ex)
            btn = None
            btns = None

        # Dispatch to button-specific handlers
        if (btn == Qt.RightButton) or (btns is not None and (btns & Qt.RightButton)):
            if self._handle_right_click(event):
                return
        elif (btn == Qt.MiddleButton) or (btns is not None and (btns & Qt.MiddleButton)):
            if self._handle_middle_click(event):
                return
        elif self._handle_auxiliary_buttons(btn, btns, event) or (btn == Qt.LeftButton and self._zoom_saved is None and self._handle_left_click(event)):
            return

        with contextlib.suppress(Exception):
            super().mousePressEvent(event)

    def _handle_right_click(self, event) -> bool:
        """Handle right-click: Enter manual panning mode if scrollbar exists."""
        try:
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()
            h_scroll = hbar.maximum() > 0
            v_scroll = vbar.maximum() > 0
        except Exception:
            return False

        if not (h_scroll or v_scroll):
            return False

        self._rc_drag_active = True
        view_qpoint = self._get_event_position(event)
        self._rc_drag_start_view = view_qpoint
        self._rc_drag_start_h = hbar.value()
        self._rc_drag_start_v = vbar.value()
        with contextlib.suppress(Exception):
            event.accept()
        return True

    def _handle_middle_click(self, event) -> bool:
        """Handle middle-click: Snap to global view."""
        viewer = self.window()
        if hasattr(viewer, "snap_to_global_view"):
            try:
                viewer.snap_to_global_view()
                event.accept()
                return True
            except Exception:
                pass
        return False

    def _handle_auxiliary_buttons(self, btn, btns, event) -> bool:
        """Handle auxiliary mouse buttons (XButton1/XButton2) for zoom."""
        xbtn1 = getattr(Qt, "XButton1", None)
        xbtn2 = getattr(Qt, "XButton2", None)

        if xbtn1 is not None and ((btn == xbtn1) or (btns is not None and (btns & xbtn1))):
            try:
                self.zoom_by(0.8)
                event.accept()
                return True
            except Exception:
                pass

        if xbtn2 is not None and ((btn == xbtn2) or (btns is not None and (btns & xbtn2))):
            try:
                self.zoom_by(1.25)
                event.accept()
                return True
            except Exception:
                pass

        return False

    def _handle_left_click(self, event) -> bool:
        """Handle left-click: Press-to-zoom at cursor position."""
        try:
            self._preset_before_press = getattr(self, "_preset_mode", "fit")
            baseline = self.get_fit_scale() if self._preset_before_press == "fit" else float(self._zoom)
        except Exception:
            self._preset_before_press = getattr(self, "_preset_mode", "fit")
            baseline = 1.0

        mul = self._get_zoom_multiplier()
        self._zoom_saved = float(baseline)

        # Calculate cursor position (view coords -> scene -> item)
        view_qpoint = self._get_event_position(event)
        scene_pt = self.mapToScene(view_qpoint) if view_qpoint is not None else None
        item_pt = self._pix_item.mapFromScene(scene_pt) if scene_pt is not None else None

        # Switch to actual mode and apply zoom
        self._preset_mode = "actual"
        self._zoom = max(0.05, min(float(baseline) * float(mul), 20.0))
        self.apply_current_view()

        # Align cursor: keep the same point under the cursor after zooming
        self._align_cursor_after_zoom(item_pt, view_qpoint)

        try:
            parent = self.parent()
            if hasattr(parent, "_update_status"):
                parent._update_status()
        except Exception:
            pass
        return True

    def _get_event_position(self, event) -> QPoint | None:
        """Extract QPoint position from mouse event."""
        try:
            if hasattr(event, "position"):
                posf = event.position()
                if hasattr(posf, "toPoint"):
                    return posf.toPoint()
                return QPoint(int(posf.x()), int(posf.y()))
            elif hasattr(event, "pos"):
                return event.pos()
        except Exception:
            pass
        return None

    def _get_zoom_multiplier(self) -> float:
        """Get the press-zoom multiplier value."""
        mul = getattr(self, "_press_zoom_multiplier", 2.0)
        try:
            mul = float(mul)
            if abs(mul) < FLOAT_EPSILON:
                mul = 2.0
        except Exception:
            mul = 2.0
        return mul

    def _align_cursor_after_zoom(self, item_pt, view_qpoint) -> None:
        """Align view so the same point stays under cursor after zoom."""
        if item_pt is None or view_qpoint is None:
            return
        try:
            new_scene_pt = self._pix_item.mapToScene(item_pt)
            new_view_pt = self.mapFromScene(new_scene_pt)
            delta_x = int(new_view_pt.x() - view_qpoint.x())
            delta_y = int(new_view_pt.y() - view_qpoint.y())
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()
            hbar.setValue(hbar.value() + delta_x)
            vbar.setValue(vbar.value() + delta_y)
        except Exception:
            with contextlib.suppress(Exception):
                self.centerOn(self._pix_item.mapToScene(item_pt))

    def mouseMoveEvent(self, event):
        if getattr(self, "_rc_drag_active", False):
            try:
                if hasattr(event, "position"):
                    posf = event.position()
                    view_qpoint = posf.toPoint() if hasattr(posf, "toPoint") else None
                    if view_qpoint is None:
                        # QPoint imported at module top

                        view_qpoint = QPoint(int(posf.x()), int(posf.y()))
                else:
                    view_qpoint = event.pos() if hasattr(event, "pos") else None
                if self._rc_drag_start_view is not None and view_qpoint is not None:
                    dx = int(view_qpoint.x() - self._rc_drag_start_view.x())
                    dy = int(view_qpoint.y() - self._rc_drag_start_view.y())
                    hbar = self.horizontalScrollBar()
                    vbar = self.verticalScrollBar()
                    hbar.setValue(int(self._rc_drag_start_h) - dx)
                    vbar.setValue(int(self._rc_drag_start_v) - dy)
                event.accept()
                return
            except Exception:
                pass
        with contextlib.suppress(Exception):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        try:
            btn = event.button() if hasattr(event, "button") else None
        except Exception:
            btn = None
        if btn == Qt.LeftButton and (self._zoom_saved is not None):
            self._zoom = float(self._zoom_saved)
            self._zoom_saved = None
            prev = getattr(self, "_preset_before_press", None)
            if prev is not None:
                self._preset_mode = prev
                self._preset_before_press = None
            self.apply_current_view()
            return
        if btn == Qt.RightButton and getattr(self, "_rc_drag_active", False):
            self._rc_drag_active = False
            with contextlib.suppress(Exception):
                event.accept()
            return
        with contextlib.suppress(Exception):
            super().mouseReleaseEvent(event)

    def is_fit(self) -> bool:
        return self._preset_mode == "fit"

    def zoom_by(self, factor: float):
        try:
            # Fit 모드에서는 실제 배율 기준으로 전환하여 확대/축소가 보이도록 처리
            if self._preset_mode == "fit":
                baseline = self.get_fit_scale()
                self._preset_mode = "actual"
                self._zoom = float(baseline) * float(factor)
                self._zoom = max(0.05, min(20.0, self._zoom))
                self.apply_current_view()
                return
            # Actual 모드에서는 현재 배율에 곱하고 적용
            self._zoom *= float(factor)
            self._zoom = max(0.05, min(20.0, self._zoom))
            self.apply_current_view()
        except Exception:
            pass

    def reset_zoom(self):
        self._zoom = 1.0
        self.apply_current_view()

    def rotate_by(self, degrees: float):
        try:
            self._rotation = float(self._rotation) + float(degrees)
        except Exception:
            try:
                self._rotation = float(degrees)
            except Exception:
                self._rotation = 0.0
        # Normalize to -360~360 range (to prevent excessive accumulation)
        try:
            while self._rotation <= ROTATION_MIN:
                self._rotation += ROTATION_MAX
            while self._rotation > ROTATION_MAX:
                self._rotation -= ROTATION_MAX
        except Exception:
            pass
        self.apply_current_view()

    def apply_current_view(self):
        pix = self._pix_item.pixmap()
        if pix.isNull():
            return
        self.resetTransform()
        try:
            pm_rect = QRectF(pix.rect())
            self._pix_item.setTransformOriginPoint(pm_rect.center())
            self._pix_item.setRotation(self._rotation)
            br = self._pix_item.mapRectToScene(pm_rect)
            self._scene.setSceneRect(br)
        except Exception:
            pass
        if self._preset_mode == "fit":
            if self._hq_downscale:
                self._apply_hq_fit()
            else:
                self.fitInView(self._pix_item, Qt.KeepAspectRatio)
        elif abs(self._zoom - 1.0) > FLOAT_EPSILON:
            self.scale(self._zoom, self._zoom)
        try:
            viewer = self.window()
            if hasattr(viewer, "_update_status"):
                viewer._update_status()
        except Exception:
            pass

    def drawForeground(self, painter, rect):
        try:
            # Since ImageViewer can be inside a QStackedWidget, read overlay info from window() instead of parent().
            viewer = self.window()
            title = getattr(viewer, "_overlay_title", "")
            info = getattr(viewer, "_overlay_info", "")
            if not title and not info:
                return
            painter.save()
            painter.resetTransform()
            bg = getattr(viewer, "_bg_color", None)

            def rel_lum(c: QColor) -> float:
                r = c.red() / 255.0
                g = c.green() / 255.0
                b = c.blue() / 255.0

                def f(u):
                    return pow((u + 0.055) / 1.055, 2.4) if u > SRGB_LINEAR_THRESHOLD else (u / 12.92)

                rL, gL, bL = f(r), f(g), f(b)
                return 0.2126 * rL + 0.7152 * gL + 0.0722 * bL

            text_color = QColor(255, 255, 255)
            try:
                if isinstance(bg, QColor):
                    text_color = QColor(0, 0, 0) if rel_lum(bg) > LUMINANCE_THRESHOLD else QColor(255, 255, 255)
            except Exception:
                pass
            painter.setPen(text_color)
            margin = 8
            x = margin
            y = margin + 14

            font = QFont()
            font.setPointSize(10)
            painter.setFont(font)

            # Measure text to draw background
            fm = painter.fontMetrics()
            title_w = fm.horizontalAdvance(title)
            info_w = fm.horizontalAdvance(info)
            line_h = fm.height()

            box_w = max(title_w, info_w) + 20
            box_h = (line_h * 2) + 10

            # Draw semi-transparent background
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 128))
            painter.drawRoundedRect(8, 8, box_w, box_h, 6, 6)

            # Draw text
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(18, 8 + line_h, title)
            painter.drawText(18, 8 + line_h * 2, info)

            # Debug-only cache summary (View mode): show cached pixmaps and sizes
            try:
                debug_enabled = logging.getLogger("image_viewer").isEnabledFor(
                    logging.DEBUG
                )
            except Exception:
                debug_enabled = False
            is_view_mode = bool(
                getattr(getattr(viewer, "explorer_state", None), "view_mode", True)
            )
            if debug_enabled and is_view_mode:
                cache = getattr(viewer, "pixmap_cache", None)
                if cache:
                    rows = []

                    def _fmt_size(num: int) -> str:
                        if num >= MB_THRESHOLD:
                            return f"{num / MB_THRESHOLD:.1f} MB"
                        if num >= KB_THRESHOLD:
                            return f"{num / KB_THRESHOLD:.1f} KB"
                        return f"{num} B"

                    for path, pix in list(cache.items()):
                        try:
                            size_bytes = pix.toImage().sizeInBytes()
                        except Exception:
                            try:
                                size_bytes = max(
                                    0, pix.width() * pix.height() * 4
                                )
                            except Exception:
                                size_bytes = 0
                        name = Path(path).name
                        rows.append((name, size_bytes))

                    if rows:
                        y_tab = y + 36
                        painter.drawText(x, y_tab, "Cache (pixmap_cache)")
                        y_tab += 16
                        mono = QFont("Consolas")
                        mono.setPointSize(9)
                        painter.setFont(mono)
                        for name, size_bytes in rows:
                            lines = [name, f"{_fmt_size(size_bytes)}"]
                            for line in lines:
                                painter.drawText(x, y_tab, line)
                                y_tab += 14
                        painter.setFont(font)
            painter.restore()
        except Exception:
            pass

    def _apply_hq_fit(self):
        pix = self._pix_item.pixmap()
        if pix.isNull():
            return
        vw, vh = self.viewport().width(), self.viewport().height()
        pw, ph = pix.width(), pix.height()
        if vw <= 0 or vh <= 0 or pw <= 0 or ph <= 0:
            self.fitInView(self._pix_item, Qt.KeepAspectRatio)
            return
        sx = vw / pw
        sy = vh / ph
        scale = min(sx, sy)
        tw, th = max(1, int(pw * scale)), max(1, int(ph * scale))

        if (
            self._hq_pixmap is not None
            and self._hq_pixmap.width() == tw
            and self._hq_pixmap.height() == th
        ):
            self._pix_item.setPixmap(self._hq_pixmap)
            self.fitInView(self._pix_item, Qt.KeepAspectRatio)
            return

        try:
            qimg = pix.toImage().convertToFormat(QImage.Format_RGB888)
            width, height = qimg.width(), qimg.height()
            bpl = qimg.bytesPerLine()
            # numpy imported at module top

            buf = qimg.bits().tobytes()
            if len(buf) < bpl * height:
                self.fitInView(self._pix_item, Qt.KeepAspectRatio)
                return
            arr = np.frombuffer(buf, dtype=np.uint8).reshape((height, bpl))[
                :, : (width * 3)
            ]
            arr = arr.reshape((height, width, 3))
            arr = np.ascontiguousarray(arr)
            try:
                # pyvips imported at module top (optional)
                pass
            except Exception:
                self.fitInView(self._pix_item, Qt.KeepAspectRatio)
                return
            try:
                vips_img = pyvips.Image.new_from_memory(
                    arr.tobytes(), width, height, 3, "uchar"
                )
                scale_x = tw / width
                scale_y = th / height
                vips_resized = vips_img.resize(
                    scale_x, kernel="lanczos3", vscale=scale_y
                )
                mem = vips_resized.write_to_memory()
                arr2 = np.frombuffer(mem, dtype=np.uint8).reshape(
                    vips_resized.height, vips_resized.width, vips_resized.bands
                )
            except Exception:
                self.fitInView(self._pix_item, Qt.KeepAspectRatio)
                return
            if arr2.shape[2] != RGB_CHANNELS:
                self.fitInView(self._pix_item, Qt.KeepAspectRatio)
                return
            h2, w2, _ = arr2.shape
            qimg2 = QImage(arr2.data, w2, h2, w2 * 3, QImage.Format_RGB888)
            new_pix = QPixmap.fromImage(qimg2)
            self._hq_pixmap = new_pix
            self._pix_item.setPixmap(new_pix)
            self._scene.setSceneRect(QRectF(new_pix.rect()))
            self.fitInView(self._pix_item, Qt.KeepAspectRatio)
        except Exception:
            self.fitInView(self._pix_item, Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._preset_mode == "fit":
            if self._hq_downscale:
                self._hq_pixmap = None
            self._zoom = self.get_fit_scale()
        self.apply_current_view()
