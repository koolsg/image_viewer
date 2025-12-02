"""Explorer grid/detail widget with thumbnail + detail views and disk cache."""

from __future__ import annotations

import contextlib
import ctypes
import hashlib
import shutil
from collections.abc import Iterable
from ctypes import wintypes
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import (
    QDateTime,
    QDir,
    QMimeData,
    QModelIndex,
    QPoint,
    QSize,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QGuiApplication,
    QIcon,
    QImage,
    QImageReader,
    QKeySequence,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFileIconProvider,
    QFileSystemModel,
    QHeaderView,
    QListView,
    QMenu,
    QMessageBox,
    QStackedLayout,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from .logger import get_logger

_logger = get_logger("ui_explorer_grid")


# --------------------------- Model -------------------------------------------
class ImageFileSystemModel(QFileSystemModel):
    """FS model with loader-backed thumbnail cache and extra Resolution column."""

    COL_NAME = 0
    COL_SIZE = 1
    COL_TYPE = 2
    COL_MOD = 3
    # Resolution column will be appended after base columns; keep symbolic name.
    COL_RES = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumb_cache: dict[str, QIcon] = {}
        self._thumb_pending: set[str] = set()
        self._loader = None
        self._thumb_size: tuple[int, int] = (256, 195)
        self._view_mode: str = "thumbnail"
        self._meta: dict[str, tuple[int | None, int | None, int | None, float | None]] = {}
        self._disk_cache_name: str = "image_viewer_thumbs"

    # --- loader wiring -----------------------------------------------------
    def set_loader(self, loader) -> None:
        try:
            if self._loader and hasattr(self._loader, "image_decoded"):
                with contextlib.suppress(Exception):
                    self._loader.image_decoded.disconnect(self._on_thumbnail_ready)
            self._loader = loader
            if self._loader and hasattr(self._loader, "image_decoded"):
                self._loader.image_decoded.connect(self._on_thumbnail_ready)
        except Exception as exc:
            _logger.debug("set_loader failed: %s", exc)

    def set_thumb_size(self, width: int, height: int) -> None:
        self._thumb_size = (width, height)

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = mode

    # --- columns -----------------------------------------------------------
    def columnCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        parent = parent or QModelIndex()
        return super().columnCount(parent) + 1  # add Resolution column

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # type: ignore[override]
        try:
            base_cols = super().columnCount()
            if (
                orientation == Qt.Horizontal
                and role == Qt.DisplayRole
                and section == base_cols
            ):
                return "Resolution"
            if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            return super().headerData(section, orientation, role)
        except Exception:
            return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int):  # type: ignore[override]  # noqa: PLR0911, PLR0912
        try:
            if not index.isValid():
                return None
            base_cols = super().columnCount(index.parent())
            col = index.column()
            path = self.filePath(index)
            self._meta_update_basic(path)
            # Resolution column
            if col == base_cols:
                if role in (Qt.DisplayRole, Qt.ToolTipRole):
                    return self._resolution_str(index)
                if role == Qt.DecorationRole:
                    return None
            if col > base_cols:
                return None

            # Type column -> extension only
            if col == self.COL_TYPE and role == Qt.DisplayRole:
                suffix = Path(path).suffix.lower().lstrip(".")
                return suffix

            # Size column -> KB/MB (decimal)
            if col == self.COL_SIZE and role == Qt.DisplayRole:
                try:
                    info = self.fileInfo(index)
                    return self._fmt_size(int(info.size()))
                except Exception:
                    return super().data(index, role)
            if role == Qt.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

            # Decoration for thumbnails
            if (
                role == Qt.DecorationRole
                and self._view_mode == "thumbnail"
                and col == self.COL_NAME
            ):
                if icon := self._thumb_cache.get(path):
                    return icon
                self._request_thumbnail(path)

            # Tooltip for thumbnails
            if (
                role == Qt.ToolTipRole
                and self._view_mode == "thumbnail"
                and col == self.COL_NAME
            ):
                return self._build_tooltip(path)

            return super().data(index, role)
        except Exception as exc:
            _logger.debug("data() failed: %s", exc)
            return super().data(index, role)

    def _resolution_str(self, index: QModelIndex) -> str:
        path = self.filePath(index)
        try:
            self._meta_update_basic(path)
            w, h, _size_bytes, _mtime = self._meta.get(path, (None, None, None, None))
            if w is None or h is None:
                reader = QImageReader(path)
                size = reader.size()
                if size.isValid():
                    w = int(size.width())
                    h = int(size.height())
                    prev = self._meta.get(path, (None, None, None, None))
                    self._meta[path] = (w, h, prev[2], prev[3])
            if w and h:
                return f"{w}x{h}"
        except Exception:
            pass
        return ""

    # --- meta helpers ------------------------------------------------------
    def _meta_update_basic(self, path: str) -> None:
        try:
            info = self.fileInfo(self.index(path))
            size_bytes = info.size()
            mtime = info.lastModified().toSecsSinceEpoch()
            prev = self._meta.get(path, (None, None, None, None))
            self._meta[path] = (prev[0], prev[1], size_bytes, float(mtime))
        except Exception:
            self._meta[path] = self._meta.get(path, (None, None, None, None))

    def meta_string(self, index: QModelIndex) -> str:
        path = self.filePath(index)
        size_str = ""
        mtime_str = ""
        res_str = ""
        try:
            self._meta_update_basic(path)
            w, h, size_bytes, mtime = self._meta.get(path, (None, None, None, None))
            if size_bytes is not None:
                size_str = self._fmt_size(int(size_bytes))
            if mtime is not None:
                mtime_dt = QDateTime.fromSecsSinceEpoch(int(mtime))
                mtime_str = mtime_dt.toString("yyyy-MM-dd HH:mm")
            if w and h:
                res_str = f"{w}x{h}"
        except Exception:
            pass
        parts = [p for p in [res_str, size_str, mtime_str] if p]
        return " бд ".join(parts)

    def _build_tooltip(self, path: str) -> str:
        """Build tooltip with file metadata."""
        try:
            filename = Path(path).name
            self._meta_update_basic(path)
            w, h, size_bytes, mtime = self._meta.get(path, (None, None, None, None))

            # Get resolution (from cache or read header)
            if w is None or h is None:
                reader = QImageReader(path)
                size = reader.size()
                if size.isValid():
                    w = int(size.width())
                    h = int(size.height())
                    prev = self._meta.get(path, (None, None, None, None))
                    self._meta[path] = (w, h, prev[2], prev[3])

            parts = [f"File: {filename}"]
            if w and h:
                parts.append(f"Resolution: {w}x{h}")
            if size_bytes is not None:
                parts.append(f"Size: {self._fmt_size(int(size_bytes))}")
            if mtime is not None:
                mtime_dt = QDateTime.fromSecsSinceEpoch(int(mtime))
                parts.append(f"Modified: {mtime_dt.toString('yyyy-MM-dd HH:mm')}")

            return "\n".join(parts)
        except Exception as exc:
            _logger.debug("_build_tooltip failed: %s", exc)
            return Path(path).name

    @staticmethod
    def _fmt_size(size: int) -> str:
        kb = 1000
        mb = kb * 1000
        if size >= mb:
            return f"{size/mb:.1f} MB"
        if size >= kb:
            return f"{size/kb:.1f} KB"
        return f"{size} B"

    # --- thumbnail load/save ------------------------------------------------
    def _request_thumbnail(self, path: str) -> None:
        # Skip if not a file (e.g., directory)
        if not Path(path).is_file():
            return
        if path in self._thumb_cache:
            return
        icon = self._load_disk_icon(path)
        if icon is not None:
            self._thumb_cache[path] = icon
            idx = self.index(path)
            if idx.isValid():
                self.dataChanged.emit(idx, idx, [Qt.DecorationRole])
            return
        if not self._loader or path in self._thumb_pending:
            return
        self._thumb_pending.add(path)
        try:
            self._loader.request_load(
                path,
                target_width=self._thumb_size[0],
                target_height=self._thumb_size[1],
                size="both",
            )
        except Exception as exc:
            _logger.debug("request_load failed for %s: %s", path, exc)

    def _on_thumbnail_ready(self, path: str, image_data, error) -> None:
        try:
            self._thumb_pending.discard(path)
            if error or image_data is None:
                return
            height, width, _ = image_data.shape
            bytes_per_line = 3 * width
            q_image = QImage(
                image_data.data, width, height, bytes_per_line, QImage.Format_RGB888
            )
            pixmap = QPixmap.fromImage(q_image)
            if pixmap.isNull():
                return
            scaled = pixmap.scaled(
                self._thumb_size[0],
                self._thumb_size[1],
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._thumb_cache[path] = QIcon(scaled)
            prev = self._meta.get(path, (None, None, None, None))
            self._meta[path] = (
                int(width),
                int(height),
                prev[2],
                prev[3],
            )
            self._save_disk_icon(path, scaled)
            idx = self.index(path)
            if idx.isValid():
                self.dataChanged.emit(idx, idx, [Qt.DecorationRole, Qt.DisplayRole])
        except Exception as exc:
            _logger.debug("thumbnail_ready failed: %s", exc)

    def _disk_dir(self, path: str) -> Path:
        return Path(path).parent / ".cache" / self._disk_cache_name

    def _disk_path(self, path: str) -> Path:
        try:
            stat = Path(path).stat()
            stamp = f"{int(stat.st_mtime)}_{stat.st_size}"
        except Exception:
            stamp = "unknown"
        base = f"{Path(path).name}_{self._thumb_size[0]}x{self._thumb_size[1]}_{stamp}"
        digest = hashlib.sha1(base.encode("utf-8")).hexdigest()
        return self._disk_dir(path) / f"{digest}.png"

    def _load_disk_icon(self, path: str) -> QIcon | None:
        try:
            p = self._disk_path(path)
            if not p.exists():
                return None
            pix = QPixmap(str(p))
            if pix.isNull():
                return None
            prev = self._meta.get(path, (None, None, None, None))
            width = prev[0]
            height = prev[1]
            with contextlib.suppress(Exception):
                reader = QImageReader(path)
                size = reader.size()
                if size.isValid():
                    width = int(size.width())
                    height = int(size.height())
            self._meta[path] = (width, height, prev[2], prev[3])
            return QIcon(pix)
        except Exception:
            return None

    def _save_disk_icon(self, path: str, pixmap: QPixmap) -> None:
        try:
            p = self._disk_path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            pixmap.save(str(p), "PNG")
        except Exception:
            pass


# --------------------------- Main Widget -------------------------------------
class ThumbnailGridWidget(QWidget):
    """Explorer widget with thumbnail view (icons) and detail view (columns)."""

    image_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_folder: str | None = None
        self._clipboard_paths: list[str] = []
        self._clipboard_mode: str | None = None  # "copy" | "cut"

        self._model = ImageFileSystemModel(self)
        self._model.setFilter(QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self._model.setNameFilters(
            [
                "*.jpg",
                "*.jpeg",
                "*.png",
                "*.bmp",
                "*.gif",
                "*.webp",
                "*.tif",
                "*.tiff",
            ]
        )
        self._model.setNameFilterDisables(False)
        self._model.setIconProvider(_ImageOnlyIconProvider())

        # Thumbnail view (icon grid)
        self._list = QListView()
        self._list.setModel(self._model)
        self._list.setViewMode(QListView.ViewMode.IconMode)
        self._list.setResizeMode(QListView.ResizeMode.Adjust)
        self._list.setMovement(QListView.Movement.Static)
        self._list.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        self._list.setUniformItemSizes(True)
        self._list.setWordWrap(True)
        self._list.setSpacing(12)
        self._list.setIconSize(QSize(256, 195))
        self._list.setGridSize(QSize(256 + 32, 195 + 48))
        self._list.setAcceptDrops(True)
        self._list.activated.connect(self._on_activated)
        self._list.doubleClicked.connect(self._on_activated)
        self._list.setStyleSheet(
            """
            QListView {
                outline: 0;
            }
            QListView::item {
                border: 0;
            }
            QListView::item:selected {
                background: transparent;
                color: palette(text);
                outline: 20px solid #4A90E2;
                outline-offset: -10px;
            }
            QListView::item:selected:active {
                background: transparent;
                color: palette(text);
                outline: 20px solid #4A90E2;
                outline-offset: -10px;
            }
            QListView::item:selected:!active {
                background: transparent;
                color: palette(text);
            }
            QListView::item:hover {
                outline: 1px solid rgba(74, 144, 226, 120);
                outline-offset: -2px;
                background: transparent;
            }
            """
        )

        # Detail view (columns)
        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setRootIsDecorated(False)
        self._tree.setSortingEnabled(True)
        self._tree.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self._tree.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
        self._tree.doubleClicked.connect(self._on_activated)
        self._tree.header().setStretchLastSection(True)
        with contextlib.suppress(Exception):
            self._tree.sortByColumn(0, Qt.AscendingOrder)
        self._tree.setStyleSheet(
            """
            QTreeView::item:selected {
                background: rgba(74, 144, 226, 80);
                color: black;
                border: none;
                outline: 0;
            }
            QTreeView::item:selected:active {
                background: rgba(74, 144, 226, 110);
                color: black;
                border: none;
                outline: 0;
            }
            QTreeView::item:hover {
                background: rgba(74, 144, 226, 30);
            }
            """
        )

        self._stack = QStackedLayout()
        self._stack.addWidget(self._list)  # index 0 thumbnail
        self._stack.addWidget(self._tree)  # index 1 detail

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._stack)

        self._view_mode = "thumbnail"

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        _logger.debug("ThumbnailGridWidget initialized (stacked list/tree)")

    # Compatibility hooks -------------------------------------------------------
    def set_loader(self, loader) -> None:
        try:
            self._model.set_loader(loader)
        except Exception as exc:
            _logger.debug("set_loader failed: %s", exc)

    def resume_pending_thumbnails(self) -> None:
        return

    def set_disk_cache_folder_name(self, name: str) -> None:
        try:
            cleaned = name.strip() or "image_viewer_thumbs"
            self._model._disk_cache_name = cleaned
        except Exception:
            pass

    # Public API -----------------------------------------------------------------
    def load_folder(self, folder_path: str) -> None:
        try:
            if not Path(folder_path).is_dir():
                _logger.warning("not a directory: %s", folder_path)
                return
            idx = self._model.setRootPath(folder_path)
            self._list.setRootIndex(idx)
            self._tree.setRootIndex(idx)
            self._current_folder = folder_path
            self._list.clearSelection()
            self._tree.clearSelection()
            # Column sizing for tree
            with contextlib.suppress(Exception):
                header = self._tree.header()
                base_cols = self._model.columnCount() - 1  # resolution column index
                header.setSectionResizeMode(QHeaderView.ResizeToContents)
                header.setStretchLastSection(False)
                header.setDefaultAlignment(
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                )
                # Desired order: Name, Type, Size, Resolution, Modified
                header.moveSection(2, 1)  # Type next to Name
                header.moveSection(base_cols, 3)  # Resolution before Modified
                margin = 16
                for col in range(self._model.columnCount()):
                    width = max(self._tree.sizeHintForColumn(col), 48)
                    self._tree.setColumnWidth(col, width + margin)
        except Exception as exc:
            _logger.error("failed to load_folder %s: %s", folder_path, exc)

    def set_thumbnail_size_wh(self, width: int, height: int) -> None:
        try:
            w = max(32, min(1024, int(width)))
            h = max(32, min(1024, int(height)))
            self._list.setIconSize(QSize(w, h))
            self._list.setGridSize(QSize(w + 32, h + 48))
            self._model.set_thumb_size(w, h)
        except Exception as exc:
            _logger.debug("set_thumbnail_size_wh failed: %s", exc)

    def set_thumbnail_size(self, size: int) -> None:
        self.set_thumbnail_size_wh(size, size)

    def set_horizontal_spacing(self, spacing: int) -> None:
        try:
            spacing = max(0, min(64, int(spacing)))
            self._list.setSpacing(spacing)
        except Exception as exc:
            _logger.debug("set_horizontal_spacing failed: %s", exc)

    def get_thumbnail_size(self) -> tuple[int, int]:
        size = self._list.iconSize()
        return size.width(), size.height()

    def get_horizontal_spacing(self) -> int:
        return self._list.spacing()

    # Activation / selection -----------------------------------------------------
    def _on_activated(self, index: QModelIndex) -> None:
        try:
            path = self._model.filePath(index)
            if Path(path).is_file():
                self.image_selected.emit(path)
                _logger.debug("image activated: %s", path)
        except Exception as exc:
            _logger.debug("activation failed: %s", exc)

    def selected_paths(self) -> list[str]:
        try:
            view = self._list if self._view_mode == "thumbnail" else self._tree
            return [
                self._model.filePath(idx)
                for idx in view.selectedIndexes()
                if idx.isValid() and idx.column() == 0
            ]
        except Exception:
            return []

    # File operations ------------------------------------------------------------
    def keyPressEvent(self, event):  # type: ignore[override]
        try:
            if event.matches(QKeySequence.StandardKey.Delete):
                self.delete_selected()
                event.accept()
                return
            if event.matches(QKeySequence.StandardKey.Copy):
                self.copy_selected()
                event.accept()
                return
            if event.matches(QKeySequence.StandardKey.Cut):
                self.cut_selected()
                event.accept()
                return
            if event.matches(QKeySequence.StandardKey.Paste):
                self.paste_into_current()
                event.accept()
                return
            if event.key() == Qt.Key.Key_F2:
                self.rename_first_selected()
                event.accept()
                return
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                idx = (
                    self._list.currentIndex()
                    if self._view_mode == "thumbnail"
                    else self._tree.currentIndex()
                )
                if idx.isValid():
                    self._on_activated(idx)
                    event.accept()
                    return
        except Exception:
            pass
        super().keyPressEvent(event)

    def _show_context_menu(self, pos: QPoint) -> None:
        try:
            menu = QMenu(self)
            menu.addAction("Open", lambda: self._activate_current())
            view_menu = menu.addMenu("View")
            view_menu.addAction(
                "Thumbnails",
                lambda: self.set_view_mode("thumbnail"),
            )
            view_menu.addAction(
                "Details",
                lambda: self.set_view_mode("detail"),
            )
            menu.addSeparator()
            menu.addAction("Copy", self.copy_selected)
            menu.addAction("Cut", self.cut_selected)
            menu.addAction("Paste", self.paste_into_current)
            menu.addAction("Rename", self.rename_first_selected)
            menu.addSeparator()
            menu.addAction("Delete", self.delete_selected)
            menu.exec(self.mapToGlobal(pos))
        except Exception as exc:
            _logger.debug("context menu failed: %s", exc)

    def _activate_current(self) -> None:
        idx = (
            self._list.currentIndex()
            if self._view_mode == "thumbnail"
            else self._tree.currentIndex()
        )
        if idx.isValid():
            self._on_activated(idx)

    def copy_selected(self) -> None:
        paths = self.selected_paths()
        if not paths:
            return
        self._clipboard_paths = paths
        self._clipboard_mode = "copy"
        self._set_clipboard_urls(paths)
        _logger.debug("copy %d paths", len(paths))

    def cut_selected(self) -> None:
        paths = self.selected_paths()
        if not paths:
            return
        self._clipboard_paths = paths
        self._clipboard_mode = "cut"
        self._set_clipboard_urls(paths)
        _logger.debug("cut %d paths", len(paths))

    def paste_into_current(self) -> None:
        if not self._current_folder or not self._clipboard_paths:
            return
        dest_dir = Path(self._current_folder)
        if not dest_dir.is_dir():
            return
        mode = self._clipboard_mode or "copy"
        for src in list(self._clipboard_paths):
            try:
                src_path = Path(src)
                if not src_path.exists():
                    continue
                target = self._unique_dest(dest_dir, src_path.name)
                if mode == "cut":
                    shutil.move(str(src_path), target)
                else:
                    shutil.copy2(str(src_path), target)
            except Exception as exc:
                _logger.warning("paste failed for %s: %s", src, exc)
        if mode == "cut":
            self._clipboard_paths = []
            self._clipboard_mode = None
        _logger.debug("paste complete: %s items -> %s", mode, dest_dir)

    def delete_selected(self) -> None:
        paths = self.selected_paths()
        if not paths:
            return
        confirm = QMessageBox.question(
            self,
            "Delete",
            f"Delete {len(paths)} item(s)?\nThey will be moved to Recycle Bin when possible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for p in paths:
            try:
                self._send_to_recycle_bin(p)
            except Exception as exc:
                _logger.warning("delete failed for %s: %s", p, exc)
        _logger.debug("delete requested for %d items", len(paths))

    def rename_first_selected(self) -> None:
        indexes = (
            self._list.selectedIndexes()
            if self._view_mode == "thumbnail"
            else self._tree.selectionModel().selectedRows()
        )
        if not indexes:
            return
        idx = indexes[0]
        # close editors before switching modes to avoid "editing failed"
        with contextlib.suppress(Exception):
            self.closePersistentEditor(idx)
        self.edit(idx)

    # Clipboard helpers ---------------------------------------------------------
    def _set_clipboard_urls(self, paths: Iterable[str]) -> None:
        mime = QMimeData()
        urls = [Path(p).as_uri() for p in paths]
        mime.setUrls([QUrl(u) for u in urls])
        QGuiApplication.clipboard().setMimeData(mime)

    # View mode ------------------------------------------------------------------
    def set_view_mode(self, mode: str) -> None:
        mode = "thumbnail" if mode not in {"thumbnail", "detail"} else mode
        self._view_mode = mode
        self._model.set_view_mode(mode)
        with contextlib.suppress(Exception):
            for idx in self._list.selectedIndexes():
                self._list.closePersistentEditor(idx)
            for idx in self._tree.selectedIndexes():
                self._tree.closePersistentEditor(idx)
            self.clearFocus()
        if mode == "thumbnail":
            self._stack.setCurrentIndex(0)
        else:
            self._stack.setCurrentIndex(1)
            # ensure columns visible
            with contextlib.suppress(Exception):
                self._tree.setColumnHidden(ImageFileSystemModel.COL_RES, False)
        self.update()

    # Utilities -----------------------------------------------------------------
    def _unique_dest(self, dest_dir: Path, name: str) -> str:
        dest = dest_dir / name
        stem = dest.stem
        suffix = dest.suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem} - Copy ({counter}){suffix}"
            counter += 1
        return str(dest)

    def _send_to_recycle_bin(self, path: str) -> None:
        try:
            FO_DELETE = 3
            FOF_ALLOWUNDO = 0x40
            FOF_NOCONFIRMATION = 0x10

            class SHFILEOPSTRUCT(ctypes.Structure):
                _fields_: ClassVar[list[tuple[str, object]]] = [  # type: ignore[assignment]
                    ("hwnd", wintypes.HWND),
                    ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_ushort),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR),
                ]

            p_from = f"{Path(path)}\0\0"
            op = SHFILEOPSTRUCT()
            op.wFunc = FO_DELETE
            op.pFrom = p_from
            op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION
            res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            if res != 0:
                raise OSError(f"SHFileOperation failed: {res}")
        except Exception:
            Path(path).unlink(missing_ok=True)

    # QWidget overrides ---------------------------------------------------------
    def keyReleaseEvent(self, event):  # type: ignore[override]
        # Let child views handle; nothing extra
        super().keyReleaseEvent(event)

    def focusInEvent(self, event):  # type: ignore[override]
        super().focusInEvent(event)
        if self._view_mode == "thumbnail":
            self._list.setFocus()
        else:
            self._tree.setFocus()


class _ImageOnlyIconProvider(QFileIconProvider):
    """Icon provider that prefers OS icons but falls back to a blank image icon."""

    def __init__(self) -> None:
        super().__init__()
        self._fallback = QIcon()

    def icon(self, file_info):  # type: ignore[override]
        try:
            icn = super().icon(file_info)
            if not icn.isNull():
                return icn
        except Exception:
            pass
        return self._fallback
