from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QFrame
from typing import Optional
from .logger import get_logger

_logger = get_logger("ui_canvas")


# NOTE: 이 파일은 기존 main.py의 ImageCanvas 클래스를 그대로 이동했습니다.
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
        self._press_zoom_multiplier = 2.0
        self._rotation = 0.0
        # 우클릭 드래그용 상태
        self._rc_drag_active = False
        self._rc_drag_start_view = None
        self._rc_drag_start_h = 0
        self._rc_drag_start_v = 0

        self.setRenderHints(self.renderHints())
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    # 이하 메서드들은 기존 main.py의 구현을 참조합니다.
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
                parent = self.parent()
                if angle > 0 and hasattr(parent, "prev_image"):
                    parent.prev_image()
                    event.accept()
                elif angle < 0 and hasattr(parent, "next_image"):
                    parent.next_image()
                    event.accept()
                else:
                    super().wheelEvent(event)
        except Exception as ex:
            _logger.debug("wheelEvent fallback due to error: %s", ex)
            try:
                super().wheelEvent(event)
            except Exception:
                pass

    def mousePressEvent(self, event) -> None:
        try:
            btn = event.button() if hasattr(event, "button") else None
            btns = event.buttons() if hasattr(event, "buttons") else None
        except Exception as ex:
            _logger.debug("mousePressEvent button read error: %s", ex)
            btn = None
            btns = None
        # 우클릭: 스크롤바가 있다면 수동 패닝 모드 진입 (레거시 동작 유지)
        if (btn == Qt.RightButton) or (btns is not None and (btns & Qt.RightButton)):
            try:
                hbar = self.horizontalScrollBar()
                vbar = self.verticalScrollBar()
                h_scroll = hbar.maximum() > 0
                v_scroll = vbar.maximum() > 0
            except Exception:
                h_scroll = v_scroll = False
            if h_scroll or v_scroll:
                self._rc_drag_active = True
                try:
                    if hasattr(event, "position"):
                        posf = event.position()
                        view_qpoint = posf.toPoint() if hasattr(posf, "toPoint") else None
                        if view_qpoint is None:
                            from PySide6.QtCore import QPoint
                            view_qpoint = QPoint(int(posf.x()), int(posf.y()))
                    else:
                        view_qpoint = event.pos() if hasattr(event, "pos") else None
                except Exception:
                    view_qpoint = None
                self._rc_drag_start_view = view_qpoint
                self._rc_drag_start_h = hbar.value()
                self._rc_drag_start_v = vbar.value()
                try:
                    event.accept()
                except Exception:
                    pass
                return
        # 중클릭: 전역 보기로 스냅 (레거시 동작 유지)
        if (btn == Qt.MiddleButton) or (btns is not None and (btns & Qt.MiddleButton)):
            parent = self.parent()
            if hasattr(parent, "snap_to_global_view"):
                try:
                    parent.snap_to_global_view()
                    event.accept()
                    return
                except Exception:
                    pass
        # 보조 버튼: 확대/축소 (레거시 매핑 유지)
        xbtn1 = getattr(Qt, 'XButton1', None)
        xbtn2 = getattr(Qt, 'XButton2', None)
        if (xbtn1 is not None) and ((btn == xbtn1) or (btns is not None and (btns & xbtn1))):
            try:
                self.zoom_by(0.8)
                event.accept()
                return
            except Exception:
                pass
        if (xbtn2 is not None) and ((btn == xbtn2) or (btns is not None and (btns & xbtn2))):
            try:
                self.zoom_by(1.25)
                event.accept()
                return
            except Exception:
                pass
        # 좌클릭: 프레스-줌 (레거시 동작: 커서 기준 확대 및 복원 지원)
        if (btn == Qt.LeftButton) and self._zoom_saved is None:
            try:
                # 현재 프리셋 저장 후 기준 배율 계산
                self._preset_before_press = getattr(self, "_preset_mode", "fit")
                baseline = self.get_fit_scale() if self._preset_before_press == "fit" else float(self._zoom)
            except Exception:
                self._preset_before_press = getattr(self, "_preset_mode", "fit")
                baseline = 1.0
            mul = getattr(self, "_press_zoom_multiplier", 2.0)
            try:
                mul = float(mul)
                if abs(mul) < 1e-6:
                    mul = 2.0
            except Exception:
                mul = 2.0
            self._zoom_saved = float(baseline)

            # 커서 위치 계산 (뷰 좌표 → 씬 → 아이템)
            view_qpoint = None
            try:
                if hasattr(event, "position"):
                    posf = event.position()
                    if hasattr(posf, "toPoint"):
                        view_qpoint = posf.toPoint()
                    else:
                        from PySide6.QtCore import QPoint
                        view_qpoint = QPoint(int(posf.x()), int(posf.y()))
                elif hasattr(event, "pos"):
                    view_qpoint = event.pos()
            except Exception:
                view_qpoint = None

            scene_pt = self.mapToScene(view_qpoint) if view_qpoint is not None else None
            item_pt = self._pix_item.mapFromScene(scene_pt) if scene_pt is not None else None

            # 실제 모드로 전환 후 확대 적용
            self._preset_mode = "actual"
            self._zoom = max(0.05, min(float(baseline) * float(mul), 20.0))
            self.apply_current_view()

            # 커서 정렬: 확대 후에도 같은 지점을 커서 아래에 유지 (레거시와 동등)
            if item_pt is not None and view_qpoint is not None:
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
                    try:
                        self.centerOn(new_scene_pt)
                    except Exception:
                        pass
            try:
                parent = self.parent()
                if hasattr(parent, "_update_status"):
                    parent._update_status()
            except Exception:
                pass
            return
        try:
            super().mousePressEvent(event)
        except Exception:
            pass

    def mouseMoveEvent(self, event):
        if getattr(self, "_rc_drag_active", False):
            try:
                if hasattr(event, "position"):
                    posf = event.position()
                    view_qpoint = posf.toPoint() if hasattr(posf, "toPoint") else None
                    if view_qpoint is None:
                        from PySide6.QtCore import QPoint
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
        try:
            super().mouseMoveEvent(event)
        except Exception:
            pass

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
            try:
                event.accept()
            except Exception:
                pass
            return
        try:
            super().mouseReleaseEvent(event)
        except Exception:
            pass

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
        # -360~360 범위로 정리 (과도 누적 방지)
        try:
            while self._rotation <= -360.0:
                self._rotation += 360.0
            while self._rotation > 360.0:
                self._rotation -= 360.0
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
        else:
            if abs(self._zoom - 1.0) > 1e-6:
                self.scale(self._zoom, self._zoom)
        try:
            parent = self.parent()
            if hasattr(parent, "_update_status"):
                parent._update_status()
        except Exception:
            pass

    def drawForeground(self, painter, rect):
        try:
            parent = self.parent()
            title = getattr(parent, "_overlay_title", "")
            info = getattr(parent, "_overlay_info", "")
            if not title and not info:
                return
            painter.save()
            painter.resetTransform()
            bg = getattr(parent, "_bg_color", None)
            from math import pow

            def rel_lum(c: QColor) -> float:
                r = c.red() / 255.0
                g = c.green() / 255.0
                b = c.blue() / 255.0
                def f(u):
                    return pow((u + 0.055) / 1.055, 2.4) if u > 0.04045 else (u / 12.92)
                rL, gL, bL = f(r), f(g), f(b)
                return 0.2126 * rL + 0.7152 * gL + 0.0722 * bL

            text_color = QColor(255, 255, 255)
            try:
                if isinstance(bg, QColor):
                    text_color = QColor(0, 0, 0) if rel_lum(bg) > 0.5 else QColor(255, 255, 255)
            except Exception:
                pass
            painter.setPen(text_color)
            margin = 8
            x = margin
            y = margin + 14
            from PySide6.QtGui import QFont
            font = QFont()
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(x, y, title)
            painter.drawText(x, y + 18, info)
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

        if self._hq_pixmap is not None and self._hq_pixmap.width() == tw and self._hq_pixmap.height() == th:
            self._pix_item.setPixmap(self._hq_pixmap)
            self.fitInView(self._pix_item, Qt.KeepAspectRatio)
            return

        try:
            qimg = pix.toImage().convertToFormat(QImage.Format_RGB888)
            width, height = qimg.width(), qimg.height()
            bpl = qimg.bytesPerLine()
            import numpy as np
            buf = qimg.bits().tobytes()
            if len(buf) < bpl * height:
                self.fitInView(self._pix_item, Qt.KeepAspectRatio)
                return
            arr = np.frombuffer(buf, dtype=np.uint8).reshape((height, bpl))[:, : (width * 3)]
            arr = arr.reshape((height, width, 3))
            arr = np.ascontiguousarray(arr)
            try:
                import pyvips  # type: ignore
            except Exception:
                self.fitInView(self._pix_item, Qt.KeepAspectRatio)
                return
            try:
                vips_img = pyvips.Image.new_from_memory(arr.tobytes(), width, height, 3, "uchar")
                scale_x = tw / width
                scale_y = th / height
                vips_resized = vips_img.resize(scale_x, kernel="lanczos3", vscale=scale_y)
                mem = vips_resized.write_to_memory()
                arr2 = np.frombuffer(mem, dtype=np.uint8).reshape(
                    vips_resized.height, vips_resized.width, vips_resized.bands
                )
            except Exception:
                self.fitInView(self._pix_item, Qt.KeepAspectRatio)
                return
            if arr2.shape[2] != 3:
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
