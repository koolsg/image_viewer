from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtWidgets import QApplication, QMessageBox

from image_viewer.file_operations import (
    rename_file,
    copy_files_to_clipboard,
    cut_files_to_clipboard,
    get_files_from_clipboard,
    paste_files,
    delete_files_to_recycle_bin,
)
from image_viewer.image_engine.engine import ImageEngine
from image_viewer.logger import get_logger, setup_logger
from image_viewer.path_utils import abs_dir_str, abs_path_str, db_key
from image_viewer.qml_models import QmlImageGridModel
from image_viewer.settings_manager import SettingsManager
from image_viewer.styles import apply_theme
from image_viewer.webp_converter import ConvertController

_logger = get_logger("main")
_BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
_GEN_PATH_SPLIT_MAX = 1
_GEN_PATH_PARTS = 2


def _apply_cli_logging_options(argv: list[str]) -> list[str]:
    """Parse our CLI options before Qt touches argv.

    We strip supported options from argv so Qt doesn't choke on unknown flags.
    """
    try:
        import argparse  # noqa: PLC0415

        parser = argparse.ArgumentParser(description="Image Viewer", add_help=False)
        parser.add_argument("--log-level")
        parser.add_argument("--log-cats")
        args, remaining = parser.parse_known_args(argv)

        if args.log_level:
            os.environ["IMAGE_VIEWER_LOG_LEVEL"] = str(args.log_level)
        if args.log_cats:
            os.environ["IMAGE_VIEWER_LOG_CATS"] = str(args.log_cats)

        return [argv[0], *remaining]
    except Exception:
        return argv


