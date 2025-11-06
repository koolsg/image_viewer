import sys
import os
import json
import threading
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from PySide6.QtCore import Qt, QObject, Signal, QRectF
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QFileDialog,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QFrame,
)
from PySide6.QtWidgets import QColorDialog
from PySide6.QtGui import QPixmap, QAction, QKeySequence, QImage, QShortcut, QActionGroup, QPainter, QColor


# --- Top-level function for the Process Pool ---
# multiprocessing에서 피클링 가능하도록 최상위에 유지되는 셔틀 함수
def decode_image(file_path, target_width=None, target_height=None, size="both"):
    from .decoder import decode_image as _decode
    return _decode(file_path, target_width, target_height, size)


class Loader(QObject):
    """백그라운드 로딩/디코딩 파이프라인 관리자."""

    image_decoded = Signal(str, object, object)  # path, numpy_array, error

    def __init__(self):
        super().__init__()
        self.executor = ProcessPoolExecutor()
        max_io = max(2, min(4, (os.cpu_count() or 2)))
        self.io_pool = ThreadPoolExecutor(max_workers=max_io)
        self._pending = set()
        self._ignored = set()
        self._next_id = 1
        self._latest_id = {}
        self._lock = threading.Lock()

    def _submit_decode(self, file_path: str, target_width: int | None, target_height: int | None, size: str = "both", req_id: int | None = None):
        try:
            future = self.executor.submit(decode_image, file_path, target_width, target_height, size)
            try:
                # Attach request metadata for staleness check
                setattr(future, "_req_id", req_id)
                setattr(future, "_path", file_path)
            except Exception:
                pass
            future.add_done_callback(self.on_decode_finished)
        except Exception as e:
            with self._lock:
                self._pending.discard(file_path)
            self.image_decoded.emit(file_path, None, str(e))

    def on_decode_finished(self, future):
        path, data, error = future.result()
        try:
            req_id = getattr(future, "_req_id", None)
        except Exception:
            req_id = None
        with self._lock:
            self._pending.discard(path)
            if path in self._ignored:
                return
            latest = self._latest_id.get(path)
            if latest is not None and req_id is not None and req_id != latest:
                return
        self.image_decoded.emit(path, data, error)

    def request_load(self, path, target_width: int | None = None, target_height: int | None = None, size: str = "both"):
        with self._lock:
            if path in self._pending or path in self._ignored:
                return
            self._pending.add(path)
            req_id = self._next_id
            self._next_id += 1
            self._latest_id[path] = req_id
        self.io_pool.submit(self._submit_decode, path, target_width, target_height, size, req_id)

    def ignore_path(self, path: str):
        """Mark path as ignored so late decode results are dropped and future submissions blocked."""
        with self._lock:
            self._ignored.add(path)
            self._pending.discard(path)
            try:
                self._latest_id.pop(path, None)
            except Exception:
                pass
    def unignore_path(self, path: str):
        """Remove path from ignored set to allow future submissions."""
        with self._lock:
            self._ignored.discard(path)

    def shutdown(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.io_pool.shutdown(wait=False, cancel_futures=True)  # type: ignore
        except TypeError:
            self.io_pool.shutdown(wait=False)


class ImageCanvas(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pix_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pix_item)
        # 뷰 프레임/여백 제거로 가장자리 테두리 방지
        try:
            self.setFrameShape(QFrame.NoFrame)
            self.setFrameShadow(QFrame.Plain)
            self.setLineWidth(0)
            self.setViewportMargins(0, 0, 0, 0)
            self.setStyleSheet("QGraphicsView { border: none; }")
        except Exception:
            pass
        # 줌 상태: 원본 픽셀 기준(1.0 = 실제 크기)
        self._zoom = 1.0
        # 프리셋(Fit/Actual) 기록: Space 스냅에 사용
        self._preset_mode = "fit"
        # HQ 다운스케일 옵션 및 캐시
        self._hq_downscale = False
        self._hq_pixmap = None
        # 프레스-줌 상태
        self._zoom_saved = None
        self._press_zoom_multiplier = 2.0
        # 회전 상태(도 단위, 시계 방향 양수)
        self._rotation = 0.0

        # 렌더 품질 설정
        self.setRenderHints(self.renderHints())
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

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
        """현재 뷰 배율(원본 픽스맵 대비)을 반환."""
        try:
            if self._preset_mode == "fit":
                return float(self.get_fit_scale())
            return float(self._zoom)
        except Exception:
            return 1.0

    def set_pixmap(self, pixmap: QPixmap):
        self._pix_item.setPixmap(pixmap)
        self._pix_item.setOffset(0, 0)
        # 새 이미지에서는 회전을 초기화
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

    def wheelEvent(self, event):
        if self._pix_item.pixmap().isNull():
            return
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

    def mousePressEvent(self, event):
        try:
            btn = event.button()
        except Exception:
            btn = None
        # 우클릭 드래그: 스크롤바가 있으면 수동 패닝
        if btn == Qt.RightButton:
            try:
                hbar = self.horizontalScrollBar()
                vbar = self.verticalScrollBar()
                h_scroll = hbar.maximum() > 0
                v_scroll = vbar.maximum() > 0
            except Exception:
                h_scroll = v_scroll = False
            if h_scroll or v_scroll:
                self._rc_drag_active = True
                view_pt = event.position() if hasattr(event, "position") else event.pos()
                self._rc_drag_start_view = view_pt
                self._rc_drag_start_h = hbar.value()
                self._rc_drag_start_v = vbar.value()
                event.accept()
                return
        # 중클릭: 전역 보기 스냅
        if btn == Qt.MiddleButton:
            parent = self.parent()
            if hasattr(parent, "snap_to_global_view"):
                parent.snap_to_global_view()
                event.accept()
                return
        # 좌클릭: 프레스-줌(커서 고정)
        if btn == Qt.LeftButton and self._zoom_saved is None:
            try:
                view_pt = event.position() if hasattr(event, "position") else event.pos()
            except Exception:
                view_pt = event.pos() if hasattr(event, "pos") else None
            scene_pt = self.mapToScene(view_pt.toPoint()) if view_pt is not None else None
            item_pt = self._pix_item.mapFromScene(scene_pt) if scene_pt is not None else None

            self._preset_before_press = getattr(self, "_preset_mode", "fit")
            # 실제 모드로 전환하되, 기준 배율은 '현재 보이는 배율'을 사용하여 항상 확대가 되도록 함
            baseline = self.get_fit_scale() if self._preset_before_press == "fit" else self._zoom
            self._preset_mode = "actual"
            self._zoom_saved = baseline
            mul = float(getattr(self, "_press_zoom_multiplier", 2.0) or 2.0)
            self._zoom = max(0.05, min(baseline * mul, 20.0))
            self.apply_current_view()

            if item_pt is not None and view_pt is not None:
                new_scene_pt = self._pix_item.mapToScene(item_pt)
                new_view_pt = self.mapFromScene(new_scene_pt)
                delta_x = int(new_view_pt.x() - view_pt.x())
                delta_y = int(new_view_pt.y() - view_pt.y())
                try:
                    hbar = self.horizontalScrollBar()
                    vbar = self.verticalScrollBar()
                    hbar.setValue(hbar.value() + delta_x)
                    vbar.setValue(vbar.value() + delta_y)
                except Exception:
                    self.centerOn(new_scene_pt)
            event.accept()
            super().mousePressEvent(event)
            return
        # 보조 버튼: 확대/축소
        if btn == Qt.XButton1:
            self.zoom_by(0.8)
            event.accept()
            return
        elif btn == Qt.XButton2:
            self.zoom_by(1.25)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_rc_drag_active", False):
            try:
                view_pt = event.position() if hasattr(event, "position") else event.pos()
                dx = int(view_pt.x() - self._rc_drag_start_view.x())
                dy = int(view_pt.y() - self._rc_drag_start_view.y())
                hbar = self.horizontalScrollBar()
                vbar = self.verticalScrollBar()
                hbar.setValue(self._rc_drag_start_h - dx)
                vbar.setValue(self._rc_drag_start_v - dy)
                event.accept()
                return
            except Exception:
                pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        try:
            btn = event.button()
        except Exception:
            btn = None
        if btn == Qt.LeftButton and (self._zoom_saved is not None):
            self._zoom = self._zoom_saved
            self._zoom_saved = None
            prev = getattr(self, "_preset_before_press", None)
            if prev is not None:
                self._preset_mode = prev
                self._preset_before_press = None
            self.apply_current_view()
            event.accept()
            super().mouseReleaseEvent(event)
            return
        if btn == Qt.RightButton and getattr(self, "_rc_drag_active", False):
            self._rc_drag_active = False
            event.accept()
            super().mouseReleaseEvent(event)
            return
        super().mouseReleaseEvent(event)

    def is_fit(self):
        return self._preset_mode == "fit"

    def fit_to_view(self):
        pix = self._pix_item.pixmap()
        if pix.isNull():
            return
        self._zoom = self.get_fit_scale()
        self.apply_current_view()

    def toggle_fit(self):
        self._preset_mode = "actual" if self._preset_mode == "fit" else "fit"
        if self._preset_mode == "fit":
            self._zoom = self.get_fit_scale()
        else:
            self._zoom = 1.0
        self.apply_current_view()

    def zoom_by(self, factor: float):
        self._preset_mode = "actual"
        self._zoom *= factor
        self._zoom = max(0.05, min(self._zoom, 20.0))
        self.apply_current_view()

    def reset_zoom(self):
        self._preset_mode = "actual"
        self._zoom = 1.0
        self.apply_current_view()

    def rotate_by(self, degrees: float):
        try:
            self._rotation = (self._rotation + float(degrees)) % 360.0
        except Exception:
            return
        # 회전 반영 및 뷰 갱신
        pm = self._pix_item.pixmap()
        if pm.isNull():
            return
        pm_rect = QRectF(pm.rect())
        try:
            self._pix_item.setTransformOriginPoint(pm_rect.center())
            self._pix_item.setRotation(self._rotation)
            br = self._pix_item.mapRectToScene(pm_rect)
            self._scene.setSceneRect(br)
        except Exception:
            pass
        # 현재 보기 정책 재적용(맞춤/실제 + 줌)
        self.apply_current_view()

    def apply_current_view(self):
        pix = self._pix_item.pixmap()
        if pix.isNull():
            return
        self.resetTransform()
        # 회전은 아이템 단위로 적용됨
        try:
            pm_rect = QRectF(pix.rect())
            self._pix_item.setTransformOriginPoint(pm_rect.center())
            self._pix_item.setRotation(self._rotation)
            # 회전 후 장면 경계 갱신
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
        # 좌측 상단 두 줄 상태 텍스트 그리기 (뷰포트 좌표)
        try:
            parent = self.parent()
            title = getattr(parent, "_overlay_title", "")
            info = getattr(parent, "_overlay_info", "")
            if not title and not info:
                return
            painter.save()
            # 뷰포트 좌표로 전환
            painter.resetTransform()
            # 대비 색상 선택(배경이 밝으면 검정, 어두우면 흰색)
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
            # 살짝 여백
            margin = 8
            x = margin
            y = margin + 14  # 첫 줄 베이스라인
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


class ImageViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Viewer")
        self.resize(1024, 768)
        try:
            self.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass

        self.image_files: list[str] = []
        self.current_index = -1
        self.pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self.cache_size = 20
        self.supported_formats = (".png", ".jpg", ".jpeg", ".webp")
        # 디코딩 전략: True이면 원본 디코딩, False이면 썸네일 모드 (기본: 원본)
        self.decode_full: bool = True

        self.canvas = ImageCanvas(self)
        self.setCentralWidget(self.canvas)

        self._create_menus()

        self.loader = Loader()
        self.loader.image_decoded.connect(self.on_image_ready)

        self._settings_path = os.path.join(os.path.dirname(__file__), "settings.json")
        # 설정 전역 캐시(dict) 로드 및 적용
        self._settings: dict = {}
        self._load_settings()
        # 디코딩 전략 기본값(원본) 및 설정 반영
        # settings.json 상태 그대로 사용: thumbnail_mode가 있으면 그것만 사용
        if "thumbnail_mode" in self._settings:
            self.decode_full = not bool(self._settings.get("thumbnail_mode", False))
        # 배경색(기본: 검정) 및 적용
        col = self._settings.get("background_color")
        self._bg_color = QColor(col) if isinstance(col, str) and QColor(col).isValid() else QColor(0, 0, 0)
        self._apply_background()
        # 프레스 배율 설정 반영
        try:
            mul = self._settings.get("press_zoom_multiplier")
            if mul is not None:
                self.canvas._press_zoom_multiplier = float(mul)
        except Exception:
            pass

        # 경로 정규화 유틸(Windows 특수 접두 및 잡음 제거)
        def _normalize_path_for_windows(p: str) -> str:
            try:
                if not isinstance(p, str):
                    return p
                p = p.strip()
                if os.name == 'nt':
                    p = p.replace('/', '\\')
                    if p.startswith('\\\\?\\'):
                        if p.startswith('\\\\?\\UNC\\'):
                            p = '\\\\' + p[8:]
                        else:
                            p = p[4:]
                    if p.startswith('[:'):
                        p = p[2:]
                    if p and p[0] in '[{(':
                        import re
                        m = re.search(r'[A-Za-z]:\\\\', p)
                        if m:
                            p = p[m.start():]
                return os.path.normpath(p)
            except Exception:
                return p
        self._normalize_path_for_windows = _normalize_path_for_windows

    def _create_menus(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("파일(&F)")

        open_action = QAction("폴더 열기...(&O)", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self.open_folder)
        file_menu.addAction(open_action)

        exit_action = QAction("끝내기(&X)", self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menu_bar.addMenu("보기(&V)")
        self.view_group = QActionGroup(self)
        self.view_group.setExclusive(True)

        self.fit_action = QAction("창에 맞춤(&F)", self, checkable=True)
        self.fit_action.setShortcut("F")
        self.fit_action.setChecked(True)
        self.fit_action.triggered.connect(self.choose_fit)
        self.view_group.addAction(self.fit_action)
        view_menu.addAction(self.fit_action)

        self.actual_action = QAction("실제 크기(&A)", self, checkable=True)
        self.actual_action.setShortcut("1")
        self.actual_action.setChecked(False)
        self.actual_action.triggered.connect(self.choose_actual)
        self.view_group.addAction(self.actual_action)
        view_menu.addAction(self.actual_action)

        self.hq_downscale_action = QAction("고품질 축소(맞춤 전용)(&Q)", self, checkable=True)
        self.hq_downscale_action.setChecked(False)
        self.hq_downscale_action.triggered.connect(self.toggle_hq_downscale)
        view_menu.addAction(self.hq_downscale_action)

        # 디코딩 전략 토글: 썸네일 모드(fast viewing)
        self.thumbnail_mode_action = QAction("썸네일 모드(fast viewing)", self, checkable=True)
        # 메뉴 체크 = 썸네일 모드, 내부 decode_full은 반대
        self.thumbnail_mode_action.setChecked(not self.decode_full)
        self.thumbnail_mode_action.triggered.connect(self.toggle_thumbnail_mode)
        view_menu.addAction(self.thumbnail_mode_action)
        # 썸네일 모드에서는 고품질 축소 옵션이 의미 없음 → 비활성화
        self.hq_downscale_action.setEnabled(self.decode_full)

        # 프레스 중 배율: 바로 입력창을 띄우는 단일 항목
        self.multiplier_action = QAction("프레스 중 배율...", self)
        self.multiplier_action.triggered.connect(self.prompt_custom_multiplier)
        view_menu.addAction(self.multiplier_action)

        # 배경색 메뉴
        bg_menu = view_menu.addMenu("배경색")
        self.bg_black_action = QAction("검정", self, checkable=True)
        self.bg_white_action = QAction("흰색", self, checkable=True)
        self.bg_custom_action = QAction("기타...", self)
        bg_menu.addAction(self.bg_black_action)
        bg_menu.addAction(self.bg_white_action)
        bg_menu.addAction(self.bg_custom_action)
        self.bg_black_action.triggered.connect(lambda: self.set_background_qcolor(QColor(0, 0, 0)))
        self.bg_white_action.triggered.connect(lambda: self.set_background_qcolor(QColor(255, 255, 255)))
        self.bg_custom_action.triggered.connect(self.choose_background_custom)
        self._sync_bg_checks()

        zoom_in_action = QAction("확대", self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.triggered.connect(lambda: self.zoom_by(1.25))
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("축소", self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.triggered.connect(lambda: self.zoom_by(0.75))
        view_menu.addAction(zoom_out_action)

        self.fullscreen_action = QAction("전체 화면", self, checkable=True)
        self.fullscreen_action.setShortcuts([
            QKeySequence(Qt.Key_Return),
            QKeySequence(Qt.Key_Enter),
        ])
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(self.fullscreen_action)

        # 전역 단축키
        self._shortcut_next = QShortcut(QKeySequence(Qt.Key_Right), self)
        self._shortcut_next.activated.connect(self.next_image)
        self._shortcut_prev = QShortcut(QKeySequence(Qt.Key_Left), self)
        self._shortcut_prev.activated.connect(self.prev_image)

        self._shortcut_first = QShortcut(QKeySequence(Qt.Key_Home), self)
        self._shortcut_first.activated.connect(self.first_image)
        self._shortcut_last = QShortcut(QKeySequence(Qt.Key_End), self)
        self._shortcut_last.activated.connect(self.last_image)

        self._shortcut_zoom_in = QShortcut(QKeySequence(Qt.Key_Up), self)
        self._shortcut_zoom_in.activated.connect(lambda: self.zoom_by(1.25))
        self._shortcut_zoom_out = QShortcut(QKeySequence(Qt.Key_Down), self)
        self._shortcut_zoom_out.activated.connect(lambda: self.zoom_by(0.8))

        self._shortcut_snap = QShortcut(QKeySequence(Qt.Key_Space), self)
        self._shortcut_snap.activated.connect(self.snap_to_global_view)

        self._shortcut_escape = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._shortcut_escape.activated.connect(self.exit_fullscreen)

    # 상태 오버레이 텍스트 갱신용 함수는 _update_status를 사용합니다.

    def _update_status(self, extra: str = ""):
        if self.current_index == -1 or not self.image_files:
            self._overlay_title = ""
            self._overlay_info = "준비됨 · Ctrl+O로 폴더 열기"
            if hasattr(self, 'canvas'):
                self.canvas.viewport().update()
            return

        fname = os.path.basename(self.image_files[self.current_index])
        idx = self.current_index + 1
        total = len(self.image_files)

        # 현재 파일의 원본 해상도 추출(QImageReader 사용; 전체 로드 없이 메타만 읽음)
        from PySide6.QtGui import QImageReader
        orig_w = orig_h = None
        try:
            reader = QImageReader(self.image_files[self.current_index])
            sz = reader.size()
            if sz.width() > 0 and sz.height() > 0:
                orig_w, orig_h = sz.width(), sz.height()
        except Exception:
            pass

        # 최근 디코딩된 해상도(썸네일/원본)를 on_image_ready에서 기록해 둠
        dec_w = dec_h = None
        try:
            dec_w, dec_h = getattr(self, "_current_decoded_size", (None, None))
        except Exception:
            pass

        # 배율 계산: 요구사항에 맞게 기준 선택
        vw = self.canvas.viewport().width()
        vh = self.canvas.viewport().height()

        def scale_from_dims(w: int | None, h: int | None) -> float | None:
            try:
                if not w or not h or w <= 0 or h <= 0:
                    return None
                if self.canvas.is_fit():
                    return min(max(1, vw) / w, max(1, vh) / h)
                else:
                    return float(self.canvas._zoom)
            except Exception:
                return None

        parts: list[str] = []
        # 현재 디코딩 전략 라벨
        try:
            strategy = "원본" if self.decode_full else "썸네일"
            parts.append(f"[{strategy}]")
        except Exception:
            pass
        if not self.decode_full:
            # 1) 썸네일 활성: 디코딩 해상도, 그 기준 배율, 원본 해상도
            if dec_w and dec_h:
                parts.append(f"{dec_w}x{dec_h}")
                sc = scale_from_dims(dec_w, dec_h)
                if sc is not None:
                    parts.append(f"@ {sc:.2f}x")
            if orig_w and orig_h:
                parts.append(f"원본 {orig_w}x{orig_h}")
        else:
            # 2) 썸네일 비활성: 해상도(=원본), 배율(원본 기준)
            base_w = orig_w if orig_w else (dec_w or None)
            base_h = orig_h if orig_h else (dec_h or None)
            if base_w and base_h:
                parts.append(f"{base_w}x{base_h}")
                sc = scale_from_dims(base_w, base_h)
                if sc is not None:
                    parts.append(f"@ {sc:.2f}x")

        if extra:
            parts.append(str(extra))

        suffix = f"  {'  '.join(parts)}" if parts else ""
        self._overlay_title = fname
        self._overlay_info = f"({idx}/{total}){('  ' + '  '.join(parts)) if parts else ''}"
        if hasattr(self, 'canvas'):
            self.canvas.viewport().update()

    def _load_last_parent_dir(self):
        # 중앙 설정 캐시에서 시작 폴더 반환
        val = self._settings.get("last_parent_dir")
        if isinstance(val, str) and os.path.isdir(val):
            return val
        try:
            return os.path.expanduser("~")
        except Exception:
            return os.getcwd()

    def _save_last_parent_dir(self, parent_dir: str):
        try:
            data = {}
            if os.path.exists(self._settings_path):
                try:
                    with open(self._settings_path, "r", encoding="utf-8") as f:
                        data = json.load(f) or {}
                except Exception:
                    data = {}
            data["last_parent_dir"] = parent_dir
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _save_settings_key(self, key: str, value):
        # 중앙 설정 캐시에 갱신 후 일괄 저장
        try:
            self._settings[key] = value
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        try:
            if os.path.exists(self._settings_path):
                with open(self._settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._settings = data
        except Exception:
            # 손상 시 무시하고 기본값 사용
            self._settings = {}

    def open_folder(self):
        try:
            start_dir = self._load_last_parent_dir()
        except Exception:
            start_dir = os.path.expanduser("~")
        try:
            dir_path = QFileDialog.getExistingDirectory(self, "폴더 열기", start_dir)
        except Exception:
            dir_path = None
        if not dir_path:
            return

        # 새 폴더 진입: 기존 세션 상태 정리
        try:
            # 1) 로더 상태 초기화 (무시/보류 제거)
            if hasattr(self, 'loader'):
                try:
                    # 최소화: 무시 집합/펜딩 초기화
                    self.loader._ignored.clear()
                    self.loader._pending.clear()
                    # 최신 요청 맵이 있으면 초기화
                    if hasattr(self.loader, '_latest_id'):
                        self.loader._latest_id.clear()
                except Exception:
                    pass
            # 2) 캐시/표시 초기화
            self.pixmap_cache.clear()
            self.current_index = -1
            try:
                empty = QPixmap(1, 1)
                empty.fill(Qt.transparent)
                self.canvas.set_pixmap(empty)
            except Exception:
                pass
        except Exception:
            pass

        # 이미지 목록 재구성
        try:
            files = []
            for name in os.listdir(dir_path):
                p = os.path.join(dir_path, name)
                if os.path.isfile(p):
                    lower = name.lower()
                    if lower.endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff")):
                        files.append(p)
            files.sort()
            self.image_files = files
        except Exception:
            self.image_files = []

        # 인덱스/상태 갱신 및 첫 이미지 표시
        if not self.image_files:
            self.setWindowTitle("Image Viewer")
            self._update_status("이미지가 없습니다.")
            return
        self.current_index = 0
        try:
            self._save_last_parent_dir(dir_path)
        except Exception:
            pass
        self.setWindowTitle(f"Image Viewer - {os.path.basename(self.image_files[self.current_index])}")
        self.display_image()
        self.maintain_decode_window(back=0, ahead=5)

    def display_image(self):
        if self.current_index == -1:
            return
        image_path = self.image_files[self.current_index]
        self.setWindowTitle(f"Image Viewer - {os.path.basename(image_path)}")

        if image_path in self.pixmap_cache:
            pix = self.pixmap_cache.pop(image_path)
            self.pixmap_cache[image_path] = pix
            self.update_pixmap(pix)
            return

        self._update_status("불러오는 중...")
        target_w = target_h = None
        # 썸네일 기반 다운스케일 디코딩은 맞춤 모드이며, 원본 디코딩이 꺼져있을 때만 사용
        if self.canvas.is_fit() and not self.decode_full:
            screen = self.windowHandle().screen() if self.windowHandle() else QApplication.primaryScreen()
            if screen is not None:
                size = screen.size()
                target_w = int(size.width())
                target_h = int(size.height())
        self.loader.request_load(image_path, target_w, target_h, "both")

    def on_image_ready(self, path, image_data, error):
        # Drop late results for items no longer present (e.g., deleted)
        try:
            if path not in self.image_files:
                return
        except Exception:
            pass
        if error:
            print(f"Error decoding {path}: {error}")
            try:
                base = os.path.basename(path)
            except Exception:
                base = path
            # 오버레이에 오류 노출
            self._overlay_info = f"디코딩 오류: {base} - {error}"
            if hasattr(self, 'canvas'):
                self.canvas.viewport().update()
            return

        height, width, channel = image_data.shape
        bytes_per_line = 3 * width
        q_image = QImage(image_data.data, width, height, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)

        # 현재 이미지라면 최근 디코딩 해상도 기록
        if path == self.image_files[self.current_index]:
            try:
                self._current_decoded_size = (width, height)
            except Exception:
                pass

        if path in self.pixmap_cache:
            self.pixmap_cache.pop(path)
        self.pixmap_cache[path] = pixmap
        if len(self.pixmap_cache) > self.cache_size:
            self.pixmap_cache.popitem(last=False)

        if path == self.image_files[self.current_index]:
            self.update_pixmap(pixmap)

    def update_pixmap(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            self.canvas.set_pixmap(pixmap)
            # 상태는 내부 로직으로 구성되므로 별도 정보 없이 갱신만 호출
            self._update_status()
        else:
            self._update_status("이미지 로드 실패")

    def keyPressEvent(self, event):
        if not self.image_files:
            return
        key = event.key()
        if key == Qt.Key_Right:
            self.next_image()
        elif key == Qt.Key_Left:
            self.prev_image()
        elif key == Qt.Key_A:
            # 좌측 90도 회전
            try:
                self.canvas.rotate_by(-90)
            except Exception:
                pass
        elif key == Qt.Key_D:
            # 우측 90도 회전
            try:
                self.canvas.rotate_by(90)
            except Exception:
                pass
        elif key == Qt.Key_Delete:
            self.delete_current_file()
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            # 전체 화면 토글: 전체 화면 상태에서 Enter/Return으로 빠져나오기 포함
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)



    def maintain_decode_window(self, back: int = 3, ahead: int = 5):
        if not self.image_files:
            return
        n = len(self.image_files)
        i = self.current_index
        start = max(0, i - back)
        end = min(n - 1, i + ahead)
        for idx in range(start, end + 1):
            path = self.image_files[idx]
            if path not in self.pixmap_cache:
                target_w = target_h = None
                if self.canvas.is_fit() and not self.decode_full:
                    screen = self.windowHandle().screen() if self.windowHandle() else QApplication.primaryScreen()
                    if screen is not None:
                        sz = screen.size()
                        target_w = int(sz.width())
                        target_h = int(sz.height())
                self.loader.request_load(path, target_w, target_h, "both")

    # 탐색
    def next_image(self):
        if not self.image_files:
            return
        n = len(self.image_files)
        if self.current_index >= n - 1:
            # 마지막이면 아무 작업도 하지 않음(랩어라운드 금지)
            return
        self.current_index += 1
        self.display_image()
        self.maintain_decode_window()

    def prev_image(self):
        if not self.image_files:
            return
        if self.current_index <= 0:
            # 첫 번째면 아무 작업도 하지 않음(랩어라운드 금지)
            return
        self.current_index -= 1
        self.display_image()
        self.maintain_decode_window()

    def first_image(self):
        if not self.image_files:
            return
        self.current_index = 0
        self.display_image()
        self.maintain_decode_window()

    def last_image(self):
        if not self.image_files:
            return
        self.current_index = len(self.image_files) - 1
        self.display_image()
        self.maintain_decode_window()

    def delete_current_file(self):
        # 현재 파일을 휴지통으로 이동(확인 대화상자 표시).
        # UX: 삭제 확정 후 먼저 다른 이미지로 전환하고, 그 다음 실제 삭제를 시도한다.
        if not self.image_files or self.current_index < 0 or self.current_index >= len(self.image_files):
            print("[delete] abort: no images or invalid index")
            return
        del_path = self.image_files[self.current_index]
        abs_path = os.path.abspath(del_path)
        print(f"[delete] start: idx={self.current_index}, total={len(self.image_files)}")

        try:
            from PySide6.QtWidgets import QMessageBox, QApplication
        except Exception:
            QMessageBox = None
            QApplication = None
            print("[delete] QMessageBox/QApplication unavailable")

        # 확인 다이얼로그
        proceed = True
        if QMessageBox is not None:
            base = os.path.basename(del_path)
            ret = QMessageBox.question(
                self,
                "휴지통으로 이동",
                f"이 파일을 휴지통으로 이동하시겠습니까?\n{base}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            proceed = (ret == QMessageBox.Yes)
            print(f"[delete] confirm: proceed={proceed}")
        if not proceed:
            print("[delete] user cancelled")
            return

        # 1) 다른 이미지로 전환하여 표시 기준을 바꾼다
        if len(self.image_files) > 1:
            if self.current_index < len(self.image_files) - 1:
                new_index = self.current_index + 1
            else:
                new_index = self.current_index - 1
            print(f"[delete] switch image: {self.current_index} -> {new_index}")
            self.current_index = new_index
            try:
                self.display_image()
                self.maintain_decode_window()
            except Exception as ex:
                print(f"[delete] switch image error: {ex}")
        else:
            print("[delete] single image case: will clear view later")

        # 화면/캐시에서 해당 경로 제거 + 이벤트/GC로 안정화
        try:
            removed = self.pixmap_cache.pop(del_path, None) is not None
            print(f"[delete] cache pop: removed={removed}")
        except Exception as ex:
            print(f"[delete] cache pop error: {ex}")
        try:
            import gc, time as _time
            if 'QApplication' in globals() and QApplication is not None:
                QApplication.processEvents()
                print("[delete] processEvents done")
            gc.collect()
            print("[delete] gc.collect done")
            _time.sleep(0.15)
            print("[delete] settle sleep done")
        except Exception as ex:
            print(f"[delete] settle phase error: {ex}")

        # 2) 실제 휴지통 이동(재시도 포함)
        try:
            try:
                from send2trash import send2trash
                import time
                last_err = None
                for attempt in range(1, 4):
                    try:
                        print(f"[delete] trash attempt {attempt}")
                        send2trash(abs_path)
                        last_err = None
                        print("[delete] trash success")
                        break
                    except Exception as ex:
                        last_err = ex
                        print(f"[delete] trash failed attempt {attempt}: {ex}")
                        time.sleep(0.2)
                if last_err is not None:
                    raise last_err
            except Exception:
                raise
        except Exception as e:
            print(f"[delete] trash final error: {e}")
            if 'QMessageBox' in globals() and QMessageBox is not None:
                QMessageBox.critical(
                    self,
                    "이동 실패",
                    (
                        "휴지통으로 이동 중 오류가 발생했습니다.\n"
                        "send2trash 설치 및 경로를 확인해 주세요.\n\n"
                        f"오류: {e}\n"
                        f"원본경로: {del_path}\n"
                        f"절대경로: {abs_path}\n"
                    ),
                )
            return

        # 삭제 성공 확인 후에만, 재요청/완료 신호를 확실히 무시하도록 ignore 적용
        try:
            if hasattr(self, 'loader'):
                self.loader.ignore_path(del_path)
        except Exception:
            pass

        # 3) 목록에서 제거하고 인덱스 정리
        try:
            try:
                del_pos = self.image_files.index(del_path)
            except ValueError:
                del_pos = None
            print(f"[delete] remove list: pos={del_pos}")
            if del_pos is not None:
                self.image_files.pop(del_pos)
                if del_pos <= self.current_index:
                    old_idx = self.current_index
                    self.current_index = max(0, self.current_index - 1)
                    print(f"[delete] index adjust: {old_idx} -> {self.current_index}")
        except Exception as ex:
            print(f"[delete] list pop error, fallback remove: {ex}")
            try:
                self.image_files.remove(del_path)
                print("[delete] list remove by value: success")
            except Exception as ex2:
                print(f"[delete] list remove by value error: {ex2}")

        # 4) 최종 표시/상태 갱신
        if not self.image_files:
            print("[delete] list empty: clearing view")
            self.current_index = -1
            try:
                empty = QPixmap(1, 1)
                empty.fill(Qt.transparent)
                self.canvas.set_pixmap(empty)
            except Exception as ex:
                print(f"[delete] clear view error: {ex}")
            self.setWindowTitle("Image Viewer")
            self._update_status()
            return
        try:
            print(f"[delete] show current: idx={self.current_index}, total={len(self.image_files)}")
            self.display_image()
            self.maintain_decode_window()
        except Exception as ex:
            print(f"[delete] final display error: {ex}")

    def closeEvent(self, event):
        self.loader.shutdown()
        event.accept()

    # 보기 명령
    def toggle_fit(self):
        self.choose_fit()

    def zoom_by(self, factor: float):
        self.canvas.zoom_by(factor)

    def reset_zoom(self):
        self.canvas.reset_zoom()

    def choose_fit(self):
        self.canvas._preset_mode = "fit"
        self.fit_action.setChecked(True)
        if hasattr(self, 'actual_action'):
            self.actual_action.setChecked(False)
        self.canvas.apply_current_view()

    def choose_actual(self):
        self.canvas._preset_mode = "actual"
        self.canvas._zoom = 1.0
        if hasattr(self, 'fit_action'):
            self.fit_action.setChecked(False)
        if hasattr(self, 'actual_action'):
            self.actual_action.setChecked(True)
        self.canvas.apply_current_view()

    def toggle_hq_downscale(self):
        enabled = self.hq_downscale_action.isChecked()
        self.canvas._hq_downscale = enabled
        self.canvas._hq_pixmap = None
        if self.canvas.is_fit():
            self.canvas.apply_current_view()

    # 디코딩 전략 토글: 썸네일 모드 on/off (체크=썸네일)
    def toggle_thumbnail_mode(self):
        is_thumbnail = self.thumbnail_mode_action.isChecked()
        # 내부 상태는 decode_full의 반대
        self.decode_full = not is_thumbnail
        # 설정 저장: 썸네일 모드 상태만 저장
        self._save_settings_key("thumbnail_mode", is_thumbnail)
        # 썸네일 모드에서는 고품질 축소 옵션 비활성화 및 해제
        self.hq_downscale_action.setEnabled(self.decode_full)
        if not self.decode_full and self.hq_downscale_action.isChecked():
            self.hq_downscale_action.setChecked(False)
            self.canvas._hq_downscale = False
        # 현재 캐시를 비워 새 전략으로 비교가 즉시 가능하도록 함
        self.pixmap_cache.clear()
        # 현재 이미지를 재표시 및 프리패치 재요청
        self.display_image()
        self.maintain_decode_window()

    def snap_to_global_view(self):
        if hasattr(self, 'fit_action') and self.fit_action.isChecked():
            self.choose_fit()
        else:
            self.choose_actual()

    # 배경색 설정/동기화
    def _apply_background(self):
        try:
            self.canvas.setBackgroundBrush(self._bg_color)
        except Exception:
            pass

    def _sync_bg_checks(self):
        try:
            is_black = self._bg_color == QColor(0, 0, 0)
            is_white = self._bg_color == QColor(255, 255, 255)
            if hasattr(self, 'bg_black_action'):
                self.bg_black_action.setChecked(bool(is_black))
            if hasattr(self, 'bg_white_action'):
                self.bg_white_action.setChecked(bool(is_white))
        except Exception:
            pass

    def _save_bg_color(self):
        try:
            c = self._bg_color
            hexcol = f"#{c.red():02x}{c.green():02x}{c.blue():02x}"
            self._save_settings_key("background_color", hexcol)
        except Exception:
            pass

    def set_background_qcolor(self, color: QColor):
        try:
            if not isinstance(color, QColor):
                return
            if not color.isValid():
                return
            self._bg_color = color
            self._apply_background()
            self._sync_bg_checks()
            self._save_bg_color()
        except Exception:
            pass

    def choose_background_custom(self):
        try:
            col = QColorDialog.getColor(self._bg_color, self, "배경색 선택")
        except Exception:
            col = None
        if col and col.isValid():
            self.set_background_qcolor(col)

    # 설정: 프레스 줌 배율
    def set_press_zoom_multiplier(self, value: float):
        try:
            v = float(value)
        except Exception:
            return
        v = max(0.1, min(v, 10.0))
        self.canvas._press_zoom_multiplier = v
        self._save_settings_key("press_zoom_multiplier", v)

    def prompt_custom_multiplier(self):
        try:
            from PySide6.QtWidgets import QInputDialog
        except Exception:
            return
        current = getattr(self.canvas, "_press_zoom_multiplier", 2.0)
        val, ok = QInputDialog.getDouble(
            self,
            "프레스 줌 배율",
            "배율을 입력하세요 (1.0-10.0):",
            float(current),
            0.1,
            10.0,
            1,
        )
        if ok:
            self.set_press_zoom_multiplier(val)

    # 전체 화면
    def enter_fullscreen(self):
        if self.isFullScreen():
            return
        self._prev_state = self.windowState()
        try:
            self._prev_geometry = self.saveGeometry()
        except Exception:
            self._prev_geometry = None
        self.menuBar().setVisible(False)
        self.setWindowState(self._prev_state | Qt.WindowFullScreen)
        if hasattr(self, 'fullscreen_action'):
            self.fullscreen_action.setChecked(True)
        self.canvas.apply_current_view()

    def exit_fullscreen(self):
        if not self.isFullScreen():
            return
        self.setUpdatesEnabled(False)
        prev = getattr(self, "_prev_state", Qt.WindowMaximized)
        self.setWindowState(prev & ~Qt.WindowFullScreen)
        geom = getattr(self, "_prev_geometry", None)
        if geom and not (prev & Qt.WindowMaximized):
            try:
                self.restoreGeometry(geom)
            except Exception:
                pass
        self.menuBar().setVisible(True)
        if hasattr(self, 'fullscreen_action'):
            self.fullscreen_action.setChecked(False)
        self.setUpdatesEnabled(True)
        self.canvas.apply_current_view()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()

    app = QApplication(sys.argv)
    viewer = ImageViewer()
    viewer.showMaximized()
    sys.exit(app.exec())
