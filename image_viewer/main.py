import sys
import os
import json
from collections import OrderedDict

from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QImage, QKeySequence, QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QFileDialog,
    QColorDialog,
    QVBoxLayout,
    QLabel,
    QProgressBar
)

# 분리된 모듈에서 로드
_pkg_root = os.path.dirname(os.path.dirname(__file__))
if _pkg_root not in sys.path:
    sys.path.append(_pkg_root)
from image_viewer.loader import Loader
from image_viewer.ui_canvas import ImageCanvas
from image_viewer.trim import (
    detect_trim_box_stats,
    make_trim_preview,
    apply_trim_to_file,
)
from image_viewer.ui_menus import build_menus
from image_viewer.decoder import decode_image as _decode
from image_viewer.strategy import DecodingStrategy, ThumbnailStrategy, FullStrategy


# --- Top-level function for the Process Pool ---
# multiprocessing에서 피클링 가능하도록 최상위에 유지되는 셔틀 함수
def decode_image(file_path, target_width=None, target_height=None, size="both"):
    return _decode(file_path, target_width, target_height, size)


from typing import Optional, Any
from .logger import get_logger
from .ui_trim import TrimBatchWorker, TrimProgressDialog

logger = get_logger("main")


class ViewState:
    """뷰 관련 상태를 캡슐화합니다."""
    def __init__(self):
        self.preset_mode: str = "fit"  # "fit" or "actual"
        self.zoom: float = 1.0
        self.hq_downscale: bool = False
        self.press_zoom_multiplier: float = 2.0
        self._prev_state = None
        self._prev_geometry = None


class TrimState:
    """트림 워크플로우 상태를 캡슐화합니다."""
    def __init__(self):
        self.is_running: bool = False
        self.in_preview: bool = False

class ImageViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Viewer")
        self.resize(1024, 768)
        try:
            self.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass

        # 상태 객체 초기화
        self.view_state = ViewState()
        self.trim_state = TrimState()

        self.image_files: list[str] = []
        self.current_index = -1
        self.pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self.cache_size = 20
        
        # 디코딩 전략 초기화 (기본: 원본)
        self.decoding_strategy: DecodingStrategy = FullStrategy()

        self.canvas = ImageCanvas(self)
        self.setCentralWidget(self.canvas)

        # 메뉴 구성(점진 분리: 별도 모듈 래퍼 통해 호출)
        build_menus(self)

        self.loader = Loader(decode_image)
        self.loader.image_decoded.connect(self.on_image_ready)

        self._settings_path = os.path.join(os.path.dirname(__file__), "settings.json")
        # 설정 전역 캐시(dict) 로드 및 적용
        self._settings: dict = {}
        self._load_settings()
        # 디코딩 전략 로드: settings에서 thumbnail_mode 반영
        if "thumbnail_mode" in self._settings and self._settings.get("thumbnail_mode", False):
            self.decoding_strategy = ThumbnailStrategy()
            logger.debug("decoding strategy: thumbnail (from settings)")
        else:
            self.decoding_strategy = FullStrategy()
            logger.debug("decoding strategy: full (default)")
        
        # 메뉴 액션과 내부 상태 동기화 (설정 반영 이후에 반드시 동기화)
        try:
            is_thumbnail = isinstance(self.decoding_strategy, ThumbnailStrategy)
            if hasattr(self, "thumbnail_mode_action"):
                self.thumbnail_mode_action.setChecked(is_thumbnail)
            if hasattr(self, "hq_downscale_action"):
                self.hq_downscale_action.setEnabled(self.decoding_strategy.supports_hq_downscale())
                if not self.decoding_strategy.supports_hq_downscale() and self.hq_downscale_action.isChecked():
                    self.hq_downscale_action.setChecked(False)
                    self.canvas._hq_downscale = False
        except Exception as e:
            logger.error("failed to sync menu state: %s", e)
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
            parts.append(f"[{self.decoding_strategy.get_name()}]")
        except Exception as e:
            logger.debug("failed to get strategy name: %s", e)
        
        if isinstance(self.decoding_strategy, ThumbnailStrategy):
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
                except Exception as e:
                    logger.warning("failed to load settings for last_parent_dir: %s", e)
                    data = {}
            data["last_parent_dir"] = parent_dir
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("last_parent_dir saved: %s", parent_dir)
        except Exception as e:
            logger.error("failed to save last_parent_dir: %s", e)

    def _save_settings_key(self, key: str, value):
        # 중앙 설정 캐시에 갱신 후 일괄 저장
        try:
            self._settings[key] = value
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
            logger.debug("settings saved: key=%s, value=%s", key, value)
        except Exception as e:
            logger.error("settings save failed: key=%s, error=%s", key, e)

    def _load_settings(self):
        try:
            if os.path.exists(self._settings_path):
                with open(self._settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._settings = data
                        logger.debug("settings loaded: %s", self._settings_path)
        except Exception as e:
            logger.warning("settings load failed: %s", e)
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

    def display_image(self) -> None:
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
        
        # 맞춤 모드이고 썸네일 전략일 때 타겟 크기 계산
        if self.canvas.is_fit():
            screen = self.windowHandle().screen() if self.windowHandle() else QApplication.primaryScreen()
            if screen is not None:
                size = screen.size()
                target_w, target_h = self.decoding_strategy.get_target_size(int(size.width()), int(size.height()))
                logger.debug("display_image: target_size=(%s, %s)", target_w, target_h)
        
        self.loader.request_load(image_path, target_w, target_h, "both")

    def on_image_ready(self, path: str, image_data: Optional[Any], error: Optional[Any]) -> None:
        # Drop late results for items no longer present (e.g., deleted)
        try:
            if path not in self.image_files:
                return
        except Exception:
            pass
        if error:
            logger.error("decode error for %s: %s", path, error)
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

        # 미리보기(트림 등) 중에는 화면 갱신을 건너뜀
        if self.trim_state.in_preview:
            logger.debug("skipping screen update during trim preview")
            return
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



    def maintain_decode_window(self, back: int = 3, ahead: int = 5) -> None:
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
            logger.debug("[delete] abort: no images or invalid index")
            return
        del_path = self.image_files[self.current_index]
        abs_path = os.path.abspath(del_path)
        logger.debug("[delete] start: idx=%s, del_path=%s, abs_path=%s, total=%s", self.current_index, del_path, abs_path, len(self.image_files))

        try:
            from PySide6.QtWidgets import QMessageBox, QApplication
        except Exception:
            QMessageBox = None
            QApplication = None
            logger.debug("[delete] QMessageBox/QApplication unavailable")

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
            logger.debug("[delete] confirm: proceed=%s", proceed)
        if not proceed:
            logger.debug("[delete] user cancelled")
            return

        # 1) 다른 이미지로 전환하여 표시 기준을 바꾼다
        if len(self.image_files) > 1:
            if self.current_index < len(self.image_files) - 1:
                new_index = self.current_index + 1
            else:
                new_index = self.current_index - 1
            logger.debug("[delete] switch image: %s -> %s", self.current_index, new_index)
            self.current_index = new_index
            try:
                self.display_image()
                self.maintain_decode_window()
            except Exception as ex:
                logger.debug("[delete] switch image error: %s", ex)
        else:
            logger.debug("[delete] single image case: will clear view later")

        # 화면/캐시에서 해당 경로 제거 + 이벤트/GC로 안정화
        try:
            removed = self.pixmap_cache.pop(del_path, None) is not None
            logger.debug("[delete] cache pop: removed=%s", removed)
        except Exception as ex:
            logger.debug("[delete] cache pop error: %s", ex)
        try:
            import gc, time as _time
            if 'QApplication' in globals() and QApplication is not None:
                QApplication.processEvents()
                logger.debug("[delete] processEvents done")
            gc.collect()
            logger.debug("[delete] gc.collect done")
            _time.sleep(0.15)
            logger.debug("[delete] settle sleep done")
        except Exception as ex:
            logger.debug("[delete] settle phase error: %s", ex)

        # 2) 실제 휴지통 이동(재시도 포함)
        try:
            try:
                from send2trash import send2trash
                import time
                last_err = None
                for attempt in range(1, 4):
                    try:
                        logger.debug("[delete] trash attempt %s", attempt)
                        send2trash(abs_path)
                        last_err = None
                        logger.debug("[delete] trash success")
                        break
                    except Exception as ex:
                        last_err = ex
                        logger.debug("[delete] trash failed attempt %s: %s", attempt, ex)
                        time.sleep(0.2)
                if last_err is not None:
                    raise last_err
            except Exception:
                raise
        except Exception as e:
            logger.debug("[delete] trash final error: %s", e)
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
            logger.debug("[delete] remove list: pos=%s", del_pos)
            if del_pos is not None:
                self.image_files.pop(del_pos)
                if del_pos <= self.current_index:
                    old_idx = self.current_index
                    self.current_index = max(0, self.current_index - 1)
                    logger.debug("[delete] index adjust: %s -> %s", old_idx, self.current_index)
        except Exception as ex:
            logger.debug("[delete] list pop error, fallback remove: %s", ex)
            try:
                self.image_files.remove(del_path)
                logger.debug("[delete] list remove by value: success")
            except Exception as ex2:
                logger.debug("[delete] list remove by value error: %s", ex2)

        # 4) 최종 표시/상태 갱신
        if not self.image_files:
            logger.debug("[delete] list empty: clearing view")
            self.current_index = -1
            try:
                empty = QPixmap(1, 1)
                empty.fill(Qt.transparent)
                self.canvas.set_pixmap(empty)
            except Exception as ex:
                logger.debug("[delete] clear view error: %s", ex)
            self.setWindowTitle("Image Viewer")
            self._update_status()
            return
        try:
            logger.debug("[delete] show current: idx=%s, total=%s", self.current_index, len(self.image_files))
            self.display_image()
            self.maintain_decode_window()
        except Exception as ex:
            logger.debug("[delete] final display error: %s", ex)

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
        # 전략 전환
        if is_thumbnail:
            self.decoding_strategy = ThumbnailStrategy()
            logger.debug("switched to ThumbnailStrategy")
        else:
            self.decoding_strategy = FullStrategy()
            logger.debug("switched to FullStrategy")
        
        # 설정 저장: 썸네일 모드 상태만 저장
        self._save_settings_key("thumbnail_mode", is_thumbnail)
        
        # 전략에 따라 고품질 축소 옵션 활성화/비활성화
        self.hq_downscale_action.setEnabled(self.decoding_strategy.supports_hq_downscale())
        if not self.decoding_strategy.supports_hq_downscale() and self.hq_downscale_action.isChecked():
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

    # ---------------- Trim Workflow ----------------
    def start_trim_workflow(self):
        # 재진입/중복 실행 방지
        if self.trim_state.is_running:
            logger.debug("trim workflow already running")
            return
        self.trim_state.is_running = True
        try:
            if not self.image_files:
                return
            try:
                from PySide6.QtWidgets import QMessageBox
            except Exception:
                return

            # 0) 트림 민감도 프로파일 선택 (기본/공격적)
            prof_box = QMessageBox(self)
            prof_box.setWindowTitle("트림 민감도")
            prof_box.setText("어떤 프로파일로 트림할까요?")
            btn_norm = prof_box.addButton("기본", QMessageBox.AcceptRole)
            btn_agg = prof_box.addButton("공격적", QMessageBox.ActionRole)
            btn_cancel = prof_box.addButton("취소", QMessageBox.RejectRole)
            prof_box.setDefaultButton(btn_norm)
            prof_box.exec()
            clicked_prof = prof_box.clickedButton()
            if clicked_prof is btn_cancel or clicked_prof is None:
                return
            profile = 'aggressive' if clicked_prof is btn_agg else 'normal'

            # 1) 저장 모드 선택 (덮어씌우기/사본/취소)
            mode_box = QMessageBox(self)
            mode_box.setWindowTitle("트림")
            mode_box.setText("Stats 방식으로 트림하겠습니다.\n(덮어씌우기, 따로 저장, 취소)")
            overwrite_btn = mode_box.addButton("덮어씌우기", QMessageBox.AcceptRole)
            saveas_btn = mode_box.addButton("사본 저장(_trimmed)", QMessageBox.ActionRole)
            cancel_btn = mode_box.addButton("취소", QMessageBox.RejectRole)
            mode_box.setDefaultButton(overwrite_btn)
            mode_box.exec()
            clicked = mode_box.clickedButton()
            if clicked is cancel_btn or clicked is None:
                return
            overwrite = (clicked is overwrite_btn)

            if not overwrite:
                # 사본 저장: 백그라운드 스레드 일괄 처리 + 진행 대화상자
                try:
                    from PySide6.QtCore import QThread
                except Exception:
                    QThread = None  # type: ignore

                paths = list(self.image_files)
                dlg = TrimProgressDialog(self)

                if QThread is None:
                    # 폴백: 동기 처리
                    worker = TrimBatchWorker(paths, profile)

                    def _on_progress(total, index, name):
                        dlg.on_progress(total, index, name)

                    worker.progress.connect(_on_progress)
                    worker.finished.connect(dlg.accept)
                    worker.run()
                    dlg.exec()
                    self.maintain_decode_window()
                    return

                thread = QThread(self)
                worker = TrimBatchWorker(paths, profile)
                worker.moveToThread(thread)
                thread.started.connect(worker.run)
                worker.progress.connect(dlg.on_progress)

                # 종료 시 안전한 정리: worker.finished → thread.quit, thread.finished → cleanup
                def _on_worker_finished():
                    try:
                        thread.quit()
                    except Exception:
                        pass

                def _on_thread_finished():
                    try:
                        worker.deleteLater()
                        thread.deleteLater()
                    except Exception:
                        pass
                    try:
                        dlg.accept()
                    except Exception:
                        pass
                    self.maintain_decode_window()

                worker.finished.connect(_on_worker_finished)
                thread.finished.connect(_on_thread_finished)
                thread.start()
                dlg.exec()
                return

            # 덮어씌우기: 파일별 승인(미리보기 + Y/N/A 단축키)
            stop_all = False
            for path in list(self.image_files):
                if stop_all:
                    break
                try:
                    crop = detect_trim_box_stats(path, profile=profile)
                except Exception:
                    crop = None
                if not crop:
                    continue
                view_w = max(1, self.canvas.viewport().width())
                view_h = max(1, self.canvas.viewport().height())
                preview = make_trim_preview(path, crop, view_w, view_h)
                if preview is None:
                    continue
                prev_pix = self.canvas._pix_item.pixmap() if self.canvas._pix_item else None
                try:
                    self.trim_state.in_preview = True
                    self.canvas.set_pixmap(preview)
                    self.canvas._preset_mode = "fit"
                    self.canvas.apply_current_view()
                except Exception as e:
                    logger.error("trim preview display error: %s", e)

                box = QMessageBox(self)
                box.setWindowTitle("Trim")
                box.setText("트림할까요? (Y/N)")
                yes = box.addButton("Accept (Y)", QMessageBox.YesRole)
                no = box.addButton("Reject (N)", QMessageBox.NoRole)
                abort_btn = box.addButton("Abort (A)", QMessageBox.RejectRole)
                # Y/N/A 단축키 동작 추가: 단축키로 버튼 클릭을 트리거
                try:
                    from PySide6.QtGui import QKeySequence, QShortcut

                    sc_y = QShortcut(QKeySequence("Y"), box)
                    sc_n = QShortcut(QKeySequence("N"), box)
                    sc_a = QShortcut(QKeySequence("A"), box)
                    sc_y.activated.connect(lambda: yes.click())
                    sc_n.activated.connect(lambda: no.click())
                    sc_a.activated.connect(lambda: abort_btn.click())
                except Exception:
                    pass
                box.setDefaultButton(yes)
                box.exec()
                clicked_btn = box.clickedButton()
                if clicked_btn is abort_btn:
                    stop_all = True
                    accepted = False
                else:
                    accepted = (clicked_btn is yes)

                # 원래 뷰 복귀
                try:
                    if prev_pix and not prev_pix.isNull():
                        self.canvas.set_pixmap(prev_pix)
                        self.canvas.apply_current_view()
                    else:
                        self.display_image()
                except Exception as e:
                    logger.error("trim preview restore error: %s", e)
                    self.display_image()
                finally:
                    self.trim_state.in_preview = False

                if not accepted:
                    continue

                try:
                    # 로그: 덮어쓰기 직전 상태 출력
                    logger.debug("[trim] overwrite prep: %s", path)
                    try:
                        displaying = (
                            self.current_index >= 0 and
                            self.current_index < len(self.image_files) and
                            self.image_files[self.current_index] == path
                        )
                    except Exception:
                        displaying = False
                    cached = False
                    try:
                        cached = (path in self.pixmap_cache)
                    except Exception:
                        cached = False
                    logger.debug("[trim] overwrite start: %s, displaying=%s, cached=%s", path, displaying, cached)
                    apply_trim_to_file(path, crop, overwrite=True)
                    logger.debug("[trim] overwrite ok: %s", path)
                except Exception:
                    try:
                        import traceback as _tb
                        logger.debug("[trim] overwrite error: %s\n%s", path, _tb.format_exc())
                    except Exception:
                        pass
                    try:
                        QMessageBox.critical(self, "Trim 오류", f"파일 저장 실패: {os.path.basename(path)}")
                    except Exception:
                        pass
                    continue

                # 캐시 무효화 및 필요시 재표시
                try:
                    self.pixmap_cache.pop(path, None)
                except Exception:
                    pass
                if self.current_index >= 0 and self.current_index < len(self.image_files) and self.image_files[self.current_index] == path:
                    self.display_image()

            self.maintain_decode_window()
        finally:
            # 실행 플래그 해제
            self.trim_state.is_running = False
            logger.debug("trim workflow finished")

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
