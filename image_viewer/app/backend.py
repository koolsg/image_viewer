from __future__ import annotations

import contextlib
import json
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtQuick import QQuickImageProvider

from image_viewer.app.state.crop_state import CropState
from image_viewer.app.state.explorer_state import ExplorerState
from image_viewer.app.state.settings_state import SettingsState
from image_viewer.app.state.tasks_state import TasksState
from image_viewer.app.state.viewer_state import ViewerState
from image_viewer.crop.crop import apply_crop_to_file
from image_viewer.image_engine.engine import ImageEngine
from image_viewer.infra.logger import get_logger
from image_viewer.infra.path_utils import abs_dir_str, abs_path_str, db_key
from image_viewer.infra.settings_manager import SettingsManager
from image_viewer.ops.crop_controller import RectN, clamp_rect_n
from image_viewer.ops.file_operations import (
    copy_files_to_clipboard,
    cut_files_to_clipboard,
    delete_files_to_recycle_bin,
    get_files_from_clipboard,
    paste_files,
    rename_file,
)
from image_viewer.ops.webp_converter import ConvertController
from image_viewer.ui.qml_models import QmlImageGridModel

_logger = get_logger("backend")
_thumb_cache_logger = get_logger("thumb_cache")
_BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
_GEN_PATH_SPLIT_MAX = 1
_GEN_PATH_PARTS = 2


@contextlib.contextmanager
def _suppress_expected(*exceptions: type[BaseException]):
    """Suppress expected exception types and log unexpected ones.

    NOTE: kept narrow and only used around GUI/Qt conversion quirks.
    """

    try:
        yield
    except exceptions:
        return
    except Exception as e:  # pragma: no cover - defensive logging
        _logger.exception("Unexpected error in suppressed block: %s", e)


class EngineImageProvider(QQuickImageProvider):
    """QML image provider that fetches pixmaps from ImageEngine cache."""

    def __init__(self, engine: ImageEngine) -> None:
        super().__init__(QQuickImageProvider.ImageType.Pixmap)
        self._engine = engine

    def requestPixmap(self, id: str, size: Any, requestedSize: Any) -> QPixmap:
        parts = str(id).split("/", _GEN_PATH_SPLIT_MAX)
        path = parts[1] if len(parts) == _GEN_PATH_PARTS and parts[0].isdigit() else str(id)

        pix = self._engine.get_cached_pixmap(path)
        if pix and not pix.isNull():
            return pix

        # Handle percent-encoded paths.
        with _suppress_expected(TypeError, ValueError, OSError):
            path_dec = QUrl.fromPercentEncoding(path.encode("utf-8"))
            pix = self._engine.get_cached_pixmap(path_dec)
            if pix and not pix.isNull():
                return pix

        return QPixmap()


class ThumbImageProvider(QQuickImageProvider):
    """QML image provider for thumbnail PNG bytes (image://thumb/<gen>/<key>)."""

    def __init__(self, thumb_bytes_by_key: dict[str, bytes], *, max_cached_pixmaps: int = 512) -> None:
        super().__init__(QQuickImageProvider.ImageType.Pixmap)
        self._thumb_bytes_by_key = thumb_bytes_by_key
        self._max_cached_pixmaps = max(0, int(max_cached_pixmaps))
        # Cache decoded pixmaps to avoid repeatedly running QPixmap.loadFromData()
        # when QML requests the same thumb many times (scrolling/relayout).
        # Cache key includes the provider id (which may include a generation prefix)
        # so that URL-based cache-busting continues to work.
        self._pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0
        self._requests = 0

    def _log_cache_stats(self) -> None:
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total) if total else 0.0
        _thumb_cache_logger.debug(
            "thumb_lru stats: requests=%d hits=%d misses=%d hit_rate=%.1f%% cache=%d evictions=%d",
            self._requests,
            self._cache_hits,
            self._cache_misses,
            hit_rate * 100.0,
            len(self._pixmap_cache),
            self._cache_evictions,
        )

    def _cache_get(self, cache_id: str) -> QPixmap | None:
        if self._max_cached_pixmaps <= 0:
            return None
        with self._cache_lock:
            pix = self._pixmap_cache.get(cache_id)
            if pix is None:
                self._cache_misses += 1
                # Log periodic summaries so we can see whether the cache is actually useful.
                if (self._cache_hits + self._cache_misses) % 200 == 0:
                    self._log_cache_stats()
                return None
            # LRU: mark as most recently used
            self._pixmap_cache.move_to_end(cache_id)
            self._cache_hits += 1
            _thumb_cache_logger.debug(
                "thumb_lru HIT: id=%s cache=%d hits=%d misses=%d",
                cache_id,
                len(self._pixmap_cache),
                self._cache_hits,
                self._cache_misses,
            )
            return pix

    def _cache_put(self, cache_id: str, pix: QPixmap) -> None:
        if self._max_cached_pixmaps <= 0:
            return
        with self._cache_lock:
            self._pixmap_cache[cache_id] = pix
            self._pixmap_cache.move_to_end(cache_id)
            while len(self._pixmap_cache) > self._max_cached_pixmaps:
                evicted_id, _ = self._pixmap_cache.popitem(last=False)
                self._cache_evictions += 1
                _thumb_cache_logger.debug(
                    "thumb_lru EVICT: id=%s cache=%d evictions=%d",
                    evicted_id,
                    len(self._pixmap_cache),
                    self._cache_evictions,
                )

    def requestPixmap(self, id: str, size: Any, requestedSize: Any) -> QPixmap:
        self._requests += 1
        cache_id = str(id)
        pix_cached = self._cache_get(cache_id)
        if pix_cached is not None and not pix_cached.isNull():
            return pix_cached

        parts = cache_id.split("/", _GEN_PATH_SPLIT_MAX)
        key = parts[1] if len(parts) == _GEN_PATH_PARTS and parts[0].isdigit() else cache_id

        data = self._thumb_bytes_by_key.get(key)
        if not data:
            with _suppress_expected(TypeError, ValueError, OSError):
                key_dec = QUrl.fromPercentEncoding(str(key).encode("utf-8"))
                data = self._thumb_bytes_by_key.get(str(key_dec))

        if not data:
            pix = QPixmap(1, 1)
            pix.fill(Qt.GlobalColor.transparent)
            return pix

        pix = QPixmap()
        if not pix.loadFromData(data):
            placeholder = QPixmap(1, 1)
            placeholder.fill(Qt.GlobalColor.transparent)
            return placeholder

        self._cache_put(cache_id, pix)

        return pix


