from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtWidgets import QApplication

from image_viewer.image_engine.engine import ImageEngine
from image_viewer.logger import get_logger
from image_viewer.path_utils import abs_dir_str, abs_path_str, db_key
from image_viewer.qml_models import QmlImageGridModel
from image_viewer.settings_manager import SettingsManager
from image_viewer.styles import apply_theme

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
        with contextlib.suppress(Exception):
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

        data = self._thumb_bytes_by_key.get(key)
        if not data:
            return QPixmap()

        pix = QPixmap()
        if not pix.loadFromData(data):
            return QPixmap()

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
    imageModelChanged = Signal()

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

        self._pending_select_path: str | None = None

        # ---- Engine -> Main wiring ----
        with contextlib.suppress(Exception):
            self.engine.image_ready.connect(self._on_engine_image_ready)
        with contextlib.suppress(Exception):
            self.engine.file_list_updated.connect(self._on_engine_file_list_updated)
        with contextlib.suppress(Exception):
            self.engine.explorer_entries_changed.connect(self._on_engine_explorer_entries_changed)
        with contextlib.suppress(Exception):
            self.engine.explorer_thumb_rows.connect(self._on_engine_explorer_thumb_rows)
        with contextlib.suppress(Exception):
            self.engine.explorer_thumb_generated.connect(self._on_engine_explorer_thumb_generated)

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

    def _get_image_model(self) -> QObject:
        return self._image_model

    imageModel = Property(QObject, _get_image_model, notify=imageModelChanged)  # type: ignore[arg-type]

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
        with contextlib.suppress(Exception):
            self.settings.set("last_parent_dir", folder)

        # If a file was passed, remember and select once list arrives.
        if folder != p:
            self._pending_select_path = p
        else:
            self._pending_select_path = None

        self.engine.open_folder(folder)

    @Slot()
    def closeView(self) -> None:
        self._set_view_mode(False)

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

    @Slot(str)
    def copyText(self, text: str) -> None:
        with contextlib.suppress(Exception):
            QGuiApplication.clipboard().setText(str(text))

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
        self.engine.request_decode(str(path), (s, s))

    # ---- internal helpers ----
    def _set_current_path(self, path: str) -> None:
        if str(path) == self._current_path:
            return

        self._current_path = str(path)
        self.currentPathChanged.emit(self._current_path)

        self._generation += 1
        self._image_url = ""
        self.imageUrlChanged.emit("")

        if not self._current_path:
            return

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

        self._generation += 1
        self._image_url = f"image://engine/{self._generation}/{path}"
        self.imageUrlChanged.emit(self._image_url)


def run(argv: list[str] | None = None) -> int:
    """Entry point: create QApplication, load QML, expose `Main` backend."""
    if argv is None:
        argv = sys.argv

    argv = _apply_cli_logging_options(list(argv))

    app = QApplication(argv)

    settings_path = abs_path_str(_BASE_DIR / "settings.json")
    settings = SettingsManager(settings_path)

    theme = settings.get("theme", "dark")
    font_size = int(settings.get("font_size", 10))
    apply_theme(app, theme, font_size)

    engine = ImageEngine()
    main = Main(engine=engine, settings=settings)

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

    # Startup restore: open last folder when it exists.
    with contextlib.suppress(Exception):
        last_dir = settings.last_parent_dir
        if last_dir and os.path.isdir(last_dir):
            main.openFolder(last_dir)

    return app.exec()
