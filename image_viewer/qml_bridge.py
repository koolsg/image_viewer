from __future__ import annotations

import contextlib
import inspect
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtQuick import QQuickImageProvider

from image_viewer.path_utils import db_key
from image_viewer.qml_models import QmlImageGridModel

if TYPE_CHECKING:
    pass


class EngineImageProvider(QQuickImageProvider):
    """QML image provider that fetches pixmaps from ImageEngine cache."""

    def __init__(self, engine: Any) -> None:
        super().__init__(QQuickImageProvider.ImageType.Pixmap)
        self._engine = engine

    def requestPixmap(self, id: str, size: Any, requestedSize: Any) -> QPixmap:
        """Fetch pixmap from engine. ID format: '{generation}/{path}'."""
        # Split generation from path. Generation is always a number.
        parts = id.split("/", 1)
        path = parts[1] if len(parts) == 2 and parts[0].isdigit() else id  # noqa: PLR2004

        if not self._engine:
            return QPixmap()

        pixmap = self._engine.get_cached_pixmap(path)
        if not pixmap or pixmap.isNull():
            from PySide6.QtCore import QUrl  # noqa: PLC0415

            path = QUrl.fromPercentEncoding(path.encode("utf-8"))
            pixmap = self._engine.get_cached_pixmap(path)

        if pixmap and not pixmap.isNull():
            return pixmap

        return QPixmap()