def _handle_qjs_value_paths(payload: object) -> list[str] | None:
    """Handle QJSValue (common from QML) into list[str] for file paths."""

    try:
        if payload.__class__.__name__ != "QJSValue":
            return None
        js_value = payload  # type: ignore[assignment]
        if hasattr(js_value, "isArray") and js_value.isArray():  # type: ignore[attr-defined]
            result: list[str] = []
            length_prop = js_value.property("length")  # type: ignore[attr-defined]
            length = length_prop.toInt()  # type: ignore[attr-defined]
            for i in range(length):
                elem = js_value.property(i)  # type: ignore[attr-defined]
                if elem.isString():  # type: ignore[attr-defined]
                    result.append(elem.toString())  # type: ignore[attr-defined]
                elif not elem.isNull() and not elem.isUndefined():  # type: ignore[attr-defined]
                    result.append(str(elem.toVariant()))  # type: ignore[attr-defined]
            return result

        if js_value.isString():  # type: ignore[attr-defined]
            return [js_value.toString()]  # type: ignore[attr-defined]

        variant = js_value.toVariant()  # type: ignore[attr-defined]
        return [str(variant)]
    except Exception:
        return None


def _coerce_paths(payload: object) -> list[str]:  # noqa: PLR0911
    """Coerce a QML-provided payload into a list of filesystem paths."""

    if payload is None:
        return []

    result = _handle_qjs_value_paths(payload)
    if result is not None:
        return result

    if isinstance(payload, (list, tuple, set)):
        return [str(p) for p in payload if p is not None]

    if hasattr(payload, "toList"):
        try:
            lst = payload.toList()  # type: ignore[attr-defined]
            return [str(p) for p in lst if p is not None]
        except Exception:
            pass

    if isinstance(payload, str):
        s = str(payload)
        try:
            v = json.loads(s)
            if isinstance(v, (list, tuple)):
                return [str(p) for p in v if p is not None]
        except Exception:
            pass
        return [s]

    return [str(payload)]


