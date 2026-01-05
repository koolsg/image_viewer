from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from image_viewer.path_utils import db_key

_KB = 1000
_MB = 1000**2
_GB = 1000**3


@dataclass
class QmlImageEntry:
    path: str
    name: str
    suffix: str
    size: int
    mtime_ms: int
    is_image: bool
    key: str
    width: int | None = None
    height: int | None = None
    thumb_gen: int = 0


class QmlImageGridModel(QAbstractListModel):
    """QML-friendly, image-only grid model.

    It is fed by ImageEngine snapshots:
    - explorer_entries_changed (basic file stats)
    - explorer_thumb_rows / explorer_thumb_generated (thumbnail PNG bytes + width/height)

    The model does *not* expose raw thumbnail bytes to QML.
    QML uses `thumbUrl` which points at an ImageProvider (image://thumb/...).
    """

    class Roles:
        Path = Qt.ItemDataRole.UserRole + 1
        Name = Qt.ItemDataRole.UserRole + 2
        Suffix = Qt.ItemDataRole.UserRole + 3
        SizeBytes = Qt.ItemDataRole.UserRole + 4
        SizeText = Qt.ItemDataRole.UserRole + 5
        MTimeMs = Qt.ItemDataRole.UserRole + 6
        MTimeText = Qt.ItemDataRole.UserRole + 7
        Width = Qt.ItemDataRole.UserRole + 8
        Height = Qt.ItemDataRole.UserRole + 9
        ResolutionText = Qt.ItemDataRole.UserRole + 10
        Key = Qt.ItemDataRole.UserRole + 11
        ThumbGen = Qt.ItemDataRole.UserRole + 12
        ThumbUrl = Qt.ItemDataRole.UserRole + 13

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries: list[QmlImageEntry] = []
        self._row_for_key: dict[str, int] = {}
        self._role_getters = {
            int(self.Roles.Path): lambda e: e.path,
            int(self.Roles.Name): lambda e: e.name,
            int(self.Roles.Suffix): lambda e: e.suffix,
            int(self.Roles.SizeBytes): lambda e: int(e.size),
            int(self.Roles.SizeText): lambda e: self._fmt_size(e.size),
            int(self.Roles.MTimeMs): lambda e: int(e.mtime_ms),
            int(self.Roles.MTimeText): lambda e: self._fmt_mtime(e.mtime_ms),
            int(self.Roles.Width): lambda e: int(e.width or 0),
            int(self.Roles.Height): lambda e: int(e.height or 0),
            int(self.Roles.ResolutionText): lambda e: (f"{e.width}x{e.height}" if (e.width and e.height) else ""),
            int(self.Roles.Key): lambda e: e.key,
            int(self.Roles.ThumbGen): lambda e: int(e.thumb_gen),
            # Include thumb_gen to force QML Image to refresh when bytes arrive.
            int(self.Roles.ThumbUrl): lambda e: f"image://thumb/{e.thumb_gen}/{e.key}",
        }

    # ---- Qt model basics -----------------------------------------
    def rowCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        if parent is not None and parent.isValid():
            return 0
        return len(self._entries)

    def roleNames(self) -> dict[int, bytes]:  # type: ignore[override]
        return {
            int(self.Roles.Path): b"path",
            int(self.Roles.Name): b"name",
            int(self.Roles.Suffix): b"suffix",
            int(self.Roles.SizeBytes): b"sizeBytes",
            int(self.Roles.SizeText): b"sizeText",
            int(self.Roles.MTimeMs): b"mtimeMs",
            int(self.Roles.MTimeText): b"mtimeText",
            int(self.Roles.Width): b"width",
            int(self.Roles.Height): b"height",
            int(self.Roles.ResolutionText): b"resolutionText",
            int(self.Roles.Key): b"key",
            int(self.Roles.ThumbGen): b"thumbGen",
            int(self.Roles.ThumbUrl): b"thumbUrl",
        }

    def data(self, index: QModelIndex, role: int):  # type: ignore[override]
        if not index.isValid():
            return None

        row = int(index.row())
        if not (0 <= row < len(self._entries)):
            return None

        entry = self._entries[row]
        getter = self._role_getters.get(int(role))
        if getter is None:
            return None
        return getter(entry)

    # ---- mutations (engine feeds) --------------------------------
    def set_entries(self, entries: list[dict]) -> None:
        """Replace model contents from EngineCore folder snapshot."""
        self.beginResetModel()
        try:
            self._entries = []
            for d in entries:
                try:
                    if not bool(d.get("is_image")):
                        continue
                    path = str(d.get("path") or "")
                    if not path:
                        continue
                    name = d.get("name")
                    if not name:
                        # Keep it simple (avoid Path import in hot path).
                        name = path.replace("\\", "/").split("/")[-1]

                    suf = str(d.get("suffix") or "")
                    size = int(d.get("size") or 0)
                    mtime_ms = int(d.get("mtime_ms") or 0)
                    key = db_key(path)

                    self._entries.append(
                        QmlImageEntry(
                            path=path,
                            name=str(name),
                            suffix=suf,
                            size=size,
                            mtime_ms=mtime_ms,
                            is_image=True,
                            key=key,
                        )
                    )
                except Exception:
                    continue

            self._row_for_key = {e.key: i for i, e in enumerate(self._entries)}
        finally:
            self.endResetModel()

    def update_thumb_rows(self, rows: list[dict]) -> None:
        """Update entries (width/height + thumb gen)."""
        changed: set[int] = set()
        for row in rows:
            with contextlib.suppress(Exception):
                path = str(row.get("path") or "")
                if not path:
                    continue
                key = db_key(path)
                idx = self._row_for_key.get(key)
                if idx is None:
                    continue

                e = self._entries[idx]

                w = row.get("width")
                h = row.get("height")
                if w is not None:
                    e.width = int(w)
                if h is not None:
                    e.height = int(h)

                # We bump thumb_gen whenever the engine says something about this
                # row (DB preload or a newly generated thumb). This makes QML
                # re-request the thumb via the provider.
                e.thumb_gen += 1
                changed.add(idx)

        for idx in sorted(changed):
            qidx = self.index(idx, 0)
            self.dataChanged.emit(
                qidx,
                qidx,
                [
                    int(self.Roles.Width),
                    int(self.Roles.Height),
                    int(self.Roles.ResolutionText),
                    int(self.Roles.ThumbGen),
                    int(self.Roles.ThumbUrl),
                ],
            )

    @staticmethod
    def _fmt_mtime(mtime_ms: int) -> str:
        try:
            mtime_ms = int(mtime_ms)
        except Exception:
            return ""
        if mtime_ms <= 0:
            return ""
        with contextlib.suppress(Exception):
            dt = datetime.fromtimestamp(mtime_ms / 1000)
            return dt.strftime("%Y-%m-%d %H:%M")
        return ""

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