class ThumbImageProvider(QQuickImageProvider):
    """QML image provider for thumbnail PNG bytes (image://thumb/<gen>/<key>)."""

    def __init__(self, thumb_bytes_by_key: dict[str, bytes]) -> None:
        super().__init__(QQuickImageProvider.ImageType.Pixmap)
        self._thumb_bytes_by_key = thumb_bytes_by_key

    def requestPixmap(self, id: str, size: Any, requestedSize: Any) -> QPixmap:
        # Expected: "{generation}/{db_key}". Generation is only used to bust QML cache.
        parts = id.split("/", 1)
        key = parts[1] if len(parts) == 2 and parts[0].isdigit() else id  # noqa: PLR2004

        data = self._thumb_bytes_by_key.get(key)
        if not data:
            return QPixmap()

        pix = QPixmap()
        if not pix.loadFromData(data):
            return QPixmap()

        # Respect requestedSize when provided.
        try:
            rw = int(getattr(requestedSize, "width", lambda: 0)())
            rh = int(getattr(requestedSize, "height", lambda: 0)())
        except Exception:
            rw, rh = 0, 0

        if rw > 0 and rh > 0:
            from PySide6.QtCore import Qt  # noqa: PLC0415

            pix = pix.scaled(
                rw,
                rh,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        return pix


class AppController(QObject):
    """Minimal QML POC controller.

    This is intentionally small and test-driven:
    - Tracks a current path and a monotonically increasing generation.
    - Requests preview decodes via the existing ImageEngine.
    - Uses EngineImageProvider to serve images to QML without base64 overhead.
    """

    imageReady = Signal(str, str, int)  # path, payload (image:// url), generation
    currentPathChanged = Signal(str)
    imageUrlChanged = Signal(str)
    zoomChanged = Signal(float)
    fitModeChanged = Signal(bool)
    imageFilesChanged = Signal()
    currentIndexChanged = Signal(int)
    viewModeChanged = Signal(bool)
    currentFolderChanged = Signal(str)
    imageModelChanged = Signal()

    def __init__(self, engine: Any | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._current_folder: str = ""
        self._image_files: list[str] = []
        self._current_index: int = -1
        self._view_mode: bool = False
        self._pending_select_path: str | None = None

        self._current_path: str = ""
        self._zoom: float = 1.0
        self._fit_mode: bool = True
        self._generation: int = 0
        self._image_url: str = ""
        self.image_provider = EngineImageProvider(engine)

        # Explorer/QML model + thumbnail bytes
        self._image_model = QmlImageGridModel(self)
        self._thumb_bytes_by_key: dict[str, bytes] = {}
        self.thumb_provider = ThumbImageProvider(self._thumb_bytes_by_key)

        # Wire engine signals if available.
        if self._engine is not None:
            # Keep controller usable in unit tests (mock engines may not expose signals).
            with contextlib.suppress(Exception):
                self._engine.image_ready.connect(self.on_engine_image_ready)
            with contextlib.suppress(Exception):
                self._engine.file_list_updated.connect(self._on_engine_file_list_updated)

            # Explorer snapshots (metadata + thumbnail DB feeds)
            with contextlib.suppress(Exception):
                self._engine.explorer_entries_changed.connect(self._on_engine_explorer_entries_changed)
            with contextlib.suppress(Exception):
                self._engine.explorer_thumb_rows.connect(self._on_engine_explorer_thumb_rows)
            with contextlib.suppress(Exception):
                self._engine.explorer_thumb_generated.connect(self._on_engine_explorer_thumb_generated)

    def _get_image_model(self) -> QObject:
        return self._image_model

    imageModel = Property(QObject, _get_image_model, notify=imageModelChanged)  # type: ignore[arg-type]

    # ---- Folder + file list state (QML-first) ----

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
        if new_idx == self._current_index:
            return
        if not self._image_files:
            self._current_index = -1
            self.currentIndexChanged.emit(self._current_index)
            return
        new_idx = max(new_idx, 0)
        if new_idx >= len(self._image_files):
            new_idx = len(self._image_files) - 1

        self._current_index = new_idx
        self.currentIndexChanged.emit(self._current_index)
        self._set_current_path(self._image_files[self._current_index])

    currentIndex = Property(int, _get_current_index, _set_current_index, notify=currentIndexChanged)  # type: ignore[arg-type]

    def _get_view_mode(self) -> bool:
        return bool(self._view_mode)

    def _set_view_mode(self, val: bool) -> None:
        new_val = bool(val)
        if self._view_mode != new_val:
            self._view_mode = new_val
            self.viewModeChanged.emit(new_val)

    viewMode = Property(bool, _get_view_mode, _set_view_mode, notify=viewModeChanged)  # type: ignore[arg-type]

    @Slot(str)
    def openFolder(self, path_or_url: str) -> None:
        """Open a folder from QML.

        QML dialogs provide URLs (e.g. file:///C:/Images). Normalize those to
        an absolute OS-native directory path before calling ImageEngine.
        """
        if self._engine is None:
            return

        from PySide6.QtCore import QUrl  # noqa: PLC0415

        from image_viewer.path_utils import abs_dir_str  # noqa: PLC0415

        p = str(path_or_url)
        if p.startswith("file:"):
            url = QUrl(p)
            if url.isLocalFile():
                p = url.toLocalFile()

        folder = abs_dir_str(p)
        self._current_folder = folder
        self.currentFolderChanged.emit(folder)

        # If a file was passed accidentally, remember it and select it once the
        # engine publishes the file list.
        if folder != p:
            self._pending_select_path = p
        else:
            self._pending_select_path = None

        self._engine.open_folder(folder)

    def _apply_file_list(self, files: list[str]) -> None:
        self._image_files = list(files)
        self.imageFilesChanged.emit()

        # Apply pending selection (e.g. started with a specific file).
        if self._pending_select_path:
            try:
                from image_viewer.path_utils import abs_path_str  # noqa: PLC0415

                target = abs_path_str(self._pending_select_path)
            except Exception:
                target = str(self._pending_select_path)

            self._pending_select_path = None
            if target in self._image_files:
                self._set_current_index(self._image_files.index(target))
                return

        # Default selection.
        if self._image_files:
            if self._current_index < 0 or self._current_index >= len(self._image_files):
                self._set_current_index(0)
        else:
            self._set_current_index(-1)

    @Slot(list)
    def _on_engine_file_list_updated(self, files: list[str]) -> None:
        self._apply_file_list(files)

    @Slot(str, list)
    def _on_engine_explorer_entries_changed(self, folder_path: str, entries: list[dict]) -> None:
        # Feed the QML grid model. It filters to images only.
        self._image_model.set_entries(entries)
        self.imageModelChanged.emit()

        # Keep current folder in sync for UI.
        with contextlib.suppress(Exception):
            if folder_path:
                self._current_folder = str(folder_path)
                self.currentFolderChanged.emit(self._current_folder)

    @Slot(list)
    def _on_engine_explorer_thumb_rows(self, rows: list[dict]) -> None:
        # Cache thumbnail bytes for the provider + update model (width/height + bust-cache gen)
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
        # Same shape as thumb rows.
        self._on_engine_explorer_thumb_rows([payload])

    def _get_current_path(self) -> str:
        return self._current_path

    def _set_current_path(self, path: str) -> None:
        if self._current_path != path:
            # Normalize path early
            try:
                from image_viewer.path_utils import abs_path_str  # noqa: PLC0415

                norm_path = abs_path_str(path)
            except Exception:
                norm_path = path

            self._current_path = norm_path
            self._generation += 1

            # Clear previous image URL immediately to ensure we don't show stale images
            self._image_url = ""
            self.imageUrlChanged.emit("")
            self.currentPathChanged.emit(norm_path)

            # Check if the requested image (norm_path) is already in the engine cache
            if self._engine:
                try:
                    get_cached = getattr(self._engine, "get_cached_pixmap", None)
                    cached = get_cached(norm_path) if callable(get_cached) else None
                except Exception:
                    cached = None

                if isinstance(cached, QPixmap) and not cached.isNull():
                    # ONLY show if the CACHED image is exactly the one we just requested
                    self._image_url = f"image://engine/{self._generation}/{norm_path}"
                    self.imageUrlChanged.emit(self._image_url)
                    return

            # If not cached, trigger a new decode request for the correct path
            self.requestPreview(path, 2048)

    currentPath = Property(str, _get_current_path, _set_current_path, notify=currentPathChanged)  # type: ignore[arg-type]

    def _get_image_url(self) -> str:
        return self._image_url

    imageUrl = Property(str, _get_image_url, notify=imageUrlChanged)  # type: ignore[arg-type]

    def _get_zoom(self) -> float:
        return self._zoom

    def _set_zoom(self, val: float) -> None:
        if self._zoom != val:
            self._zoom = val
            self.zoomChanged.emit(val)

    zoom = Property(float, _get_zoom, _set_zoom, notify=zoomChanged)  # type: ignore[arg-type]

    def _get_fit_mode(self) -> bool:
        return self._fit_mode

    def _set_fit_mode(self, val: bool) -> None:
        if self._fit_mode != val:
            self._fit_mode = val
            self.fitModeChanged.emit(val)

    fitMode = Property(bool, _get_fit_mode, _set_fit_mode, notify=fitModeChanged)  # type: ignore[arg-type]

    @Slot()
    def currentGeneration(self) -> int:
        return int(self._generation)

    @Slot(str)
    def setCurrentPathSlot(self, path: str) -> None:
        self._set_current_path(str(path))

    @Slot(str, int)
    def requestPreview(self, path: str, size: int) -> None:
        """Ask the engine to decode a square preview for `path`."""
        if not self._engine:
            return

        target = (int(size), int(size))

        # NOTE: Some unit tests monkeypatch engine.request_decode using MethodType
        # but provide a function that does not accept `self`. To be resilient,
        # inspect the underlying function signature.
        meth = getattr(self._engine, "request_decode", None)
        if meth is None:
            return

        func = getattr(meth, "__func__", None)
        if func is not None:
            try:
                params = list(inspect.signature(func).parameters)
            except Exception:
                params = []
            if params and params[0] != "self":
                func(str(path), target)  # type: ignore[misc]
                return

        # Normal (bound) instance method path
        meth(str(path), target)

    # --- QML control slots (QML-first navigation) ---

    @Slot()
    def nextImage(self) -> None:
        if not self._image_files:
            return
        self._set_current_index(self._current_index + 1)

    @Slot()
    def prevImage(self) -> None:
        if not self._image_files:
            return
        self._set_current_index(self._current_index - 1)

    @Slot()
    def firstImage(self) -> None:
        if not self._image_files:
            return
        self._set_current_index(0)

    @Slot()
    def lastImage(self) -> None:
        if not self._image_files:
            return
        self._set_current_index(len(self._image_files) - 1)

    @Slot()
    def closeViewWindow(self) -> None:
        """In the QML-first app, this means: exit the Viewer page."""
        self._set_view_mode(False)

    # ---- QML helpers for context menus ---------------------------

    @Slot(str)
    def copyText(self, text: str) -> None:
        with contextlib.suppress(Exception):
            QGuiApplication.clipboard().setText(str(text))

    @Slot(str)
    def revealInExplorer(self, path: str) -> None:
        # Open the containing folder (best-effort).
        from PySide6.QtCore import QUrl  # noqa: PLC0415

        p = str(path)
        url = QUrl.fromLocalFile(p)
        if url.isValid():
            # Note: selecting the file in Explorer is Windows-specific; for now,
            # just open the folder.
            with contextlib.suppress(Exception):
                folder_url = QUrl.fromLocalFile(url.toLocalFile().rsplit("\\", 1)[0])
                QDesktopServices.openUrl(folder_url)

    def getImageUrl(self) -> str:
        return self._image_url

    # ---- Integration hook for the main window ----

    def on_engine_image_ready(self, path: str, pixmap: QPixmap, error: object | None) -> None:
        if error is not None:
            return
        if not path:
            return

        from image_viewer.path_utils import abs_path_str  # noqa: PLC0415

        try:
            abs_path = abs_path_str(path)
        except Exception:
            abs_path = str(path)

        # If this decode corresponds to the currently selected image, update the
        # viewer image URL. Otherwise, treat it as a thumbnail/prefetch result
        # and just let the providers serve it from cache.
        if self._current_path and abs_path == self._current_path:
            self._image_url = f"image://engine/{self._generation}/{path}"
            self.imageUrlChanged.emit(self._image_url)
            self.imageReady.emit(path, self._image_url, self._generation)