@contextlib.contextmanager
def _suppress_expected(*exceptions: type[BaseException]):
    """Context manager that suppresses expected exception types and logs unexpected ones.

    Usage: with _suppress_expected(TypeError, ValueError, OSError):
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
        # ID format: "{generation}/{path}". Generation is only for cache-busting.
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

    def __init__(self, thumb_bytes_by_key: dict[str, bytes]) -> None:
        super().__init__(QQuickImageProvider.ImageType.Pixmap)
        self._thumb_bytes_by_key = thumb_bytes_by_key

    def requestPixmap(self, id: str, size: Any, requestedSize: Any) -> QPixmap:
        parts = str(id).split("/", _GEN_PATH_SPLIT_MAX)
        key = parts[1] if len(parts) == _GEN_PATH_PARTS and parts[0].isdigit() else str(id)

        # QML may percent-encode the id part of an image:// URL.
        data = self._thumb_bytes_by_key.get(key)
        if not data:
            with _suppress_expected(TypeError, ValueError, OSError):
                key_dec = QUrl.fromPercentEncoding(str(key).encode("utf-8"))
                data = self._thumb_bytes_by_key.get(str(key_dec))
        if not data:
            # Returning a null pixmap causes QML to spam:
            #   QQuickImage: Failed to get image from provider
            # Use a tiny transparent placeholder instead.
            pix = QPixmap(1, 1)
            pix.fill(Qt.GlobalColor.transparent)
            return pix

        pix = QPixmap()
        if not pix.loadFromData(data):
            placeholder = QPixmap(1, 1)
            placeholder.fill(Qt.GlobalColor.transparent)
            return placeholder

        return pix


class Main(QObject):
    """Single backend object exposed to QML.

    Final architecture target:
      QML -> Main(QObject) -> ImageEngine/decoder/db

    No QWidget/QMainWindow involvement.
    """

    currentFolderChanged = Signal(str)
    imageFilesChanged = Signal()
    currentIndexChanged = Signal(int)
    viewModeChanged = Signal(bool)
    currentPathChanged = Signal(str)
    imageUrlChanged = Signal(str)
    zoomChanged = Signal(float)
    fitModeChanged = Signal(bool)
    rotationChanged = Signal(float)
    pressZoomMultiplierChanged = Signal(float)
    imageModelChanged = Signal()
    clipboardChanged = Signal()
    fastViewEnabledChanged = Signal(bool)
    backgroundColorChanged = Signal(str)
    statusOverlayChanged = Signal(str)

    webpConvertRunningChanged = Signal(bool)
    webpConvertProgressChanged = Signal()
    webpConvertLog = Signal(str)
    webpConvertFinished = Signal(int, int)
    webpConvertCanceled = Signal()
    webpConvertError = Signal(str)

    # UI-only thumbnail width (pixels) persisted in settings; does NOT trigger engine regen
    thumbnailWidthChanged = Signal(int)

    def __init__(
        self,
        engine: ImageEngine | None = None,
        settings: SettingsManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine or ImageEngine()
        self.settings = settings or SettingsManager(abs_path_str(_BASE_DIR / "settings.json"))

        self._thumb_bytes_by_key: dict[str, bytes] = {}
        self.engine_image_provider = EngineImageProvider(self.engine)
        self.thumb_provider = ThumbImageProvider(self._thumb_bytes_by_key)

        self._image_model = QmlImageGridModel(self)

        self._current_folder: str = ""
        self._image_files: list[str] = []
        self._current_index: int = -1
        self._view_mode: bool = False

        self._current_path: str = ""
        self._image_url: str = ""
        self._generation: int = 0

        self._zoom: float = 1.0
        self._fit_mode: bool = True
        self._rotation: float = 0.0

        self._pending_select_path: str | None = None

        # Status overlay state (legacy parity: strategy + file/output res + scale).
        self._decoded_w: int | None = None
        self._decoded_h: int | None = None
        self._status_overlay_text: str = ""

        # View-related settings (QML menu parity with legacy ui_menus.py).
        self._fast_view_enabled: bool = bool(self.settings.fast_view_enabled)
        self._background_color: str = str(self.settings.get("background_color", "#000000"))
        self._press_zoom_multiplier: float = float(self.settings.get("press_zoom_multiplier", 3.0))

        # UI-only thumbnail width (pixels). Persisted but does NOT trigger engine regen.
        self._thumbnail_width: int = int(self.settings.get("thumbnail_width", 220))

        # WebP conversion controller (QML Tools -> Convert to WebP...)
        self._init_webp_converter()

        # Apply initial decoding strategy.
        self._apply_initial_decoding_strategy()

        # Explorer clipboard state (copy/cut -> paste).
        # QML triggers operations via slots; we keep the clipboard state in Python
        # so we can implement cut semantics (move on paste).
        self._clipboard_paths: list[str] = []
        self._clipboard_mode: str | None = None  # "copy" | "cut"
        # Cached external clipboard file list (populated from system clipboard)
        self._clipboard_cached_external_paths: list[str] | None = None

        # Subscribe to clipboard changes to avoid polling on property reads.
        try:
            cb = QGuiApplication.clipboard()
            cb.dataChanged.connect(self._on_clipboard_changed)
            # Populate initial cache
            self._on_clipboard_changed()
        except Exception:
            # Non-fatal: if clipboard isn't available, we fall back to on-demand checks.
            self._clipboard_cached_external_paths = None

        # ---- Engine -> Main wiring ----
        self._setup_engine_signals()

    def _init_webp_converter(self) -> None:
        self._webp_controller = ConvertController()
        self._webp_running = False
        self._webp_completed = 0
        self._webp_total = 0

        self._webp_controller.progress.connect(self._on_webp_progress)
        self._webp_controller.log.connect(self.webpConvertLog.emit)
        self._webp_controller.finished.connect(self._on_webp_finished)
        self._webp_controller.canceled.connect(self._on_webp_canceled)
        self._webp_controller.error.connect(self._on_webp_error)

    def _apply_initial_decoding_strategy(self) -> None:
        """Apply the initial decoding strategy and fail fast on misconfiguration."""
        try:
            if self._fast_view_enabled:
                self.engine.set_decoding_strategy(self.engine.get_fast_strategy())
            else:
                self.engine.set_decoding_strategy(self.engine.get_full_strategy())
        except AttributeError as e:
            # Fail fast: show an error to the user and exit so misconfiguration is noticed immediately.
            _logger.critical("Failed to set initial decoding strategy: %s", e, exc_info=True)
            try:
                # QApplication already exists when Main is constructed in run(); show modal dialog.
                QMessageBox.critical(None, "Startup Error", f"Failed to initialize decoding strategy:\n{e}")
            except Exception:
                # Fallback to stderr if Qt widgets aren't functional for some reason.
                print(f"Critical: Failed to initialize decoding strategy: {e}", file=sys.stderr, flush=True)
            sys.exit(1)

    def _setup_engine_signals(self) -> None:
        """Connect engine signals to Main slots; fail fast if the engine is missing expected signals."""
        try:
            self.engine.image_ready.connect(self._on_engine_image_ready)
            self.engine.file_list_updated.connect(self._on_engine_file_list_updated)
            self.engine.explorer_entries_changed.connect(self._on_engine_explorer_entries_changed)
            self.engine.explorer_thumb_rows.connect(self._on_engine_explorer_thumb_rows)
            self.engine.explorer_thumb_generated.connect(self._on_engine_explorer_thumb_generated)
        except AttributeError as e:
            # Fail fast: missing engine signals indicates misconfiguration — stop startup.
            _logger.critical("Failed to connect engine signals: %s", e, exc_info=True)
            try:
                QMessageBox.critical(None, "Startup Error", f"Engine initialization failed:\n{e}")
            except Exception:
                print(f"Critical: Failed to connect engine signals: {e}", file=sys.stderr, flush=True)
            sys.exit(1)

    # ---- QML properties ----
    def _get_current_folder(self) -> str:
        return self._current_folder

    currentFolder = Property(str, _get_current_folder, notify=currentFolderChanged)  # type: ignore[arg-type]

    def _get_image_files(self) -> list[str]:
        return list(self._image_files)

    imageFiles = Property(list, _get_image_files, notify=imageFilesChanged)  # type: ignore[arg-type]

    def _get_current_index(self) -> int:
        return int(self._current_index)

    def _set_current_index(self, idx: int) -> None:
        new_idx = int(idx)
        new_idx = -1 if not self._image_files else max(0, min(new_idx, len(self._image_files) - 1))

        if new_idx == self._current_index:
            return

        self._current_index = new_idx
        self.currentIndexChanged.emit(self._current_index)

        if 0 <= self._current_index < len(self._image_files):
            self._set_current_path(self._image_files[self._current_index])
        else:
            self._set_current_path("")

    currentIndex = Property(int, _get_current_index, _set_current_index, notify=currentIndexChanged)  # type: ignore[arg-type]

    def _get_view_mode(self) -> bool:
        return bool(self._view_mode)

    def _set_view_mode(self, val: bool) -> None:
        new_val = bool(val)
        if new_val == self._view_mode:
            return
        self._view_mode = new_val
        self.viewModeChanged.emit(new_val)

    viewMode = Property(bool, _get_view_mode, _set_view_mode, notify=viewModeChanged)  # type: ignore[arg-type]

    def _get_current_path(self) -> str:
        return self._current_path

    currentPath = Property(str, _get_current_path, notify=currentPathChanged)  # type: ignore[arg-type]

    def _get_image_url(self) -> str:
        return self._image_url

    imageUrl = Property(str, _get_image_url, notify=imageUrlChanged)  # type: ignore[arg-type]

    def _get_zoom(self) -> float:
        return float(self._zoom)

    def _set_zoom(self, val: float) -> None:
        new_val = float(val)
        if new_val == self._zoom:
            return
        self._zoom = new_val
        self.zoomChanged.emit(new_val)

    zoom = Property(float, _get_zoom, _set_zoom, notify=zoomChanged)  # type: ignore[arg-type]

    def _get_fit_mode(self) -> bool:
        return bool(self._fit_mode)

    def _set_fit_mode(self, val: bool) -> None:
        new_val = bool(val)
        if new_val == self._fit_mode:
            return
        self._fit_mode = new_val
        self.fitModeChanged.emit(new_val)

    fitMode = Property(bool, _get_fit_mode, _set_fit_mode, notify=fitModeChanged)  # type: ignore[arg-type]

    def _get_rotation(self) -> float:
        return float(self._rotation)

    def _set_rotation(self, val: float) -> None:
        new_val = float(val)
        if new_val == self._rotation:
            return
        self._rotation = new_val
        self.rotationChanged.emit(new_val)

    rotation = Property(float, _get_rotation, _set_rotation, notify=rotationChanged)  # type: ignore[arg-type]

    def _get_press_zoom_multiplier(self) -> float:
        return float(self._press_zoom_multiplier)

    def _set_press_zoom_multiplier(self, val: float) -> None:
        new_val = float(val)
        # Avoid silly values.
        if new_val <= 0:
            new_val = 3.0
        if new_val == self._press_zoom_multiplier:
            return
        self._press_zoom_multiplier = new_val
        self.pressZoomMultiplierChanged.emit(new_val)
        with contextlib.suppress(Exception):
            self.settings.set("press_zoom_multiplier", new_val)

    # ---- Thumbnail UI size (UI-only) ----
    def _get_thumbnail_width(self) -> int:
        return int(self._thumbnail_width)

    def _set_thumbnail_width(self, w: int) -> None:
        new_w = int(max(64, min(1024, int(w))))
        if new_w == self._thumbnail_width:
            return
        self._thumbnail_width = new_w
        with contextlib.suppress(Exception):
            self.settings.set("thumbnail_width", new_w)
        self.thumbnailWidthChanged.emit(new_w)

    thumbnailWidth = Property(int, _get_thumbnail_width, _set_thumbnail_width, notify=thumbnailWidthChanged)  # type: ignore[arg-type]

    pressZoomMultiplier = Property(
        float,
        _get_press_zoom_multiplier,
        _set_press_zoom_multiplier,
        notify=pressZoomMultiplierChanged,  # type: ignore[arg-type]
    )

    def _get_image_model(self) -> QObject:
        return self._image_model

    imageModel = Property(QObject, _get_image_model, notify=imageModelChanged)  # type: ignore[arg-type]

    def _get_clipboard_has_files(self) -> bool:
        if self._clipboard_paths:
            return True
        if self._clipboard_cached_external_paths:
            return len(self._clipboard_cached_external_paths) > 0
        # Fallback to on-demand check if cache isn't available
        external_paths = get_files_from_clipboard()
        return external_paths is not None and len(external_paths) > 0

    clipboardHasFiles = Property(bool, _get_clipboard_has_files, notify=clipboardChanged)  # type: ignore[arg-type]

    def _get_fast_view_enabled(self) -> bool:
        return bool(self._fast_view_enabled)

    def _set_fast_view_enabled(self, val: bool) -> None:
        new_val = bool(val)
        if new_val == self._fast_view_enabled:
            return

        self._fast_view_enabled = new_val
        self.fastViewEnabledChanged.emit(new_val)

        try:
            self.settings.set("fast_view_enabled", new_val)
        except Exception as e:
            _logger.error("Failed to persist fast_view_enabled: %s", e)

        # Switch engine decoding strategy.
        try:
            if new_val:
                self.engine.set_decoding_strategy(self.engine.get_fast_strategy())
            else:
                self.engine.set_decoding_strategy(self.engine.get_full_strategy())
        except AttributeError as e:
            _logger.error("Failed to switch decoding strategy: %s", e)

        # Force refresh of current image so the visual result matches the strategy.
        try:
            self.refreshCurrentImage()
        except Exception as e:
            _logger.error("Failed to refresh current image: %s", e)

    fastViewEnabled = Property(bool, _get_fast_view_enabled, _set_fast_view_enabled, notify=fastViewEnabledChanged)  # type: ignore[arg-type]

    def _get_background_color(self) -> str:
        return str(self._background_color)

    def _set_background_color(self, val: str) -> None:
        new_val = str(val).strip()
        if not new_val:
            return
        if new_val == self._background_color:
            return

        self._background_color = new_val
        self.backgroundColorChanged.emit(new_val)
        with contextlib.suppress(Exception):
            self.settings.set("background_color", new_val)

    backgroundColor = Property(str, _get_background_color, _set_background_color, notify=backgroundColorChanged)  # type: ignore[arg-type]

    def _get_status_overlay_text(self) -> str:
        return str(self._status_overlay_text)

    statusOverlayText = Property(str, _get_status_overlay_text, notify=statusOverlayChanged)  # type: ignore[arg-type]

    def _get_webp_running(self) -> bool:
        return bool(self._webp_running)

    webpConvertRunning = Property(bool, _get_webp_running, notify=webpConvertRunningChanged)  # type: ignore[arg-type]

    def _get_webp_percent(self) -> int:
        if self._webp_total <= 0:
            return 0
        return int((self._webp_completed * 100) / self._webp_total)

    webpConvertPercent = Property(int, _get_webp_percent, notify=webpConvertProgressChanged)  # type: ignore[arg-type]

    def _set_webp_running(self, running: bool) -> None:
        new_val = bool(running)
        if new_val == self._webp_running:
            return
        self._webp_running = new_val
        self.webpConvertRunningChanged.emit(new_val)

    def _set_webp_progress(self, completed: int, total: int) -> None:
        self._webp_completed = int(completed)
        self._webp_total = int(total)
        self.webpConvertProgressChanged.emit()

    # ---- QML slots ----
    @Slot(str)
    def openFolder(self, path_or_url: str) -> None:
        """Open a folder (or file URL string) provided by QML FolderDialog."""
        p = str(path_or_url)
        if p.startswith("file:"):
            url = QUrl(p)
            if url.isLocalFile():
                p = url.toLocalFile()

        folder = abs_dir_str(p)
        self._current_folder = folder
        self.currentFolderChanged.emit(folder)

        # Persist immediately.
        # - last_open_dir: the folder we actually opened
        # - last_parent_dir: used as the starting location for the next FolderDialog
        with contextlib.suppress(Exception):
            self.settings.set("last_open_dir", folder)
            parent_dir = abs_dir_str(str(Path(folder).parent))
            self.settings.set("last_parent_dir", parent_dir)

        # If a file was passed, remember and select once list arrives.
        if folder != p:
            self._pending_select_path = p
        else:
            self._pending_select_path = None

        self.engine.open_folder(folder)

    @Slot()
    def closeView(self) -> None:
        _logger.debug("closeView requested (currentPath=%s)", getattr(self, "_current_path", None))
        self._set_view_mode(False)

    @Slot(str)
    def qmlDebug(self, message: str) -> None:
        """Debug hook from QML.

        Prints directly to stderr (flush) so we can trace input routing even when
        the Python logger is filtered or when we need visibility very early.
        QML-origin messages are prefixed with an emoji marker so they're visually
        distinctive in terminal output and log files.
        """
        msg = str(message)
        # Integrate QML-originated diagnostics with the Python logging pipeline.
        _logger.debug("[QML] %s", msg)
        # Also print a colored line to stderr for immediate visibility in terminal
        try:
            print(f"\033[95m[QML] {msg}\033[0m", file=sys.stderr, flush=True)
        except Exception:
            # Fallback to plain print if terminal doesn't accept ANSI sequences
            print(f"[QML] {msg}", file=sys.stderr, flush=True)

    @Slot()
    def nextImage(self) -> None:
        self._set_current_index(self._current_index + 1)

    @Slot()
    def prevImage(self) -> None:
        self._set_current_index(self._current_index - 1)

    @Slot()
    def firstImage(self) -> None:
        self._set_current_index(0)

    @Slot()
    def lastImage(self) -> None:
        if self._image_files:
            self._set_current_index(len(self._image_files) - 1)

    @Slot(float)
    def rotateBy(self, degrees: float) -> None:
        """Rotate the current image (viewer-only)."""
        self._set_rotation(self._rotation + float(degrees))

    @Slot()
    def resetRotation(self) -> None:
        self._set_rotation(0.0)

    @Slot(str, bool, int, int, bool)
    def startWebpConvert(
        self,
        folder_or_url: str,
        shouldResize: bool,
        targetShort: int,
        quality: int,
        deleteOriginals: bool,
    ) -> None:
        """Start batch WebP conversion.

        QML passes a FolderDialog URL string; we normalize to a local folder path.
        """
        if self._webp_running:
            return

        p = str(folder_or_url)
        if p.startswith("file:"):
            url = QUrl(p)
            if url.isLocalFile():
                p = url.toLocalFile()

        folder = abs_dir_str(p)
        if not folder:
            self.webpConvertError.emit("Invalid folder")
            return

        self._set_webp_progress(0, 0)
        self._set_webp_running(True)

        try:
            self._webp_controller.start(
                Path(folder),
                bool(shouldResize),
                int(targetShort),
                int(quality),
                bool(deleteOriginals),
            )
        except Exception as e:
            self._set_webp_running(False)
            self.webpConvertError.emit(str(e))

    @Slot()
    def cancelWebpConvert(self) -> None:
        if not self._webp_running:
            return
        with contextlib.suppress(Exception):
            self._webp_controller.cancel()

    def _on_webp_progress(self, completed: int, total: int) -> None:
        self._set_webp_progress(completed, total)

    def _on_webp_finished(self, converted: int, total: int) -> None:
        self._set_webp_progress(total, total)
        self._set_webp_running(False)
        self.webpConvertFinished.emit(int(converted), int(total))

    def _on_webp_canceled(self) -> None:
        self._set_webp_running(False)
        self.webpConvertCanceled.emit()

    def _on_webp_error(self, msg: str) -> None:
        self._set_webp_running(False)
        self.webpConvertError.emit(str(msg))

    @Slot(str)
    def copyText(self, text: str) -> None:
        with contextlib.suppress(Exception):
            QGuiApplication.clipboard().setText(str(text))

    @Slot(object)
    def setBackgroundColor(self, payload: object) -> None:
        """Set persisted background color.

        QML ColorDialog passes a QColor; QML code may also pass a hex string.
        """
        if payload is None:
            return

        if isinstance(payload, QColor):
            self._set_background_color(payload.name())
            return

        self._set_background_color(str(payload))

    @Slot(object)
    def copyFiles(self, payload: object) -> None:
        """Copy one or more file paths.

        Accepts QML arrays or single strings. Handles QVariantList or Python lists.
        """
        _logger.debug("copyFiles called with payload type=%s payload=%r", type(payload), payload)
        paths: list[str] = _coerce_paths(payload)
        if not paths:
            return
        copy_files_to_clipboard(paths)
        self._clipboard_paths = list(paths)
        self._clipboard_mode = "copy"
        self.clipboardChanged.emit()

    @Slot(object)
    def cutFiles(self, payload: object) -> None:
        """Cut one or more file paths.

        Accepts QML arrays or single strings.
        """
        _logger.debug("cutFiles called with payload type=%s payload=%r", type(payload), payload)
        paths: list[str] = _coerce_paths(payload)
        if not paths:
            return

        # On Windows, setting clipboard for cut/move requires the shell to see the drop-effect
        # We still use the same helper which sets URLs to the clipboard; Windows will interpret
        # these as files and the subsequent paste handler will move them if mode == 'cut'.
        cut_files_to_clipboard(paths)
        self._clipboard_paths = list(paths)
        self._clipboard_mode = "cut"
        self.clipboardChanged.emit()

    @Slot()
    def pasteFiles(self) -> None:
        """Paste clipboard files into the currently opened folder."""
        if not self._current_folder:
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

        success_count, failed = paste_files(self._current_folder, clipboard_paths, mode)
        _logger.debug("pasteFiles: %d success, %d failed, mode=%s", success_count, len(failed), mode)

        if mode == "cut" and success_count > 0:
            self._clipboard_paths = []
            self._clipboard_mode = None
            self.clipboardChanged.emit()

        with contextlib.suppress(Exception):
            self.engine.open_folder(self._current_folder)

    @Slot(str, str)
    def renameFile(self, path: str, newName: str) -> None:
        """Rename a file in place (same directory) and refresh current folder."""
        p = str(path)
        if p.startswith("file:"):
            url = QUrl(p)
            if url.isLocalFile():
                p = url.toLocalFile()

        try:
            new_path = rename_file(p, str(newName))
        except Exception as e:
            _logger.error("renameFile failed: %s", e)
            return

        # Keep selection on renamed file when possible.
        self._pending_select_path = new_path
        with contextlib.suppress(Exception):
            if self._current_folder:
                self.engine.open_folder(self._current_folder)

    @Slot(str)
    @Slot(object)
    def performDelete(self, payload: object) -> None:
        """Perform deletion requested by QML dialog.

        `payload` may be a single path string or a list of path strings.
        This calls into the explorer helper to move files to Recycle Bin and
        then refreshes the current folder in the engine.

        For diagnostics we log the Python-level type and a short preview of the
        payload so we can inspect problematic QML objects that fail conversion.
        """
        try:
            # Debug: record the incoming payload type and a compact repr.
            try:
                payload_type = payload.__class__.__name__
            except Exception:
                payload_type = str(type(payload))
            _logger.debug("performDelete called with payload type=%s payload=%r", payload_type, payload)

            # If it's a QJSValue, attempt to extract an array preview for logging.
            try:
                if payload.__class__.__name__ == "QJSValue":
                    _logger.debug("performDelete: QJSValue.isArray=%s", getattr(payload, "isArray", lambda: False)())
            except Exception:
                pass

            paths: list[str] = _coerce_paths(payload)

            if not paths:
                return

            # Let the explorer-level helper perform deletion semantics
            with contextlib.suppress(Exception):
                success_count, failed = delete_files_to_recycle_bin(paths)
                _logger.debug("performDelete: %d deleted, %d failed", success_count, len(failed))

            # Refresh current folder listing so UI updates (best-effort)
            try:
                cur = getattr(self, "_current_folder", None)
                if cur:
                    self.engine.open_folder(cur)
            except Exception:
                pass
        except Exception as e:
            _logger.error("performDelete failed: %s", e)

    @Slot(str)
    def revealInExplorer(self, path: str) -> None:
        p = str(path)
        if p.startswith("file:"):
            url = QUrl(p)
            if url.isLocalFile():
                p = url.toLocalFile()

        # Best-effort: open the containing folder.
        with contextlib.suppress(Exception):
            folder = str(Path(p).parent)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    @Slot(str, int)
    def requestPreview(self, path: str, size: int) -> None:
        if not path:
            return
        s = int(size)

        # Mirror the legacy strategies:
        # - Fast view: decode near-viewport (bounded by `size`)
        # - Original: decode full-resolution (target_size=None)
        target = (s, s) if self._fast_view_enabled else None
        self.engine.request_decode(str(path), target)

    @Slot()
    def refreshCurrentFolder(self) -> None:
        """Refresh the currently opened folder (Explorer)."""
        if not self._current_folder:
            return
        self.engine.open_folder(self._current_folder)

    @Slot()
    def refreshCurrentImage(self) -> None:
        """Force a re-decode of the current image with current strategy settings."""
        if not self._current_path:
            return

        with contextlib.suppress(Exception):
            self.engine.remove_from_cache(self._current_path)

        # Bump generation so QML refreshes the provider URL even if the path is unchanged.
        self._generation += 1
        self._image_url = ""
        self.imageUrlChanged.emit("")

        # Request decode again.
        with contextlib.suppress(Exception):
            self.requestPreview(self._current_path, 2048)

        # Ensure overlay text updates even before decode finishes.
        with contextlib.suppress(Exception):
            self._update_status_overlay()

    # ---- internal helpers ----
    def _set_current_path(self, path: str) -> None:
        if str(path) == self._current_path:
            return

        self._current_path = str(path)
        self.currentPathChanged.emit(self._current_path)

        # Legacy parity: opening a new image resets rotation.
        self._set_rotation(0.0)

        self._generation += 1
        self._image_url = ""
        self.imageUrlChanged.emit("")

        if not self._current_path:
            self._decoded_w = None
            self._decoded_h = None
            self._status_overlay_text = ""
            self.statusOverlayChanged.emit(self._status_overlay_text)
            return

        # Update overlay immediately (file resolution/strategy may already be known).
        with contextlib.suppress(Exception):
            self._update_status_overlay()

        # If cached, expose immediately.
        pix = None
        with contextlib.suppress(Exception):
            pix = self.engine.get_cached_pixmap(self._current_path)
        if isinstance(pix, QPixmap) and not pix.isNull():
            self._image_url = f"image://engine/{self._generation}/{self._current_path}"
            self.imageUrlChanged.emit(self._image_url)
            return

        # Otherwise request a preview decode.
        with contextlib.suppress(Exception):
            self.requestPreview(self._current_path, 2048)

    # ---- engine slots ----
    @Slot(list)
    def _on_engine_file_list_updated(self, files: list[str]) -> None:
        self._image_files = list(files)
        self.imageFilesChanged.emit()

        # Apply pending selection
        if self._pending_select_path:
            target = str(self._pending_select_path)
            self._pending_select_path = None
            with contextlib.suppress(Exception):
                target = abs_path_str(target)
            if target in self._image_files:
                self._set_current_index(self._image_files.index(target))
                return

        # Default selection
        if self._image_files and self._current_index < 0:
            self._set_current_index(0)
        if not self._image_files:
            self._set_current_index(-1)

    @Slot(str, list)
    def _on_engine_explorer_entries_changed(self, folder_path: str, entries: list[dict]) -> None:
        self._image_model.set_entries(entries)
        self.imageModelChanged.emit()
        if folder_path:
            self._current_folder = str(folder_path)
            self.currentFolderChanged.emit(self._current_folder)

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
        if not path or str(path) != self._current_path:
            return

        # Track decoded output resolution for overlay.
        with contextlib.suppress(Exception):
            self._decoded_w = int(pixmap.width())
            self._decoded_h = int(pixmap.height())
            self._update_status_overlay()

        self._generation += 1
        self._image_url = f"image://engine/{self._generation}/{path}"
        self.imageUrlChanged.emit(self._image_url)

    def _update_status_overlay(self) -> None:
        """Build overlay text equivalent to legacy StatusOverlayBuilder."""
        if not self._current_path:
            new_text = ""
        else:
            parts: list[str] = []

            # Strategy name: mirror legacy decoding_strategy.get_name().
            strategy = "fast view" if self._fast_view_enabled else "original"
            parts.append(f"[{strategy}]")

            file_res = None
            with contextlib.suppress(Exception):
                file_res = self.engine.get_resolution(self._current_path)

            if file_res and file_res[0] and file_res[1]:
                parts.append(f"File {file_res[0]}x{file_res[1]}")

            # Output resolution rules:
            # - Fast view: prefer decoded size if available
            # - Original: output == file resolution when known
            out_res: tuple[int, int] | None = None
            if self._fast_view_enabled and self._decoded_w and self._decoded_h:
                out_res = (self._decoded_w, self._decoded_h)
            if out_res is None and file_res:
                out_res = file_res
            if out_res is None and self._decoded_w and self._decoded_h:
                out_res = (self._decoded_w, self._decoded_h)

            if out_res and out_res[0] and out_res[1]:
                parts.append(f"Output {out_res[0]}x{out_res[1]}")

            scale = None
            if file_res and out_res and file_res[0] > 0 and file_res[1] > 0:
                # Scale relative to original file pixels (legacy displayed '@ {scale:.2f}x').
                scale = out_res[0] / file_res[0]

            if scale is not None:
                parts.append(f"@ {scale:.2f}x")

            new_text = " ".join(parts)

        if new_text == self._status_overlay_text:
            return

        self._status_overlay_text = new_text
        self.statusOverlayChanged.emit(new_text)

    def _on_clipboard_changed(self) -> None:
        """Update cached external clipboard file list and emit change only when it differs."""
        try:
            external = get_files_from_clipboard()
        except Exception:
            external = None

        # Normalize to list or empty list.
        new_list: list[str] = list(external) if external else []

        if self._clipboard_cached_external_paths is None:
            changed = bool(new_list)
        else:
            changed = new_list != self._clipboard_cached_external_paths

        if changed:
            self._clipboard_cached_external_paths = new_list
            with contextlib.suppress(Exception):
                self.clipboardChanged.emit()
        else:
            # Update cache even if not changed (first-time populate)
            self._clipboard_cached_external_paths = new_list


def _handle_qjs_value(payload: object) -> list[str] | None:
    """Try to handle QJSValue from QML."""
    try:
        if payload.__class__.__name__ != "QJSValue":
            return None
        js_value = payload  # type: ignore[assignment]
        if hasattr(js_value, "isArray") and js_value.isArray():  # type: ignore[attr-defined]
            result = []
            length_prop = js_value.property("length")  # type: ignore[attr-defined]
            length = length_prop.toInt()  # type: ignore[attr-defined]
            for i in range(length):
                elem = js_value.property(i)  # type: ignore[attr-defined]
                if elem.isString():  # type: ignore[attr-defined]
                    result.append(elem.toString())  # type: ignore[attr-defined]
                elif not elem.isNull() and not elem.isUndefined():  # type: ignore[attr-defined]
                    result.append(str(elem.toVariant()))  # type: ignore[attr-defined]
            _logger.debug("_coerce_paths: handled QJSValue array with %d items", len(result))
            return result
        if js_value.isString():  # type: ignore[attr-defined]
            s = js_value.toString()  # type: ignore[attr-defined]
            _logger.debug("_coerce_paths: handled QJSValue string: %r", s)
            return [s]
        variant = js_value.toVariant()  # type: ignore[attr-defined]
        return [str(variant)]
    except Exception as e:
        _logger.debug("_coerce_paths: QJSValue handling failed: %s", e)
        return None


def _coerce_paths(payload: object) -> list[str]:  # noqa: PLR0911
    """Coerce a QML-provided payload into a list of filesystem paths.

    Accepts QJSValue arrays (most common), native Python lists, QVariantList,
    single strings, and JSON-encoded lists.
    """
    result: list[str] | None = None
    if payload is None:
        return []

    # Try QJSValue first (most common case from QML)
    result = _handle_qjs_value(payload)
    if result is not None:
        return result

    # Native Python collections
    if isinstance(payload, (list, tuple, set)):
        result = [str(p) for p in payload if p is not None]
        _logger.debug("_coerce_paths: handled as list/tuple/set with %d items", len(result))
        return result

    # QVariantList
    if hasattr(payload, "toList"):
        try:
            lst = payload.toList()  # type: ignore[attr-defined]
            result = [str(p) for p in lst if p is not None]
            _logger.debug("_coerce_paths: handled as QVariantList with %d items", len(result))
            return result
        except Exception as e:
            _logger.debug("_coerce_paths: toList() failed: %s", e)

    # JSON-encoded string
    if isinstance(payload, str):
        s = str(payload)
        try:
            v = json.loads(s)
            if isinstance(v, (list, tuple)):
                result = [str(p) for p in v if p is not None]
                _logger.debug("_coerce_paths: parsed JSON string with %d items", len(result))
                return result
        except Exception:
            pass
        _logger.debug("_coerce_paths: treated string as single path")
        return [s]

    # Fallback
    _logger.debug("_coerce_paths: converted to string fallback")
    return [str(payload)]


def run(argv: list[str] | None = None) -> int:
    """Entry point: create QApplication, load QML, expose `Main` backend."""
    if argv is None:
        argv = sys.argv

    argv = _apply_cli_logging_options(list(argv))

    # Apply CLI-provided env overrides (IMAGE_VIEWER_LOG_LEVEL / IMAGE_VIEWER_LOG_CATS)
    # after parsing, because many module-level loggers are created before env vars exist.
    setup_logger()
    _logger.info("Starting Image Viewer (QML)")

    app = QApplication(argv)

    settings_path = abs_path_str(_BASE_DIR / "settings.json")
    settings = SettingsManager(settings_path)

    theme = settings.get("theme", "dark")
    font_size = int(settings.get("font_size", 10))
    apply_theme(app, theme, font_size)

    engine = ImageEngine()
    main = Main(engine=engine, settings=settings)

    # Ensure engine-owned worker threads are stopped cleanly before Qt starts
    # tearing down QObjects, otherwise we can hit:
    #   "QThread: Destroyed while thread '' is still running"
    app.aboutToQuit.connect(engine.shutdown)

    qml_engine = QQmlApplicationEngine()
    qml_engine.addImageProvider("engine", main.engine_image_provider)
    qml_engine.addImageProvider("thumb", main.thumb_provider)

    qml_url = QUrl.fromLocalFile(str(_BASE_DIR / "qml" / "App.qml"))
    qml_engine.load(qml_url)
    if not qml_engine.rootObjects():
        _logger.error("Failed to load QML root: %s", qml_url.toString())
        return 1

    root = qml_engine.rootObjects()[0]
    root.setProperty("main", main)

    # Emit an immediate QML-facing debug message to confirm the binding works.
    # Use contextlib.suppress to avoid any startup failures if printing fails.
    with contextlib.suppress(Exception):
        try:
            main.qmlDebug("[STARTUP] main property set on QML root")
        except Exception:
            # Fall back to logger only if direct call fails
            _logger.debug("[STARTUP] main property set (qmlDebug call failed)")

    # Startup restore: prefer reopening the last opened folder when it exists.
    # Fall back to last_parent_dir for backward compatibility.
    with contextlib.suppress(Exception):
        last_dir = getattr(settings, "last_open_dir", None) or settings.last_parent_dir
        if last_dir and os.path.isdir(last_dir):
            main.openFolder(last_dir)

    return app.exec()