class BackendFacade(QObject):
    """Single backend object exposed to QML.

    QML → Python: backend.dispatch(cmd, payload)
    Python → QML: backend.event(dict), backend.taskEvent(dict)
    QML bindings: backend.viewer / backend.explorer / backend.settings / backend.tasks
    """

    # QObject already has an .event() handler method, so we must not shadow it.
    # Expose the QML signal name as "event" while keeping a safe Python attribute.
    event_ = Signal(object, name="event")
    taskEvent = Signal(object, name="taskEvent")

    def __init__(
        self,
        engine: ImageEngine | None = None,
        settings: SettingsManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        self._engine = engine or ImageEngine()
        self._settings_mgr = settings or SettingsManager(abs_path_str(_BASE_DIR / "settings.json"))

        self._viewer = ViewerState(self)
        self._explorer = ExplorerState(self)
        self._settings = SettingsState(self)
        self._tasks = TasksState(self)
        self._crop = CropState(self)

        self._thumb_bytes_by_key: dict[str, bytes] = {}
        self.engine_image_provider = EngineImageProvider(self._engine)
        self.thumb_provider = ThumbImageProvider(self._thumb_bytes_by_key)

        self._image_model = QmlImageGridModel(self)
        self._explorer._set_image_model(self._image_model)

        self._generation = 0
        self._pending_select_path: str | None = None

        self._decoded_w: int | None = None
        self._decoded_h: int | None = None

        # Settings init
        self._settings._set_fast_view_enabled(bool(self._settings_mgr.fast_view_enabled))
        self._settings._set_background_color(str(self._settings_mgr.get("background_color", "#000000")))
        self._settings._set_press_zoom_multiplier(float(self._settings_mgr.get("press_zoom_multiplier", 3.0)))
        self._settings._set_thumbnail_width(int(self._settings_mgr.get("thumbnail_width", 220)))

        self._clipboard_paths: list[str] = []
        self._clipboard_mode: str | None = None  # "copy" | "cut"
        self._clipboard_cached_external_paths: list[str] | None = None

        self._init_webp_converter()
        self._apply_initial_decoding_strategy()
        self._setup_engine_signals()
        self._setup_clipboard_signals()

    # ---- expose state objects to QML ----
    def _get_viewer(self) -> QObject:
        return self._viewer

    viewerState = Property(QObject, _get_viewer, constant=True)  # type: ignore[arg-type]

    def _get_explorer(self) -> QObject:
        return self._explorer

    explorerState = Property(QObject, _get_explorer, constant=True)  # type: ignore[arg-type]

    def _get_settings(self) -> QObject:
        return self._settings

    settingsObj = Property(QObject, _get_settings, constant=True)  # type: ignore[arg-type]

    def _get_tasks(self) -> QObject:
        return self._tasks

    tasksState = Property(QObject, _get_tasks, constant=True)  # type: ignore[arg-type]

    def _get_crop(self) -> QObject:
        return self._crop

    cropState = Property(QObject, _get_crop, constant=True)  # type: ignore[arg-type]

    # For ergonomic QML usage:
    #   backend.viewer / backend.explorer / backend.settings / backend.tasks
    viewer = Property(QObject, _get_viewer, constant=True)  # type: ignore[arg-type]
    explorer = Property(QObject, _get_explorer, constant=True)  # type: ignore[arg-type]
    settings = Property(QObject, _get_settings, constant=True)  # type: ignore[arg-type]
    tasks = Property(QObject, _get_tasks, constant=True)  # type: ignore[arg-type]
    crop = Property(QObject, _get_crop, constant=True)  # type: ignore[arg-type]

    # ---- init wiring ----
    def _init_webp_converter(self) -> None:
        self._webp_controller = ConvertController()
        self._webp_completed = 0
        self._webp_total = 0

        self._webp_controller.progress.connect(self._on_webp_progress)
        self._webp_controller.log.connect(self._on_webp_log)
        self._webp_controller.finished.connect(self._on_webp_finished)
        self._webp_controller.canceled.connect(self._on_webp_canceled)
        self._webp_controller.error.connect(self._on_webp_error)

    def _apply_initial_decoding_strategy(self) -> None:
        if self._settings._get_fast_view_enabled():
            self._engine.set_decoding_strategy(self._engine.get_fast_strategy())
        else:
            self._engine.set_decoding_strategy(self._engine.get_full_strategy())

    def _setup_engine_signals(self) -> None:
        self._engine.image_ready.connect(self._on_engine_image_ready)
        self._engine.file_list_updated.connect(self._on_engine_file_list_updated)
        self._engine.explorer_entries_changed.connect(self._on_engine_explorer_entries_changed)
        self._engine.explorer_thumb_rows.connect(self._on_engine_explorer_thumb_rows)
        self._engine.explorer_thumb_generated.connect(self._on_engine_explorer_thumb_generated)

    def _setup_clipboard_signals(self) -> None:
        # Best-effort: clipboard can be missing in headless tests.
        cb = QGuiApplication.clipboard()
        cb.dataChanged.connect(self._on_clipboard_changed)
        self._on_clipboard_changed()

    # ---- QML command entry ----
    # NOTE: The second argument must be a Qt-friendly variant type.
    # Using `object` here causes runtime failures when QML passes a JS object
    # (e.g. `{ index: 3 }`).
    @Slot(str, "QVariant")  # type: ignore[call-overload]
    def dispatch(self, cmd: str, payload: object | None = None) -> None:  # noqa: PLR0915, PLR0912, PLR0911
        command = str(cmd or "").strip()
        if not command:
            self.event_.emit({"type": "event", "name": "error", "level": "error", "message": "Empty cmd"})
            return

        if command == "log":
            self._handle_log_cmd(payload)
            return

        if command == "openFolder":
            self._cmd_open_folder(payload)
            return

        if command == "closeView":
            self._viewer._set_view_mode(False)
            return

        if command == "openCrop":
            self._cmd_open_crop()
            return

        if command == "closeCrop":
            self._cmd_close_crop()
            return

        if command == "cropSetAspect":
            self._cmd_crop_set_aspect(payload)
            return

        if command == "cropSetPreview":
            self._crop._set_preview_enabled(bool(_get_payload_value(payload, "value", default=False)))
            return

        if command == "cropSetFitMode":
            self._crop._set_fit_mode(bool(_get_payload_value(payload, "value", default=True)))
            return

        if command == "cropSetZoom":
            self._crop._set_fit_mode(False)
            self._crop._set_zoom(float(_get_payload_value(payload, "value", default=1.0)))
            return

        if command == "cropZoomBy":
            factor = float(_get_payload_value(payload, "factor", default=1.0))
            base = 1.0 if self._crop._get_fit_mode() else self._crop._get_zoom()
            self._crop._set_fit_mode(False)
            self._crop._set_zoom(base * factor)
            return

        if command == "cropSetRect":
            self._cmd_crop_set_rect(payload)
            return

        if command == "cropResetRect":
            self._crop._set_rect(0.25, 0.25, 0.5, 0.5)
            return

        if command == "cropSaveAs":
            self._cmd_crop_save_as(payload)
            return

        if command == "setViewMode":
            val = bool(_get_payload_value(payload, "value", default=False))
            self._viewer._set_view_mode(val)
            return

        if command == "setCurrentIndex":
            idx = int(_get_payload_value(payload, "index", default=-1))
            self._set_current_index(idx)
            return

        if command == "setFitMode":
            self._viewer._set_fit_mode(bool(_get_payload_value(payload, "value", default=True)))
            return

        if command == "setZoom":
            self._viewer._set_fit_mode(False)
            self._viewer._set_zoom(float(_get_payload_value(payload, "value", default=1.0)))
            return

        if command == "zoomBy":
            factor = float(_get_payload_value(payload, "factor", default=1.0))
            base = 1.0 if self._viewer._get_fit_mode() else self._viewer._get_zoom()
            self._viewer._set_fit_mode(False)
            self._viewer._set_zoom(base * factor)
            return

        if command == "rotateBy":
            deg = float(_get_payload_value(payload, "degrees", default=0.0))
            self._viewer._set_rotation(self._viewer._get_rotation() + deg)
            return

        if command == "resetRotation":
            self._viewer._set_rotation(0.0)
            return

        if command == "setFastViewEnabled":
            enabled = bool(_get_payload_value(payload, "value", default=False))
            self._cmd_set_fast_view(enabled)
            return

        if command == "setBackgroundColor":
            self._cmd_set_background_color(payload)
            return

        if command == "setThumbnailWidth":
            w = int(_get_payload_value(payload, "value", default=self._settings._get_thumbnail_width()))
            self._cmd_set_thumbnail_width(w)
            return

        if command == "copyFiles":
            paths = _coerce_paths(_get_payload_value(payload, "paths", default=payload))
            self._cmd_copy_files(paths)
            return

        if command == "cutFiles":
            paths = _coerce_paths(_get_payload_value(payload, "paths", default=payload))
            self._cmd_cut_files(paths)
            return

        if command == "pasteFiles":
            self._cmd_paste_files()
            return

        if command == "renameFile":
            p = str(_get_payload_value(payload, "path", default=""))
            new_name = str(_get_payload_value(payload, "newName", default=""))
            self._cmd_rename_file(p, new_name)
            return

        if command == "deleteFiles":
            paths = _coerce_paths(_get_payload_value(payload, "paths", default=payload))
            self._cmd_delete_files(paths)
            return

        if command == "revealInExplorer":
            p = str(_get_payload_value(payload, "path", default=""))
            self._cmd_reveal_in_explorer(p)
            return

        if command == "copyText":
            txt = str(_get_payload_value(payload, "text", default=""))
            self._cmd_copy_text(txt)
            return

        if command == "refreshCurrentFolder":
            self._cmd_refresh_current_folder()
            return

        if command == "refreshCurrentImage":
            self._cmd_refresh_current_image()
            return

        if command == "startWebpConvert":
            self._cmd_start_webp_convert(payload)
            return

        if command == "cancelWebpConvert":
            self._cmd_cancel_webp_convert()
            return

        self.event_.emit(
            {
                "type": "event",
                "name": "error",
                "level": "warning",
                "message": f"Unknown cmd: {command}",
            }
        )

    # ---- crop helpers ----
    def _cmd_open_crop(self) -> None:
        path = str(self._viewer._get_current_path() or "")
        if not path:
            return

        # Crop UI is a sub-mode of view mode.
        self._viewer._set_view_mode(True)
        self._crop._set_active(True)
        self._crop._set_current_path(path)
        self._crop._set_preview_enabled(False)

        # Default: free aspect.
        self._crop._set_aspect_ratio(0.0)
        self._crop._set_fit_mode(True)
        self._crop._set_zoom(1.0)

        # Image URL uses the same engine provider.
        self._crop._set_image_url(self._viewer._get_image_url())

        res = None
        with contextlib.suppress(Exception):
            res = self._engine.get_resolution(path)
        if res and res[0] and res[1]:
            self._crop._set_image_size(int(res[0]), int(res[1]))
        else:
            self._crop._set_image_size(0, 0)

        # Default rect centered (50% of area).
        self._crop._set_rect(0.25, 0.25, 0.5, 0.5)

        # Ensure we have a preview pixmap ready.
        if not self._viewer._get_image_url():
            self._request_preview(path, 2048)

    def _cmd_close_crop(self) -> None:
        self._crop._set_preview_enabled(False)
        self._crop._set_active(False)

    def _cmd_crop_set_aspect(self, payload: object | None) -> None:
        val = float(_get_payload_value(payload, "ratio", default=0.0))
        # 0 means free.
        if val <= 0:
            self._crop._set_aspect_ratio(0.0)
            return
        self._crop._set_aspect_ratio(val)

        # Re-apply current rect through the constraint clamp so the UI snaps.
        self._cmd_crop_set_rect(
            {
                "x": self._crop._get_x(),
                "y": self._crop._get_y(),
                "w": self._crop._get_w(),
                "h": self._crop._get_h(),
                "anchor": "center",
            }
        )

    def _cmd_crop_set_rect(self, payload: object | None) -> None:
        x = float(_get_payload_value(payload, "x", default=self._crop._get_x()))
        y = float(_get_payload_value(payload, "y", default=self._crop._get_y()))
        w = float(_get_payload_value(payload, "w", default=self._crop._get_w()))
        h = float(_get_payload_value(payload, "h", default=self._crop._get_h()))
        anchor = str(_get_payload_value(payload, "anchor", default="center"))

        img_w = int(self._crop._get_image_width())
        img_h = int(self._crop._get_image_height())
        # Legacy widget used 8px; normalize against original image size.
        min_w = (8.0 / img_w) if img_w > 0 else 0.01
        min_h = (8.0 / img_h) if img_h > 0 else 0.01

        cur = RectN(self._crop._get_x(), self._crop._get_y(), self._crop._get_w(), self._crop._get_h())
        prop = RectN(x, y, w, h)
        out = clamp_rect_n(
            current=cur,
            proposed=prop,
            anchor=anchor,
            aspect_ratio=float(self._crop._get_aspect_ratio()),
            min_size=(min_w, min_h),
        )
        self._crop._set_rect(out.x, out.y, out.w, out.h)

    def _cmd_crop_save_as(self, payload: object | None) -> None:
        src = str(self._crop._get_current_path() or "")
        if not src:
            return

        raw_out = _get_payload_value(payload, "outputPath", default="")
        out = str(raw_out or "")
        if out.startswith("file:"):
            url = QUrl(out)
            if url.isLocalFile():
                out = url.toLocalFile()

        out = abs_path_str(out)
        if not out:
            return

        # Compute pixel crop from normalized rect.
        res = None
        with contextlib.suppress(Exception):
            res = self._engine.get_resolution(src)
        img_w = int(res[0]) if res and res[0] else int(self._crop._get_image_width())
        img_h = int(res[1]) if res and res[1] else int(self._crop._get_image_height())
        if img_w <= 0 or img_h <= 0:
            self.taskEvent.emit(
                {
                    "type": "task",
                    "name": "cropSave",
                    "state": "error",
                    "message": "Failed to determine image size for cropping.",
                }
            )
            return

        x = float(self._crop._get_x())
        y = float(self._crop._get_y())
        w = float(self._crop._get_w())
        h = float(self._crop._get_h())

        left = round(x * img_w)
        top = round(y * img_h)
        width = round(w * img_w)
        height = round(h * img_h)

        left = max(0, min(left, img_w - 1))
        top = max(0, min(top, img_h - 1))
        width = max(1, min(width, img_w - left))
        height = max(1, min(height, img_h - top))

        crop_px = (left, top, width, height)

        try:
            apply_crop_to_file(src, crop_px, out)
            with contextlib.suppress(Exception):
                self._engine.prefetch([out], None)
        except Exception as e:
            self.taskEvent.emit(
                {
                    "type": "task",
                    "name": "cropSave",
                    "state": "error",
                    "message": str(e),
                }
            )
            return

        self.taskEvent.emit(
            {
                "type": "task",
                "name": "cropSave",
                "state": "finished",
                "outputPath": out,
                "crop": {"left": left, "top": top, "width": width, "height": height},
            }
        )

    # ---- cmd handlers ----
    def _handle_log_cmd(self, payload: object | None) -> None:
        level = str(_get_payload_value(payload, "level", default="debug")).lower()
        msg = str(_get_payload_value(payload, "message", default=""))
        if not msg:
            return

        # integrate into Python logging pipeline
        if level == "info":
            _logger.info("[QML] %s", msg)
        elif level in {"warn", "warning"}:
            _logger.warning("[QML] %s", msg)
        elif level == "error":
            _logger.error("[QML] %s", msg)
        else:
            _logger.debug("[QML] %s", msg)

        # reliable stderr visibility (same as previous qmlDebug)
        try:
            print(f"\033[95m[QML] {msg}\033[0m", file=sys.stderr, flush=True)
        except Exception:
            print(f"[QML] {msg}", file=sys.stderr, flush=True)

    def _cmd_open_folder(self, payload: object | None) -> None:
        raw = _get_payload_value(payload, "path", default=payload)
        p = str(raw or "")
        if p.startswith("file:"):
            url = QUrl(p)
            if url.isLocalFile():
                p = url.toLocalFile()

        folder = abs_dir_str(p)
        if not folder:
            self.event_.emit({"type": "event", "name": "toast", "level": "error", "message": "Invalid folder"})
            return

        self._explorer._set_current_folder(folder)

        with contextlib.suppress(Exception):
            self._settings_mgr.set("last_open_dir", folder)
            parent_dir = abs_dir_str(str(Path(folder).parent))
            self._settings_mgr.set("last_parent_dir", parent_dir)

        if folder != p:
            self._pending_select_path = p
        else:
            self._pending_select_path = None

        self._engine.open_folder(folder)

    def _cmd_set_fast_view(self, enabled: bool) -> None:
        self._settings._set_fast_view_enabled(enabled)
        with contextlib.suppress(Exception):
            self._settings_mgr.set("fast_view_enabled", enabled)

        if enabled:
            self._engine.set_decoding_strategy(self._engine.get_fast_strategy())
        else:
            self._engine.set_decoding_strategy(self._engine.get_full_strategy())

        self._cmd_refresh_current_image()

    def _cmd_set_background_color(self, payload: object | None) -> None:
        color_obj = _get_payload_value(payload, "color", default=payload)
        if color_obj is None:
            return
        c = color_obj.name() if isinstance(color_obj, QColor) else str(color_obj)

        self._settings._set_background_color(c)
        with contextlib.suppress(Exception):
            self._settings_mgr.set("background_color", c)

    def _cmd_set_thumbnail_width(self, width: int) -> None:
        self._settings._set_thumbnail_width(width)
        with contextlib.suppress(Exception):
            self._settings_mgr.set("thumbnail_width", int(self._settings._get_thumbnail_width()))

    def _cmd_copy_files(self, paths: list[str]) -> None:
        if not paths:
            return
        copy_files_to_clipboard(paths)
        self._clipboard_paths = list(paths)
        self._clipboard_mode = "copy"
        self._sync_clipboard_state()

    def _cmd_cut_files(self, paths: list[str]) -> None:
        if not paths:
            return
        cut_files_to_clipboard(paths)
        self._clipboard_paths = list(paths)
        self._clipboard_mode = "cut"
        self._sync_clipboard_state()

    def _cmd_paste_files(self) -> None:
        folder = self._explorer._get_current_folder()
        if not folder:
            return

        clipboard_paths = self._clipboard_paths
        mode = self._clipboard_mode or "copy"

        if not clipboard_paths:
            external_paths = get_files_from_clipboard()
            if external_paths:
                clipboard_paths = external_paths
                mode = "copy"
            else:
                return

        success_count, failed = paste_files(folder, clipboard_paths, mode)
        _logger.debug("pasteFiles: %d success, %d failed, mode=%s", success_count, len(failed), mode)

        if mode == "cut" and success_count > 0:
            self._clipboard_paths = []
            self._clipboard_mode = None
            self._sync_clipboard_state()

        with contextlib.suppress(Exception):
            self._engine.open_folder(folder)

    def _cmd_rename_file(self, path: str, new_name: str) -> None:
        p = str(path)
        if p.startswith("file:"):
            url = QUrl(p)
            if url.isLocalFile():
                p = url.toLocalFile()

        if not p or not new_name:
            return

        try:
            new_path = rename_file(p, str(new_name))
        except Exception as e:
            self.event_.emit({"type": "event", "name": "toast", "level": "error", "message": f"Rename failed: {e}"})
            return

        self._pending_select_path = new_path
        folder = self._explorer._get_current_folder()
        if folder:
            with contextlib.suppress(Exception):
                self._engine.open_folder(folder)

    def _cmd_delete_files(self, paths: list[str]) -> None:
        if not paths:
            return

        with contextlib.suppress(Exception):
            delete_files_to_recycle_bin(paths)

        folder = self._explorer._get_current_folder()
        if folder:
            with contextlib.suppress(Exception):
                self._engine.open_folder(folder)

    def _cmd_reveal_in_explorer(self, path: str) -> None:
        p = str(path)
        if p.startswith("file:"):
            url = QUrl(p)
            if url.isLocalFile():
                p = url.toLocalFile()
        if not p:
            return
        with contextlib.suppress(Exception):
            folder = str(Path(p).parent)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _cmd_copy_text(self, text: str) -> None:
        if not text:
            return
        with contextlib.suppress(Exception):
            QGuiApplication.clipboard().setText(str(text))

    def _cmd_refresh_current_folder(self) -> None:
        folder = self._explorer._get_current_folder()
        if not folder:
            return
        self._engine.open_folder(folder)

    def _cmd_refresh_current_image(self) -> None:
        path = self._viewer._get_current_path()
        if not path:
            return

        with contextlib.suppress(Exception):
            self._engine.remove_from_cache(path)

        self._generation += 1
        self._viewer._set_image_url("")

        with contextlib.suppress(Exception):
            self._request_preview(path, 2048)

        with contextlib.suppress(Exception):
            self._update_status_overlay()

    def _cmd_start_webp_convert(self, payload: object | None) -> None:
        if self._tasks._get_webp_running():
            return

        raw = _get_payload_value(
            payload,
            "folder",
            default=_get_payload_value(payload, "folder_or_url", default=payload),
        )
        p = str(raw or "")
        if p.startswith("file:"):
            url = QUrl(p)
            if url.isLocalFile():
                p = url.toLocalFile()

        folder = abs_dir_str(p)
        if not folder:
            self.taskEvent.emit({"type": "task", "name": "webpConvert", "state": "error", "message": "Invalid folder"})
            return

        should_resize = bool(_get_payload_value(payload, "shouldResize", default=True))
        target_short = int(_get_payload_value(payload, "targetShort", default=2160))
        quality = int(_get_payload_value(payload, "quality", default=90))
        delete_originals = bool(_get_payload_value(payload, "deleteOriginals", default=True))

        self._webp_completed = 0
        self._webp_total = 0
        self._tasks._set_webp_percent(0)
        self._tasks._set_webp_running(True)
        self.taskEvent.emit({"type": "task", "name": "webpConvert", "state": "started", "folder": folder})

        try:
            self._webp_controller.start(
                Path(folder),
                bool(should_resize),
                int(target_short),
                int(quality),
                bool(delete_originals),
            )
        except Exception as e:
            self._tasks._set_webp_running(False)
            self.taskEvent.emit({"type": "task", "name": "webpConvert", "state": "error", "message": str(e)})

    def _cmd_cancel_webp_convert(self) -> None:
        if not self._tasks._get_webp_running():
            return
        with contextlib.suppress(Exception):
            self._webp_controller.cancel()

    # ---- webp signals -> taskEvent ----
    def _on_webp_progress(self, completed: int, total: int) -> None:
        self._webp_completed = int(completed)
        self._webp_total = int(total)
        percent = int((self._webp_completed * 100) / self._webp_total) if self._webp_total > 0 else 0
        self._tasks._set_webp_percent(percent)
        self.taskEvent.emit(
            {
                "type": "task",
                "name": "webpConvert",
                "state": "progress",
                "completed": self._webp_completed,
                "total": self._webp_total,
                "percent": percent,
            }
        )

    def _on_webp_log(self, line: str) -> None:
        self.taskEvent.emit({"type": "task", "name": "webpConvert", "state": "log", "message": str(line)})

    def _on_webp_finished(self, converted: int, total: int) -> None:
        self._tasks._set_webp_percent(100)
        self._tasks._set_webp_running(False)
        self.taskEvent.emit(
            {
                "type": "task",
                "name": "webpConvert",
                "state": "finished",
                "converted": int(converted),
                "total": int(total),
            }
        )

    def _on_webp_canceled(self) -> None:
        self._tasks._set_webp_running(False)
        self.taskEvent.emit({"type": "task", "name": "webpConvert", "state": "canceled"})

    def _on_webp_error(self, msg: str) -> None:
        self._tasks._set_webp_running(False)
        self.taskEvent.emit({"type": "task", "name": "webpConvert", "state": "error", "message": str(msg)})

    # ---- internal state transitions ----
    def _set_current_index(self, idx: int) -> None:
        files = self._explorer._get_image_files()
        new_idx = int(idx)
        new_idx = -1 if not files else max(0, min(new_idx, len(files) - 1))

        self._explorer._set_current_index(new_idx)

        if 0 <= new_idx < len(files):
            self._set_current_path(files[new_idx])
        else:
            self._set_current_path("")

    def _set_current_path(self, path: str) -> None:
        p = str(path)
        if p == self._viewer._get_current_path():
            return

        self._viewer._set_current_path(p)

        # Opening a new image resets rotation.
        self._viewer._set_rotation(0.0)

        self._generation += 1
        self._viewer._set_image_url("")

        if not p:
            self._decoded_w = None
            self._decoded_h = None
            self._viewer._set_status_overlay_text("")
            return

        self._update_status_overlay()

        pix = None
        with contextlib.suppress(Exception):
            pix = self._engine.get_cached_pixmap(p)
        if isinstance(pix, QPixmap) and not pix.isNull():
            self._viewer._set_image_url(f"image://engine/{self._generation}/{p}")
            return

        self._request_preview(p, 2048)

    def _request_preview(self, path: str, size: int) -> None:
        if not path:
            return
        s = int(size)
        target = (s, s) if self._settings._get_fast_view_enabled() else None
        self._engine.request_decode(str(path), target)

    def _update_status_overlay(self) -> None:
        path = self._viewer._get_current_path()
        if not path:
            self._viewer._set_status_overlay_text("")
            return

        parts: list[str] = []
        strategy = "fast view" if self._settings._get_fast_view_enabled() else "original"
        parts.append(f"[{strategy}]")

        file_res = None
        with contextlib.suppress(Exception):
            file_res = self._engine.get_resolution(path)

        if file_res and file_res[0] and file_res[1]:
            parts.append(f"File {file_res[0]}x{file_res[1]}")

        out_res: tuple[int, int] | None = None
        if self._settings._get_fast_view_enabled() and self._decoded_w and self._decoded_h:
            out_res = (self._decoded_w, self._decoded_h)
        if out_res is None and file_res:
            out_res = file_res
        if out_res is None and self._decoded_w and self._decoded_h:
            out_res = (self._decoded_w, self._decoded_h)

        if out_res and out_res[0] and out_res[1]:
            parts.append(f"Output {out_res[0]}x{out_res[1]}")

        scale = None
        if file_res and out_res and file_res[0] > 0 and file_res[1] > 0:
            scale = out_res[0] / file_res[0]
        if scale is not None:
            parts.append(f"@ {scale:.2f}x")

        self._viewer._set_status_overlay_text(" ".join(parts))

    def _sync_clipboard_state(self) -> None:
        has = bool(self._clipboard_paths)
        if not has and self._clipboard_cached_external_paths:
            has = len(self._clipboard_cached_external_paths) > 0
        self._explorer._set_clipboard_has_files(has)

    def _on_clipboard_changed(self) -> None:
        try:
            external = get_files_from_clipboard()
        except Exception:
            external = None
        self._clipboard_cached_external_paths = list(external) if external else []
        self._sync_clipboard_state()

    # ---- engine slots ----
    @Slot(list)
    def _on_engine_file_list_updated(self, files: list[str]) -> None:
        norm = [abs_path_str(f) for f in files]
        self._explorer._set_image_files(norm)

        # Apply pending selection.
        if self._pending_select_path:
            target = abs_path_str(str(self._pending_select_path))
            self._pending_select_path = None
            if target in norm:
                self._set_current_index(norm.index(target))
                return

        if norm and self._explorer._get_current_index() < 0:
            self._set_current_index(0)
        if not norm:
            self._set_current_index(-1)

    @Slot(str, list)
    def _on_engine_explorer_entries_changed(self, folder_path: str, entries: list[dict]) -> None:
        self._image_model.set_entries(entries)
        if folder_path:
            self._explorer._set_current_folder(str(folder_path))

    @Slot(list)
    def _on_engine_explorer_thumb_rows(self, rows: list[dict]) -> None:
        changed_rows: list[dict] = []
        for row in rows:
            with contextlib.suppress(Exception):
                path = str(row.get("path") or "")
                if not path:
                    continue
                key = db_key(path)
                thumb = row.get("thumbnail")
                if thumb is not None:
                    self._thumb_bytes_by_key[key] = bytes(thumb)
                changed_rows.append({**row, "path": path})

        if changed_rows:
            self._image_model.update_thumb_rows(changed_rows)

    @Slot(dict)
    def _on_engine_explorer_thumb_generated(self, payload: dict) -> None:
        self._on_engine_explorer_thumb_rows([payload])

    @Slot(str, QPixmap, object)
    def _on_engine_image_ready(self, path: str, pixmap: QPixmap, error: object | None) -> None:
        if error is not None:
            return
        if not path or str(path) != self._viewer._get_current_path():
            return

        with contextlib.suppress(Exception):
            self._decoded_w = int(pixmap.width())
            self._decoded_h = int(pixmap.height())
            self._update_status_overlay()

        self._generation += 1
        self._viewer._set_image_url(f"image://engine/{self._generation}/{path}")

        if self._crop._get_active() and str(path) == self._crop._get_current_path():
            self._crop._set_image_url(self._viewer._get_image_url())


def _get_payload_value(payload: object | None, key: str, *, default: Any) -> Any:
    """Extract a value from a QML payload.

    Supports:
    - dict-like payloads (Python dict)
    - None
    - otherwise returns default

    We intentionally keep schema small and explicit.
    """

    if payload is None:
        return default

    # QML often passes a JS object which arrives as QJSValue/QVariant.
    # Convert to a Python mapping when possible.
    if payload.__class__.__name__ == "QJSValue" and hasattr(payload, "toVariant"):
        with contextlib.suppress(Exception):
            payload = payload.toVariant()  # type: ignore[assignment, attr-defined]

    if isinstance(payload, dict):
        return payload.get(key, default)

    return default
