import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QInputDialog,
)

# Load from separated modules
_pkg_root = os.path.dirname(os.path.dirname(__file__))
if _pkg_root not in sys.path:
    sys.path.append(_pkg_root)
import gc
import time
import time as _time
import traceback as _tb
import contextlib

# --- Top-level function for the Process Pool ---
# Shuttle function kept at top level for pickling in multiprocessing
from PySide6.QtGui import QImageReader, QShortcut
from send2trash import send2trash

from image_viewer.decoder import decode_image
from image_viewer.loader import Loader
from image_viewer.strategy import FastViewStrategy, FullStrategy, DecodingStrategy
from image_viewer.trim import apply_trim_to_file, detect_trim_box_stats, make_trim_preview
from image_viewer.ui_canvas import ImageCanvas
from image_viewer.ui_menus import build_menus

from typing import Any

from image_viewer.logger import get_logger
from image_viewer.ui_settings import SettingsDialog
from image_viewer.ui_trim import TrimBatchWorker, TrimProgressDialog


# --- CLI logging options -----------------------------------------------------
# Qt가 알 수 없는 옵션으로 종료되는 걸 막기 위해, 우리가 사용하는 옵션만 선제적으로 파싱해
# 환경변수(IMAGE_VIEWER_LOG_LEVEL, IMAGE_VIEWER_LOG_CATS)에 반영하고 sys.argv에서 제거한다.


def _apply_cli_logging_options() -> None:
    try:
        import os as _os
        import sys as _sys

        level = None
        cats = None
        rest = [_sys.argv[0]]
        i = 1
        while i < len(_sys.argv):
            a = _sys.argv[i]
            if a.startswith("--log-level="):
                level = a.split("=", 1)[1].strip()
                i += 1
                continue
            if a == "--log-level" and i + 1 < len(_sys.argv):
                level = _sys.argv[i + 1].strip()
                i += 2
                continue
            if a.startswith("--log-cats="):
                cats = a.split("=", 1)[1].strip()
                i += 1
                continue
            if a == "--log-cats" and i + 1 < len(_sys.argv):
                cats = _sys.argv[i + 1].strip()
                i += 2
                continue
            rest.append(a)
            i += 1
        if level:
            _os.environ["IMAGE_VIEWER_LOG_LEVEL"] = level
        if cats:
            _os.environ["IMAGE_VIEWER_LOG_CATS"] = cats
        _sys.argv[:] = rest
    except Exception:
        # 로깅 설정 실패는 앱 실행을 막지 않는다.
        pass


_apply_cli_logging_options()
logger = get_logger("main")


class ViewState:
    """Encapsulates view-related state."""

    def __init__(self):
        self.preset_mode: str = "fit"  # "fit" or "actual"
        self.zoom: float = 1.0
        self.hq_downscale: bool = False
        self.press_zoom_multiplier: float = 2.0
        self._prev_state = None
        self._prev_geometry = None


class TrimState:
    """Encapsulates trim workflow state."""

    def __init__(self):
        self.is_running: bool = False
        self.in_preview: bool = False


class ExplorerState:
    """Encapsulates explorer mode state."""

    def __init__(self):
        self.view_mode: bool = True  # True=View, False=Explorer
        self._explorer_tree: Any | None = None
        self._explorer_grid: Any | None = None


class ImageViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Viewer")
        self.resize(1024, 768)

        self.view_state = ViewState()
        self.trim_state = TrimState()
        self.explorer_state = ExplorerState()
        self.image_files: list[str] = []
        self.current_index = -1
        self.pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self.cache_size = 20
        self.decode_full = False
        self.decoding_strategy: DecodingStrategy = FullStrategy()

        self.canvas = ImageCanvas(self)
        self.setCentralWidget(self.canvas)

        self.loader = Loader(decode_image)
        self.loader.image_decoded.connect(self.on_image_ready)
        self.thumb_loader = Loader(decode_image)

        self._settings_path = os.path.join(os.path.dirname(__file__), "settings.json")
        self._settings: dict[str, Any] = {}
        self._load_settings()
        self._bg_color = self._determine_startup_background()

        if self._settings.get("fast_view_enabled", False):
            self.decoding_strategy = FastViewStrategy()
        else:
            self.decoding_strategy = FullStrategy()

        build_menus(self)
        self._apply_background()

        self._overlay_title = ""
        self._overlay_info = "Ready"

    def _get_file_dimensions(self, file_path: str) -> tuple[int | None, int | None]:
        """Get the original dimensions of a file."""
        try:
            reader = QImageReader(file_path)
            size = reader.size()
            if size.width() > 0 and size.height() > 0:
                return size.width(), size.height()
        except Exception:
            pass
        return None, None

    def _get_decoded_dimensions(self) -> tuple[int | None, int | None]:
        """Get the most recently decoded dimensions."""
        try:
            return getattr(self, "_current_decoded_size", (None, None))
        except Exception:
            return None, None

    def _calculate_scale(self, width: int | None, height: int | None) -> float | None:
        """Calculate the scale ratio."""
        try:
            if not width or not height or width <= 0 or height <= 0:
                return None

            viewport_width = self.canvas.viewport().width()
            viewport_height = self.canvas.viewport().height()

            if self.canvas.is_fit():
                scale_x = max(1, viewport_width) / width
                scale_y = max(1, viewport_height) / height
                return min(scale_x, scale_y)
            else:
                return float(self.canvas._zoom)
        except Exception:
            return None

    def _build_status_parts(self) -> list[str]:
        """Build parts for status display."""
        parts: list[str] = []

        # Decoding strategy label
        try:
            parts.append(f"[{self.decoding_strategy.get_name()}]")
        except Exception as e:
            logger.debug("failed to get strategy name: %s", e)

        file_res = self._get_file_resolution()
        output_res = self._get_output_resolution()

        if file_res:
            parts.append(f"File {file_res[0]}x{file_res[1]}")

        if output_res:
            parts.append(f"Output {output_res[0]}x{output_res[1]}")
            scale = self._calculate_scale(output_res[0], output_res[1])
        else:
            scale = self._calculate_scale(
                file_res[0] if file_res else None, file_res[1] if file_res else None
            )

        if scale is not None:
            parts.append(f"@ {scale:.2f}x")

        return parts

    def _get_file_resolution(self) -> tuple[int, int] | None:
        if not self.image_files or self.current_index < 0:
            return None
        path = self.image_files[self.current_index]
        width, height = self._get_file_dimensions(path)
        if width and height:
            return width, height
        return None

    def _get_output_resolution(self) -> tuple[int, int] | None:
        if isinstance(self.decoding_strategy, FastViewStrategy):
            dec_w, dec_h = self._get_decoded_dimensions()
            if dec_w and dec_h:
                return dec_w, dec_h

        file_res = self._get_file_resolution()
        if file_res:
            return file_res

        return self._get_decoded_dimensions()

    def _update_status(self, extra: str = ""):
        """Update the status overlay text."""
        if self.current_index == -1 or not self.image_files:
            self._overlay_title = ""
            self._overlay_info = "Ready · Press Ctrl+O to open folder"
            if hasattr(self, "canvas"):
                self.canvas.viewport().update()
            return

        fname = os.path.basename(self.image_files[self.current_index])
        idx = self.current_index + 1
        total = len(self.image_files)

        # 상태 파츠 생성
        parts = self._build_status_parts()

        if extra:
            parts.append(str(extra))

        # 오버레이 정보 설정
        self._overlay_title = fname
        if parts:
            self._overlay_info = f"({idx}/{total})  {'  '.join(parts)}"
        else:
            self._overlay_info = f"({idx}/{total})"

        if hasattr(self, "canvas"):
            self.canvas.viewport().update()

    def _load_last_parent_dir(self):
        # Return start folder from central settings cache
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
                    with open(self._settings_path, encoding="utf-8") as f:
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
        # Update central settings cache and save all at once
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
                with open(self._settings_path, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._settings = data
                        logger.debug("settings loaded: %s", self._settings_path)
        except Exception as e:
            logger.warning("settings load failed: %s", e)
            # Ignore corrupted settings and use defaults
            self._settings = {}
        # Ensure a default background color is always available
        if not hasattr(self, "_bg_color"):
            self._bg_color = self._determine_startup_background()

    def _determine_startup_background(self) -> QColor:
        try:
            hexcol = self._settings.get("background_color")
            if isinstance(hexcol, str):
                color = QColor(hexcol)
                if color.isValid():
                    return color
                logger.warning("saved background_color invalid: %s", hexcol)
        except Exception as e:
            logger.warning("failed to parse background_color: %s", e)
        return QColor(0, 0, 0)

    def open_folder(self):
        try:
            start_dir = self._load_last_parent_dir()
        except Exception:
            start_dir = os.path.expanduser("~")
        try:
            dir_path = QFileDialog.getExistingDirectory(self, "Open Folder", start_dir)
        except Exception:
            dir_path = None
        if not dir_path:
            return

        # 새 폴더 진입: 기존 세션 상태 정리
        try:
            # 1) 로더 상태 초기화 (무시/보류 제거)
            if hasattr(self, "loader"):
                try:
                    # 최소화: 무시 집합/펜딩 초기화
                    self.loader._ignored.clear()
                    self.loader._pending.clear()
                    # 최신 요청 맵이 있으면 초기화
                    if hasattr(self.loader, "_latest_id"):
                        self.loader._latest_id.clear()
                except Exception:
                    pass
            # 2) 캐시/표시 초기화
            self.pixmap_cache.clear()
            self.current_index = -1
            try:
                empty = QPixmap(1, 1)
                empty.fill(Qt.GlobalColor.transparent)
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
                    if lower.endswith(
                        (
                            ".jpg",
                            ".jpeg",
                            ".png",
                            ".bmp",
                            ".gif",
                            ".webp",
                            ".tif",
                            ".tiff",
                        )
                    ):
                        files.append(p)
            files.sort()
            self.image_files = files
        except Exception:
            self.image_files = []

        # 인덱스/상태 갱신 및 첫 이미지 표시
        if not self.image_files:
            self.setWindowTitle("Image Viewer")
            self._update_status("No images found.")
            return
        self.current_index = 0
        with contextlib.suppress(Exception):
            self._save_last_parent_dir(dir_path)
        self.setWindowTitle(
            f"Image Viewer - {os.path.basename(self.image_files[self.current_index])}"
        )
        self.display_image()
        self.maintain_decode_window(back=0, ahead=5)

    def display_image(self) -> None:
        if self.current_index == -1:
            return
        image_path = self.image_files[self.current_index]
        self.setWindowTitle(f"Image Viewer - {os.path.basename(image_path)}")
        logger.debug("display_image: idx=%s path=%s", self.current_index, image_path)

        # 캐시가 있더라도 원본 해상도보다 작은 썸네일이면 현재 표시에는 사용하지 않고 재디코딩(전체) 요청
        if image_path in self.pixmap_cache:

            pix = self.pixmap_cache.pop(image_path)
            self.pixmap_cache[image_path] = pix
            logger.debug(
                    "display_image: cache-hit(full) path=%s cache_size=%s",
                    image_path,
                    len(self.pixmap_cache),
                )
            self.update_pixmap(pix)
            return
            """
            use_cached = True
            try:
                if (
                    orig_w
                    and orig_h
                    and (pix.width() < orig_w or pix.height() < orig_h)
                ):
                    use_cached = False
            except Exception:
                use_cached = True
            if use_cached:
                self.pixmap_cache[image_path] = pix
                logger.debug(
                    "display_image: cache-hit(full) path=%s cache_size=%s",
                    image_path,
                    len(self.pixmap_cache),
                )
                self.update_pixmap(pix)
                return
            else:
                logger.debug(
                    "display_image: cache-present(thumbnail) -> request full decode"
                )
                # 썸네일 캐시는 유지(다른 경로에서 재사용 가능), 현재 표시만 전체 디코딩 요청
                self.pixmap_cache[image_path] = pix"""
        else:

            self._update_status("Loading...")

            # fast view 모드에서는 뷰포트에 맞춰 축소 디코딩
            target_w = target_h = None
            if isinstance(self.decoding_strategy, FastViewStrategy) :
                screen = (
                    self.windowHandle().screen()
                    if self.windowHandle()
                    else QApplication.primaryScreen()
                )
                if screen is not None:
                    size = screen.size()
                    target_w, target_h = self.decoding_strategy.get_target_size(
                        int(size.width()), int(size.height())
                    )

            self.loader.request_load(image_path, target_w, target_h, "both")

    def on_image_ready(
        self, path: str, image_data: Any | None, error: Any | None
    ) -> None:
        # Drop late results for items no longer present (e.g., deleted)
        try:
            if path not in self.image_files:
                logger.debug("on_image_ready drop: path not in image_files: %s", path)
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
            if hasattr(self, "canvas"):
                self.canvas.viewport().update()
            return

        try:
            shape = getattr(image_data, "shape", None)
            logger.debug("on_image_ready ok: path=%s shape=%s", path, shape)
        except Exception:
            logger.debug("on_image_ready ok: path=%s", path)

        if image_data is not None:
            height, width, _ = image_data.shape
            bytes_per_line = 3 * width
            q_image = QImage(
                image_data.data,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGB888,
            )
            pixmap = QPixmap.fromImage(q_image)

            # 현재 이미지라면 최근 디코딩 해상도 기록
            if path == self.image_files[self.current_index]:
                with contextlib.suppress(Exception):
                    self._current_decoded_size = (width, height)

            if path in self.pixmap_cache:
                self.pixmap_cache.pop(path)
            self.pixmap_cache[path] = pixmap
            if len(self.pixmap_cache) > self.cache_size:
                self.pixmap_cache.popitem(last=False)
            logger.debug("on_image_ready cache_size=%s", len(self.pixmap_cache))

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
            self._update_status("Image load failed")

    def keyPressEvent(self, event):
        if not self.image_files:
            return
        key = event.key()
        if key == Qt.Key.Key_Right:
            self.next_image()
        elif key == Qt.Key.Key_Left:
            self.prev_image()
        elif key == Qt.Key.Key_A:
            # 좌측 90도 회전
            with contextlib.suppress(Exception):
                self.canvas.rotate_by(-90)
        elif key == Qt.Key.Key_D:
            # 우측 90도 회전
            with contextlib.suppress(Exception):
                self.canvas.rotate_by(90)
        elif key == Qt.Key.Key_Delete:
            self.delete_current_file()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
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
        logger.debug("prefetch window: idx=%s range=[%s..%s]", i, start, end)
        for idx in range(start, end + 1):
            path = self.image_files[idx]
            if path not in self.pixmap_cache:
                target_w = target_h = None
                fast_view_action = getattr(self, "fast_view_action", None)
                fast_view_enabled = bool(fast_view_action and fast_view_action.isChecked())
                if fast_view_enabled and not self.decode_full:
                    screen = (
                        self.windowHandle().screen()
                        if self.windowHandle()
                        else QApplication.primaryScreen()
                    )
                    if screen is not None:
                        sz = screen.size()
                        target_w = int(sz.width())
                        target_h = int(sz.height())
                logger.debug(
                    "prefetch request: path=%s target=(%s,%s)", path, target_w, target_h
                )
                self.loader.request_load(path, target_w, target_h, "both")

    def _unignore_decode_window(self, back: int = 1, ahead: int = 4) -> None:
        try:
            if not self.image_files:
                return
            n = len(self.image_files)
            i = self.current_index
            start = max(0, i - back)
            end = min(n - 1, i + ahead)
            for idx in range(start, end + 1):
                try:
                    p = self.image_files[idx]
                    if hasattr(self, "loader"):
                        self.loader.unignore_path(p)
                except Exception:
                    pass
        except Exception:
            pass

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
        if (
            not self.image_files
            or self.current_index < 0
            or self.current_index >= len(self.image_files)
        ):
            logger.debug("[delete] abort: no images or invalid index")
            return
        del_path = self.image_files[self.current_index]
        abs_path = os.path.abspath(del_path)
        logger.debug(
            "[delete] start: idx=%s, del_path=%s, abs_path=%s, total=%s",
            self.current_index,
            del_path,
            abs_path,
            len(self.image_files),
        )

        # 확인 다이얼로그
        proceed = True
        base = os.path.basename(del_path)
        ret = QMessageBox.question(
            self,
            "휴지통으로 이동",
            f"이 파일을 휴지통으로 이동하시겠습니까?\n{base}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        proceed = ret == QMessageBox.StandardButton.Yes
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
            logger.debug(
                "[delete] switch image: %s -> %s", self.current_index, new_index
            )
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
            # gc, _time imported at module top

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
                # time, send2trash imported at module top

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
                        logger.debug(
                            "[delete] trash failed attempt %s: %s", attempt, ex
                        )
                        time.sleep(0.2)
                if last_err is not None:
                    raise last_err
            except Exception:
                raise
        except Exception as e:
            logger.debug("[delete] trash final error: %s", e)
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
            if hasattr(self, "loader"):
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
                    logger.debug(
                        "[delete] index adjust: %s -> %s", old_idx, self.current_index
                    )
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
                empty.fill(Qt.GlobalColor.transparent)
                self.canvas.set_pixmap(empty)
            except Exception as ex:
                logger.debug("[delete] clear view error: %s", ex)
            self.setWindowTitle("Image Viewer")
            self._update_status()
            return
        try:
            logger.debug(
                "[delete] show current: idx=%s, total=%s",
                self.current_index,
                len(self.image_files),
            )
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
        if hasattr(self, "fit_action"):
            self.fit_action.setChecked(True)
        if hasattr(self, "actual_action"):
            self.actual_action.setChecked(False)
        self.canvas.apply_current_view()

    def choose_actual(self):
        self.canvas._preset_mode = "actual"
        self.canvas._zoom = 1.0
        if hasattr(self, "fit_action"):
            self.fit_action.setChecked(False)
        if hasattr(self, "actual_action"):
            self.actual_action.setChecked(True)
        self.canvas.apply_current_view()

    def toggle_hq_downscale(self):
        if hasattr(self, "hq_downscale_action"):
            enabled = self.hq_downscale_action.isChecked()
            self.canvas._hq_downscale = enabled
            self.canvas._hq_pixmap = None
            if self.canvas.is_fit():
                self.canvas.apply_current_view()

    # 디코딩 전략 토글: 썸네일 모드 on/off (체크=썸네일)
    def toggle_fast_view(self):
        is_fast_view = self.fast_view_action.isChecked()
        # 전략 전환
        if is_fast_view:
            self.decoding_strategy = FastViewStrategy()
            logger.debug("switched to FastViewStrategy")
        else:
            self.decoding_strategy = FullStrategy()
            logger.debug("switched to FullStrategy")

        # 설정 저장: 썸네일 모드 상태만 저장
        self._save_settings_key("fast_view_enabled", is_fast_view)

        # 전략에 따라 고품질 축소 옵션 활성화/비활성화
        self.hq_downscale_action.setEnabled(
            self.decoding_strategy.supports_hq_downscale()
        )
        if (
            not self.decoding_strategy.supports_hq_downscale()
            and self.hq_downscale_action.isChecked()
        ):
            self.hq_downscale_action.setChecked(False)
            self.canvas._hq_downscale = False

        # 현재 캐시를 비워 새 전략으로 비교가 즉시 가능하도록 함
        self.pixmap_cache.clear()
        # 현재 이미지를 재표시 및 프리패치 재요청
        self.display_image()
        self.maintain_decode_window()

    def snap_to_global_view(self):
        if hasattr(self, "fit_action") and self.fit_action.isChecked():
            self.choose_fit()
        else:
            self.choose_actual()

    # 배경색 설정/동기화
    def _apply_background(self):
        with contextlib.suppress(Exception):
            self.canvas.setBackgroundBrush(self._bg_color)

    def _sync_bg_checks(self):
        try:
            is_black = self._bg_color == QColor(0, 0, 0)
            is_white = self._bg_color == QColor(255, 255, 255)
            if hasattr(self, "bg_black_action"):
                self.bg_black_action.setChecked(bool(is_black))
            if hasattr(self, "bg_white_action"):
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
            pass
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

            # 0) 트림 민감도 프로파일 선택 (기본/공격적)
            prof_box = QMessageBox(self)
            prof_box.setWindowTitle("트림 민감도")
            prof_box.setText("어떤 프로파일로 트림할까요?")
            btn_norm = prof_box.addButton("기본", QMessageBox.ButtonRole.AcceptRole)
            btn_agg = prof_box.addButton("공격적", QMessageBox.ButtonRole.ActionRole)
            btn_cancel = prof_box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
            prof_box.setDefaultButton(btn_norm)
            prof_box.exec()
            clicked_prof = prof_box.clickedButton()
            if clicked_prof is btn_cancel or clicked_prof is None:
                return
            profile = "aggressive" if clicked_prof is btn_agg else "normal"

            # 1) 저장 모드 선택 (덮어씌우기/사본/취소)
            mode_box = QMessageBox(self)
            mode_box.setWindowTitle("트림")
            mode_box.setText(
                "Stats 방식으로 트림하겠습니다.\n(덮어씌우기, 따로 저장, 취소)"
            )
            overwrite_btn = mode_box.addButton(
                "덮어씌우기", QMessageBox.ButtonRole.AcceptRole
            )
            saveas_btn = mode_box.addButton(
                "사본 저장(_trimmed)", QMessageBox.ButtonRole.ActionRole
            )
            cancel_btn = mode_box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
            mode_box.setDefaultButton(overwrite_btn)
            mode_box.exec()
            clicked = mode_box.clickedButton()
            if clicked is cancel_btn or clicked is None:
                return
            overwrite = clicked is overwrite_btn

            if not overwrite:
                # 사본 저장: 백그라운드 스레드 일괄 처리 + 진행 대화상자
                paths = list(self.image_files)
                dlg = TrimProgressDialog(self)

                # 동기 처리
                worker = TrimBatchWorker(paths, profile)

                def _on_progress(total: int, index: int, name: str):
                    dlg.on_progress(total, index, name)

                worker.progress.connect(_on_progress)
                worker.finished.connect(dlg.accept)
                worker.run()
                dlg.exec()
                self.maintain_decode_window()
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
                preview = make_trim_preview(path, crop)
                if preview is None:
                    continue
                prev_pix = (
                    self.canvas._pix_item.pixmap() if self.canvas._pix_item else None
                )
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
                yes = box.addButton("Accept (Y)", QMessageBox.ButtonRole.YesRole)
                no = box.addButton("Reject (N)", QMessageBox.ButtonRole.NoRole)
                abort_btn = box.addButton(
                    "Abort (A)", QMessageBox.ButtonRole.RejectRole
                )
                # Y/N/A 단축키 동작 추가: 단축키로 버튼 클릭을 트리거
                try:
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
                    accepted = clicked_btn is yes

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

                # 로그: 덮어쓰기 직전 상태 출력
                logger.debug("[trim] overwrite prep: %s", path)
                displaying = False
                cached = False

                with contextlib.suppress(Exception):
                    displaying = (
                        self.current_index >= 0
                        and self.current_index < len(self.image_files)
                        and self.image_files[self.current_index] == path
                    )

                with contextlib.suppress(Exception):
                    cached = path in self.pixmap_cache

                logger.debug(
                    "[trim] overwrite start: %s, displaying=%s, cached=%s",
                    path,
                    displaying,
                    cached,
                )

                try:
                    apply_trim_to_file(path, crop, overwrite=True)
                    logger.debug("[trim] overwrite ok: %s", path)
                except Exception:
                    # _tb imported at module top
                    logger.debug(
                        "[trim] overwrite error: %s\n%s", path, _tb.format_exc()
                    )
                    QMessageBox.critical(
                        self,
                        "Trim 오류",
                        f"파일 저장 실패: {os.path.basename(path)}",
                    )
                    continue

                # 캐시 무효화 및 필요시 재표시
                with contextlib.suppress(Exception):
                    self.pixmap_cache.pop(path, None)
                if (
                    self.current_index >= 0
                    and self.current_index < len(self.image_files)
                    and self.image_files[self.current_index] == path
                ):
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
        if hasattr(self, "fullscreen_action"):
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
            with contextlib.suppress(Exception):
                self.restoreGeometry(geom)
        self.menuBar().setVisible(True)
        if hasattr(self, "fullscreen_action"):
            self.fullscreen_action.setChecked(False)
        self.setUpdatesEnabled(True)
        self.canvas.apply_current_view()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()

    # --------------- Explorer Mode ----------------
    def toggle_view_mode(self) -> None:
        """View Mode <-> Explorer Mode 전환"""
        self.explorer_state.view_mode = not self.explorer_state.view_mode
        self._update_ui_for_mode()
        logger.debug("view_mode toggled: %s", self.explorer_state.view_mode)

    def _update_ui_for_mode(self) -> None:
        """모드 변경에 따라 UI 재구성"""
        if self.explorer_state.view_mode:
            self._setup_view_mode()
        else:
            self._setup_explorer_mode()

        # 메뉴 동기화
        if hasattr(self, "explorer_mode_action"):
            self.explorer_mode_action.setChecked(not self.explorer_state.view_mode)

    def _setup_view_mode(self) -> None:
        """View Mode 설정: 중앙 캔버스만 표시"""
        try:
            # Explorer Grid 로더 연결 해제(점프 후 UI 부하 차단)
            try:
                grid = getattr(self.explorer_state, "_explorer_grid", None)
                if grid is not None:
                    grid.set_loader(None)
            except Exception:
                pass

            current_widget = self.centralWidget()

            # Check if we're using the stacked widget architecture
            if isinstance(current_widget, QStackedWidget):
                # Good: stacked widget exists, just switch to canvas page (Index 0)
                try:
                    current_widget.setCurrentIndex(0)
                    logger.debug("switched to View Mode via stacked widget")
                except Exception as e:
                    logger.warning("failed to switch stacked widget page: %s", e)
            else:
                # Fallback: manually set canvas as central widget
                try:
                    # Verify canvas is valid
                    if self.canvas:
                        parent = (
                            self.canvas.parent()
                        )  # This will raise if C++ object deleted

                        # Set canvas as central widget
                        self.setCentralWidget(self.canvas)
                        self.canvas.show()
                        logger.debug("switched to View Mode with existing canvas")
                except RuntimeError as e:
                    # Canvas C++ object is deleted
                    logger.warning("canvas C++ object is invalid: %s", e)
                    try:
                        self.canvas = ImageCanvas(self)
                        self.setCentralWidget(self.canvas)
                        logger.warning("canvas recreated and set as central widget")
                    except Exception as e2:
                        logger.error("failed to recreate canvas: %s", e2)
                except Exception as e:
                    logger.warning("failed to set canvas as central widget: %s", e)
                    try:
                        self.canvas = ImageCanvas(self)
                        self.setCentralWidget(self.canvas)
                        logger.warning("canvas recreated and set as central widget")
                    except Exception as e2:
                        logger.error("failed to recreate canvas: %s", e2)

        except Exception as e:
            logger.error("failed to setup view mode: %s", e)

    def open_settings(self):
        try:
            dlg = SettingsDialog(self, self)
            dlg.exec()
        except Exception as e:
            logger.error("failed to open settings: %s", e)

    def apply_thumbnail_settings(
        self,
        width: int | None = None,
        height: int | None = None,
        hspacing: int | None = None,
    ) -> None:
        try:
            grid = getattr(self.explorer_state, "_explorer_grid", None)
            if width is not None:
                self._save_settings_key("thumbnail_width", int(width))
            if height is not None:
                self._save_settings_key("thumbnail_height", int(height))
            if grid:
                try:
                    if hasattr(grid, "set_thumbnail_size_wh") and (
                        width is not None or height is not None
                    ):
                        w = int(
                            width if width is not None else grid.get_thumbnail_size()[0]
                        )
                        h = int(
                            height
                            if height is not None
                            else grid.get_thumbnail_size()[1]
                        )
                        grid.set_thumbnail_size_wh(w, h)
                    elif (
                        hasattr(grid, "set_thumbnail_size")
                        and width is not None
                        and height is not None
                    ):
                        # Fallback: square
                        grid.set_thumbnail_size(int(width))
                except Exception:
                    pass
            if hspacing is not None:
                self._save_settings_key("thumbnail_hspacing", int(hspacing))
                if grid and hasattr(grid, "set_horizontal_spacing"):
                    grid.set_horizontal_spacing(int(hspacing))
        except Exception as e:
            logger.debug("apply_thumbnail_settings failed: %s", e)

    def _setup_explorer_mode(self) -> None:
        """Explorer Mode 설정: 좌측 트리 + 우측 그리드"""
        try:
            # QSplitter, QStackedWidget imported at module top
            from image_viewer.ui_explorer_grid import ThumbnailGridWidget
            from image_viewer.ui_explorer_tree import FolderTreeWidget

            current_widget = self.centralWidget()
            stacked_widget = None

            if isinstance(current_widget, QStackedWidget):
                stacked_widget = current_widget
                logger.debug("reusing existing stacked widget")
            else:
                stacked_widget = QStackedWidget()
                if isinstance(current_widget, ImageCanvas):
                    self.takeCentralWidget()
                    stacked_widget.addWidget(current_widget)
                elif self.canvas:
                    stacked_widget.addWidget(self.canvas)
                self.setCentralWidget(stacked_widget)
                logger.debug("created stacked widget for mode switching")

            # 이미 Page 1이 있으면 그대로 재사용(그리드/트리/썸네일 캐시 보존)
            if stacked_widget.count() > 1:
                try:
                    page1 = stacked_widget.widget(1)
                    # 기존 grid 참조가 있으면 로더만 재연결
                    grid = getattr(self.explorer_state, "_explorer_grid", None)
                    if grid is not None:
                        with contextlib.suppress(Exception):
                            grid.set_loader(self.thumb_loader)
                except Exception:
                    pass
                stacked_widget.setCurrentIndex(1)
                logger.debug("switched to existing Explorer page")
                return

            # 최초 생성 경로
            splitter = QSplitter(Qt.Orientation.Horizontal)
            tree = FolderTreeWidget()
            grid = ThumbnailGridWidget()

            try:
                grid.set_loader(self.thumb_loader)
            except Exception as ex:
                logger.debug("failed to attach thumb_loader: %s", ex)

            # 설정 적용
            try:
                if (
                    "thumbnail_width" in self._settings
                    or "thumbnail_height" in self._settings
                    or "thumbnail_size" in self._settings
                ):
                    w = int(
                        self._settings.get(
                            "thumbnail_width", self._settings.get("thumbnail_size", 256)
                        )
                    )
                    h = int(
                        self._settings.get(
                            "thumbnail_height",
                            self._settings.get("thumbnail_size", 195),
                        )
                    )
                    if hasattr(grid, "set_thumbnail_size_wh"):
                        grid.set_thumbnail_size_wh(w, h)
                    elif hasattr(grid, "set_thumbnail_size"):
                        grid.set_thumbnail_size(int(w))
                if "thumbnail_hspacing" in self._settings:
                    grid.set_horizontal_spacing(
                        int(self._settings.get("thumbnail_hspacing", 10))
                    )
            except Exception as e:
                logger.debug("failed to apply grid settings: %s", e)

            splitter.addWidget(tree)
            splitter.addWidget(grid)
            splitter.setSizes([300, 700])

            # 신호 연결
            tree.folder_selected.connect(
                lambda p: self._on_explorer_folder_selected(p, grid)
            )
            grid.image_selected.connect(lambda p: self._on_explorer_image_selected(p))

            # Page 1 추가 및 전환
            stacked_widget.addWidget(splitter)
            stacked_widget.setCurrentIndex(1)

            self.explorer_state._explorer_tree = tree
            self.explorer_state._explorer_grid = grid

            # 현재 폴더 자동 로드
            if self.image_files:
                current_dir = str(Path(self.image_files[0]).parent)
                tree.set_root_path(current_dir)
                grid.load_folder(current_dir)

            logger.debug("switched to Explorer Mode")
        except Exception as e:
            logger.error("failed to setup explorer mode: %s", e)

    def _on_explorer_folder_selected(self, folder_path: str, grid) -> None:
        """탐색기에서 폴더 선택 시"""
        try:
            grid.load_folder(folder_path)
            logger.debug("explorer folder selected: %s", folder_path)
        except Exception as e:
            logger.error(
                "failed to load folder in explorer: %s, error=%s", folder_path, e
            )

    def _on_explorer_image_selected(self, image_path: str) -> None:
        """탐색기에서 이미지 선택 시"""
        try:
            # View Mode로 전환하고 해당 이미지 표시
            if not self.explorer_state.view_mode:
                self.explorer_state.view_mode = True
                self._update_ui_for_mode()

            # 포커스 보장: 화살표/단축키 즉시 동작
            try:
                self.setFocus(Qt.FocusReason.OtherFocusReason)
                if hasattr(self, "canvas") and self.canvas is not None:
                    self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)
            except Exception:
                pass

            # jump 거리 계산(디버깅용)
            try:
                cur_idx = self.current_index
                tgt_idx = (
                    self.image_files.index(image_path)
                    if image_path in self.image_files
                    else None
                )
                logger.debug(
                    "explorer select: cur=%s tgt=%s path=%s",
                    cur_idx,
                    tgt_idx,
                    image_path,
                )
            except Exception:
                pass

            # image_path로 이미지 표시
            if image_path in self.image_files:
                self.current_index = self.image_files.index(image_path)
            else:
                # 새 폴더인 경우 먼저 폴더를 열기
                new_folder = str(Path(image_path).parent)
                logger.debug("explorer select: open_folder_at %s", new_folder)
                self.open_folder_at(new_folder)
                if image_path in self.image_files:
                    self.current_index = self.image_files.index(image_path)

            logger.debug(
                "explorer select display: idx=%s path=%s",
                self.current_index,
                image_path,
            )
            self.display_image()
            # 전환 직후 과도한 프리페치 방지
            self.maintain_decode_window(back=0, ahead=1)
            logger.debug("explorer image selected done: %s", image_path)
        except Exception as e:
            logger.error(
                "failed to select image in explorer: %s, error=%s", image_path, e
            )

    def open_folder_at(self, folder_path: str) -> None:
        """특정 폴더를 직접 열기 (탐색기 모드에서 사용)"""
        try:
            if not os.path.isdir(folder_path):
                logger.warning("not a directory: %s", folder_path)
                return

            # 세션 상태 정리: Viewer/Thumbnail 로더 모두 대기/무시 목록 초기화
            try:
                if hasattr(self, "loader"):
                    self.loader._ignored.clear()
                    self.loader._pending.clear()
                    if hasattr(self.loader, "_latest_id"):
                        self.loader._latest_id.clear()
            except Exception:
                pass
            try:
                if hasattr(self, "thumb_loader") and self.thumb_loader is not None:
                    self.thumb_loader._ignored.clear()
                    self.thumb_loader._pending.clear()
                    if hasattr(self.thumb_loader, "_latest_id"):
                        self.thumb_loader._latest_id.clear()
            except Exception:
                pass

            self.pixmap_cache.clear()
            self.current_index = -1

            # 이미지 목록 재구성
            files = []
            for name in os.listdir(folder_path):
                p = os.path.join(folder_path, name)
                if os.path.isfile(p):
                    lower = name.lower()
                    if lower.endswith(
                        (
                            ".jpg",
                            ".jpeg",
                            ".png",
                            ".bmp",
                            ".gif",
                            ".webp",
                            ".tif",
                            ".tiff",
                        )
                    ):
                        files.append(p)
            files.sort()
            self.image_files = files

            if not self.image_files:
                self.setWindowTitle("Image Viewer")
                self._update_status("No images found.")
                return

            self.current_index = 0
            self._save_last_parent_dir(folder_path)
            self.setWindowTitle(
                f"Image Viewer - {os.path.basename(self.image_files[self.current_index])}"
            )
            # 초기 프리패치도 경량화
            self.maintain_decode_window(back=0, ahead=3)

            logger.debug(
                "folder opened: %s, images=%d", folder_path, len(self.image_files)
            )
        except Exception as e:
            logger.error("failed to open_folder_at: %s, error=%s", folder_path, e)


if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()

    app = QApplication(sys.argv)
    viewer = ImageViewer()
    viewer.showMaximized()
    sys.exit(app.exec())
