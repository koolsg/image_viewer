from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal


class ExplorerState(QObject):
    """State bound by the Explorer (grid/list) UI."""

    currentFolderChanged = Signal(str)
    imageFilesChanged = Signal()
    currentIndexChanged = Signal(int)
    imageModelChanged = Signal()
    clipboardHasFilesChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_folder = ""
        self._image_files: list[str] = []
        self._current_index = -1
        self._image_model: QObject | None = None
        self._clipboard_has_files = False

    def _get_current_folder(self) -> str:
        return str(self._current_folder)

    currentFolder = Property(str, _get_current_folder, notify=currentFolderChanged)  # type: ignore[arg-type]

    def _get_image_files(self) -> list[str]:
        return list(self._image_files)

    imageFiles = Property(list, _get_image_files, notify=imageFilesChanged)  # type: ignore[arg-type]

    def _get_current_index(self) -> int:
        return int(self._current_index)

    currentIndex = Property(int, _get_current_index, notify=currentIndexChanged)  # type: ignore[arg-type]

    def _get_image_model(self) -> QObject:
        return self._image_model  # type: ignore[return-value]

    imageModel = Property(QObject, _get_image_model, notify=imageModelChanged)  # type: ignore[arg-type]

    def _get_clipboard_has_files(self) -> bool:
        return bool(self._clipboard_has_files)

    clipboardHasFiles = Property(bool, _get_clipboard_has_files, notify=clipboardHasFilesChanged)  # type: ignore[arg-type]

    # ---- internal mutation helpers (called by backend) ----
    def _set_current_folder(self, folder: str) -> None:
        f = str(folder)
        if f == self._current_folder:
            return
        self._current_folder = f
        self.currentFolderChanged.emit(f)

    def _set_image_files(self, files: list[str]) -> None:
        self._image_files = list(files)
        self.imageFilesChanged.emit()

    def _set_current_index(self, idx: int) -> None:
        i = int(idx)
        if i == self._current_index:
            return
        self._current_index = i
        self.currentIndexChanged.emit(i)

    def _set_image_model(self, model: QObject) -> None:
        if model is self._image_model:
            return
        self._image_model = model
        self.imageModelChanged.emit()

    def _set_clipboard_has_files(self, has: bool) -> None:
        v = bool(has)
        if v == self._clipboard_has_files:
            return
        self._clipboard_has_files = v
        self.clipboardHasFilesChanged.emit(v)
