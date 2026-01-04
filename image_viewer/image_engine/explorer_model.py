"""Explorer model: UI-thread table model backed by Engine snapshots.

This model replaces QFileSystemModel usage in Explorer mode.
It is intentionally lightweight and does not perform disk I/O; it consumes
snapshots (plain dicts) emitted by the engine core thread.

Threading:
- All QPixmap/QIcon creation happens here (UI thread).
- EngineCore only sends bytes + primitive metadata.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QFileInfo, QModelIndex, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFileIconProvider

from image_viewer.logger import get_logger
from image_viewer.path_utils import db_key

_logger = get_logger("explorer_model")


_KB = 1000
_MB = 1000**2
_GB = 1000**3


@dataclass
class ExplorerEntry:
    path: str
    name: str
    suffix: str
    size: int
    mtime_ms: int
    is_image: bool
    width: int | None = None
    height: int | None = None


class ExplorerTableModel(QAbstractTableModel):
    """Flat file list model with a Resolution column.

    Columns match ImageFileSystemModel layout:
    0 Name, 1 Size, 2 Type, 3 Modified, 4 Resolution
    """

    # Compatibility signal used by some widgets (optional)
    progress = Signal(int, int)

    COL_NAME = 0
    COL_SIZE = 1
    COL_TYPE = 2
    COL_MOD = 3
    COL_RES = 4

    def __init__(self, engine, parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._folder: str | None = None

        self._entries: list[ExplorerEntry] = []
        self._row_for_key: dict[str, int] = {}

        self._thumb_bytes: dict[str, bytes] = {}
        self._thumb_icons: dict[str, QIcon] = {}
        self._thumb_size: tuple[int, int] = (256, 195)

        self._icon_provider = QFileIconProvider()

        # Engine feeds
        with contextlib.suppress(Exception):
            engine.explorer_entries_changed.connect(self._on_entries_changed)
        with contextlib.suppress(Exception):
            engine.explorer_thumb_rows.connect(self._on_thumb_rows)
        with contextlib.suppress(Exception):
            engine.explorer_thumb_generated.connect(self._on_thumb_generated)

    # ---- Qt model basics -----------------------------------------
    def rowCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        if parent is not None and parent.isValid():
            return 0
        return len(self._entries)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        return 5

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # type: ignore[override]
        if orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)
        if role == Qt.ItemDataRole.DisplayRole:
            return ["Name", "Size", "Type", "Modified", "Resolution"][int(section)]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int):  # type: ignore[override]  # noqa: PLR0911, PLR0912
        if not index.isValid():
            return None
        row = int(index.row())
        col = int(index.column())
        if row < 0 or row >= len(self._entries):
            return None

        entry = self._entries[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.COL_NAME:
                return entry.name
            if col == self.COL_SIZE:
                return self._fmt_size(entry.size)
            if col == self.COL_TYPE:
                return entry.suffix
            if col == self.COL_MOD:
                if entry.mtime_ms:
                    try:
                        dt = datetime.fromtimestamp(entry.mtime_ms / 1000)
                        return dt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        return ""
                return ""
            if col == self.COL_RES:
                if entry.width and entry.height:
                    return f"{entry.width}x{entry.height}"
                return ""

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == self.COL_NAME:
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            if col in (self.COL_SIZE, self.COL_RES):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter

        if role == Qt.ItemDataRole.DecorationRole and col == self.COL_NAME:
            key = db_key(entry.path)

            # Prefer cached thumbnail icon for images.
            if entry.is_image:
                icon = self._thumb_icons.get(key)
                if icon is not None:
                    return icon

                thumb = self._thumb_bytes.get(key)
                if thumb is not None:
                    pix = QPixmap()
                    if pix.loadFromData(thumb):
                        # Scale for icon grids
                        tw, th = self._thumb_size
                        if tw and th:
                            pix = pix.scaled(
                                tw, th, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                            )
                        icon = QIcon(pix)
                        self._thumb_icons[key] = icon
                        return icon

                # IMPORTANT: Do not trigger decoding from paint/DecorationRole.
                # Thumbnail generation is driven by the engine-core FS/DB worker
                # which compares (path + size + mtime + thumb dims) and only
                # requests decodes for missing/outdated entries.

            # Fallback: OS icon
            with contextlib.suppress(Exception):
                return self._icon_provider.icon(QFileInfo(entry.path))
            return None

        if role == Qt.ItemDataRole.ToolTipRole:
            parts = [entry.name]
            if entry.width and entry.height:
                parts.append(f"Resolution: {entry.width}x{entry.height}")
            if entry.size:
                parts.append(f"Size: {self._fmt_size(entry.size)}")
            return "\n".join(parts)

        return None

    # ---- sorting ---------------------------------------------------
    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:  # type: ignore[override]
        reverse = order == Qt.SortOrder.DescendingOrder

        def key_fn(e: ExplorerEntry):
            if column == self.COL_NAME:
                return e.name.lower()
            if column == self.COL_SIZE:
                return e.size
            if column == self.COL_TYPE:
                return e.suffix.lower()
            if column == self.COL_MOD:
                return e.mtime_ms
            if column == self.COL_RES:
                return (e.width or 0) * (e.height or 0)
            return e.name.lower()

        self.layoutAboutToBeChanged.emit()
        try:
            self._entries.sort(key=key_fn, reverse=reverse)
            self._rebuild_index()
        finally:
            self.layoutChanged.emit()

    # ---- compatibility helpers (QFileSystemModel-ish) --------------
    def filePath(self, index: QModelIndex) -> str:
        if not index.isValid():
            return ""
        row = int(index.row())
        if 0 <= row < len(self._entries):
            return self._entries[row].path
        return ""

    def isDir(self, index: QModelIndex) -> bool:
        # Explorer model is file-only.
        return False

    def set_view_mode(self, mode: str) -> None:
        # Used by view toggles.
        self._thumb_icons.clear()
        self._thumb_bytes.clear()

    def set_thumb_size(self, width: int, height: int) -> None:
        self._thumb_size = (int(width), int(height))
        self._thumb_icons.clear()
        with contextlib.suppress(Exception):
            self._engine.set_thumbnail_size(int(width), int(height))
        # Trigger refresh for icon scaling.
        if self._entries:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._entries) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DecorationRole])

    def batch_load_thumbnails(self, _root_index: QModelIndex | None = None) -> None:
        # EngineCore starts DB preload on open_folder.
        return

    # The following are no-ops for compatibility with code paths that tweak QFileSystemModel.
    def setNameFilters(self, _filters) -> None:
        return

    def setNameFilterDisables(self, _value: bool) -> None:
        return

    def nameFilters(self):
        return []

    def nameFilterDisables(self):
        return True

    def setFilter(self, _filter) -> None:
        return

    def filter(self):
        return 0

    def setIconProvider(self, provider) -> None:
        # Allow UI to override OS icon provider.
        self._icon_provider = provider

    def setRootPath(self, folder_path: str):
        # Backwards compatible entry point.
        with contextlib.suppress(Exception):
            self._engine.open_folder(folder_path)
        return QModelIndex()

    # ---- engine signal handlers ------------------------------------
    def _on_entries_changed(self, folder_path: str, entries: list[dict]) -> None:
        self.beginResetModel()
        try:
            same_folder = self._folder == folder_path
            old_thumb_bytes = self._thumb_bytes if same_folder else {}
            old_thumb_icons = self._thumb_icons if same_folder else {}

            self._folder = folder_path
            self._entries = [
                ExplorerEntry(
                    path=str(Path(e.get("path", ""))),
                    name=e.get("name") or Path(e.get("path", "")).name,
                    suffix=e.get("suffix") or "",
                    size=int(e.get("size") or 0),
                    mtime_ms=int(e.get("mtime_ms") or 0),
                    is_image=bool(e.get("is_image")),
                )
                for e in entries
            ]
            self._rebuild_index()

            # Preserve thumbnails for unchanged files to avoid flicker.
            if same_folder:
                keys = set(self._row_for_key.keys())
                self._thumb_bytes = {k: v for k, v in old_thumb_bytes.items() if k in keys}
                self._thumb_icons = {k: v for k, v in old_thumb_icons.items() if k in keys}
            else:
                self._thumb_bytes.clear()
                self._thumb_icons.clear()
        finally:
            self.endResetModel()

    def _on_thumb_rows(self, rows: list[dict]) -> None:
        changed_rows: set[int] = set()
        for row in rows:
            try:
                path = str(Path(str(row.get("path"))))
                key = db_key(path)

                thumb = row.get("thumbnail")
                if thumb is not None:
                    self._thumb_bytes[key] = bytes(thumb)

                w = row.get("width")
                h = row.get("height")

                idx = self._row_for_key.get(key)
                if idx is not None:
                    entry = self._entries[idx]
                    entry.width = int(w) if w is not None else entry.width
                    entry.height = int(h) if h is not None else entry.height
                    changed_rows.add(idx)
            except Exception:
                continue

        for r in sorted(changed_rows):
            top_left = self.index(r, 0)
            bottom_right = self.index(r, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DecorationRole, Qt.ItemDataRole.DisplayRole])

    def _on_thumb_generated(self, payload: dict) -> None:
        # Same payload shape as rows; treat as a single-row update.
        self._on_thumb_rows([payload])

    def _rebuild_index(self) -> None:
        self._row_for_key = {db_key(e.path): i for i, e in enumerate(self._entries)}

    @staticmethod
    def _fmt_size(size_bytes: int) -> str:
        try:
            size_bytes = int(size_bytes)
        except Exception:
            return ""
        size_bytes = max(size_bytes, 0)
        if size_bytes < _KB:
            return f"{size_bytes} B"
        if size_bytes < _MB:
            return f"{size_bytes / _KB:.1f} KB"
        if size_bytes < _GB:
            return f"{size_bytes / _MB:.1f} MB"
        return f"{size_bytes / _GB:.1f} GB"
