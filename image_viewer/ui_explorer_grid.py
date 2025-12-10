"""Explorer grid/detail widget with thumbnail + detail views and disk cache."""

from __future__ import annotations

import contextlib
from pathlib import Path

from PySide6.QtCore import (
    QDir,
    QModelIndex,
    QPoint,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QFontMetrics,
    QIcon,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileIconProvider,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QStackedLayout,
    QToolTip,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from . import explorer_mode_operations
from .busy_cursor import busy_cursor
from .image_engine.fs_model import ImageFileSystemModel
from .logger import get_logger

_logger = get_logger("ui_explorer_grid")


# --------------------------- Icon Provider -----------------------------------
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


# --------------------------- Custom ListView with Better Tooltips ------------
class _ThumbnailListView(QListView):
    """Custom QListView with smooth mouse-following tooltips."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._last_tooltip_index = QModelIndex()
        self._last_tooltip_text = ""
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_pending_tooltip)
        self._pending_tooltip_pos = QPoint()
        self._pending_tooltip_text = ""
        self._current_mouse_pos = QPoint()

    def mouseMoveEvent(self, event):
        """Show tooltip at cursor position when hovering over items."""
        super().mouseMoveEvent(event)
        try:
            self._current_mouse_pos = event.globalPosition().toPoint()
            index = self.indexAt(event.pos())

            if index.isValid():
                tooltip = self.model().data(index, Qt.ToolTipRole)
                if tooltip:
                    tooltip_str = str(tooltip)
                    # If same item, update position immediately for smooth following
                    if index == self._last_tooltip_index and tooltip_str == self._last_tooltip_text:
                        QToolTip.showText(self._current_mouse_pos, tooltip_str, self)
                    # If different item, show with slight delay to avoid flicker
                    elif index != self._last_tooltip_index:
                        self._last_tooltip_index = index
                        self._last_tooltip_text = tooltip_str
                        self._pending_tooltip_pos = self._current_mouse_pos
                        self._pending_tooltip_text = tooltip_str
                        self._tooltip_timer.start(100)  # 100ms delay for new items
            # Mouse left item area
            elif self._last_tooltip_index.isValid():
                self._last_tooltip_index = QModelIndex()
                self._last_tooltip_text = ""
                self._tooltip_timer.stop()
                QToolTip.hideText()
        except Exception:
            pass

    def _show_pending_tooltip(self):
        """Show the pending tooltip after timer expires."""
        try:
            if self._pending_tooltip_text:
                QToolTip.showText(self._pending_tooltip_pos, self._pending_tooltip_text, self)
        except Exception:
            pass

    def leaveEvent(self, event):
        """Hide tooltip when mouse leaves the widget."""
        super().leaveEvent(event)
        try:
            self._tooltip_timer.stop()
            QToolTip.hideText()
            self._last_tooltip_index = QModelIndex()
            self._last_tooltip_text = ""
        except Exception:
            pass


# --------------------------- Main Widget -------------------------------------
class ThumbnailGridWidget(QWidget):
    """Explorer widget with thumbnail view (icons) and detail view (columns)."""

    image_selected = Signal(str)

    def __init__(self, parent=None, model: ImageFileSystemModel | None = None) -> None:
        super().__init__(parent)
        self._current_folder: str | None = None
        self._clipboard_paths: list[str] = []
        self._clipboard_mode: str | None = None  # "copy" | "cut"
        self._context_menu: QMenu | None = None  # Pre-created context menu

        # Use provided model or create new one (for backward compatibility)
        if model is not None:
            self._model = model
        else:
            self._model = ImageFileSystemModel(self)

        # Configure model if not already configured
        if self._model.filter() == QDir.Filter.NoFilter:
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
        self._list = _ThumbnailListView()
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
        # Style will be applied by theme system
        self._list.setObjectName("explorerThumbnailList")

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
        # Style will be applied by theme system
        self._tree.setObjectName("explorerDetailTree")

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

    # Public API -----------------------------------------------------------------
    def load_folder(self, folder_path: str) -> None:
        """Load folder and display thumbnails.

        Note: Thumbnail loading happens asynchronously in background.
        This method only sets up the folder structure.
        """
        try:
            # Check through model, not direct file access
            folder_index = self._model.index(folder_path)
            if not folder_index.isValid() or not self._model.isDir(folder_index):
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
            # Batch load thumbnails from cache
            self._model.batch_load_thumbnails(idx)
        except Exception as exc:
            _logger.error("failed to load_folder %s: %s", folder_path, exc)

    def set_thumbnail_size_wh(self, width: int, height: int) -> None:
        """Set thumbnail size (width and height separately).

        Args:
            width: Thumbnail width in pixels
            height: Thumbnail height in pixels
        """
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
            # Create menu once and reuse
            if self._context_menu is None:
                self._context_menu = QMenu(self)
                self._context_menu.addAction("Open", self._activate_current)
                view_menu = self._context_menu.addMenu("View")
                view_menu.addAction("Thumbnails", lambda: self.set_view_mode("thumbnail"))
                view_menu.addAction("Details", lambda: self.set_view_mode("detail"))
                self._context_menu.addSeparator()
                self._context_menu.addAction("Copy", self.copy_selected)
                self._context_menu.addAction("Cut", self.cut_selected)
                self._context_menu.addAction("Paste", self.paste_into_current)
                self._context_menu.addAction("Rename", self.rename_first_selected)
                self._context_menu.addSeparator()
                self._context_menu.addAction("Delete", self.delete_selected)

            self._context_menu.exec(self.mapToGlobal(pos))
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

        explorer_mode_operations.copy_files_to_clipboard(paths)

        # Update UI state
        self._clipboard_paths = paths
        self._clipboard_mode = "copy"

    def cut_selected(self) -> None:
        paths = self.selected_paths()
        if not paths:
            return

        explorer_mode_operations.cut_files_to_clipboard(paths)

        # Update UI state
        self._clipboard_paths = paths
        self._clipboard_mode = "cut"

    def paste_into_current(self) -> None:
        if not self._current_folder or not self._clipboard_paths:
            return

        success_count, _failed = explorer_mode_operations.paste_files(
            self._current_folder, self._clipboard_paths, self._clipboard_mode or "copy"
        )

        # Update UI state
        if self._clipboard_mode == "cut" and success_count > 0:
            self._clipboard_paths = []
            self._clipboard_mode = None

    def delete_selected(self) -> None:
        paths = self.selected_paths()
        if not paths:
            return

        explorer_mode_operations.delete_files_to_recycle_bin(paths, self)

    def rename_first_selected(self) -> None:
        """Rename the first selected file using a dialog with dynamic width."""
        if self._view_mode == "thumbnail":
            indexes = self._list.selectedIndexes()
        else:
            indexes = self._tree.selectionModel().selectedRows()

        if not indexes:
            return

        idx = indexes[0]
        old_path = self._model.filePath(idx)

        # Check validity through model, not direct file access
        if not old_path or not idx.isValid():
            return

        old_name = Path(old_path).name
        parent_dir = Path(old_path).parent

        # Create custom dialog with dynamic width
        dialog = QDialog(self)
        dialog.setWindowTitle("Rename File")

        layout = QVBoxLayout(dialog)

        # Label
        label = QLabel("New name:")
        layout.addWidget(label)

        # Line edit with current filename
        line_edit = QLineEdit(old_name)
        line_edit.selectAll()  # Select all text for easy replacement

        # Calculate width based on filename length
        font_metrics = QFontMetrics(line_edit.font())
        text_width = font_metrics.horizontalAdvance(old_name)
        # Add padding: 40px for margins, 20px extra space
        dialog_width = max(300, min(600, text_width + 60))
        dialog.setMinimumWidth(dialog_width)

        layout.addWidget(line_edit)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_name = line_edit.text()

        if not new_name or new_name == old_name:
            return

        # Validate filename
        if not new_name.strip():
            QMessageBox.warning(self, "Invalid Name", "Filename cannot be empty.")
            return

        # Check for invalid characters (Windows)
        invalid_chars = '<>:"/\\|?*'
        if any(c in new_name for c in invalid_chars):
            QMessageBox.warning(
                self,
                "Invalid Name",
                f"Filename cannot contain: {invalid_chars}"
            )
            return

        new_path = parent_dir / new_name

        # Check if target already exists
        if new_path.exists():
            QMessageBox.warning(
                self,
                "File Exists",
                f"A file named '{new_name}' already exists."
            )
            return

        # Perform rename
        try:
            Path(old_path).rename(new_path)
            _logger.debug("renamed: %s -> %s", old_path, new_path)

            # Update cache if needed
            if old_path in self._model._thumb_cache:
                icon = self._model._thumb_cache.pop(old_path)
                self._model._thumb_cache[str(new_path)] = icon

            if old_path in self._model._meta:
                meta = self._model._meta.pop(old_path)
                self._model._meta[str(new_path)] = meta

        except Exception as exc:
            _logger.error("rename failed: %s", exc)
            QMessageBox.critical(
                self,
                "Rename Failed",
                f"Failed to rename file:\n{exc}"
            )



    # View mode ------------------------------------------------------------------
    def set_view_mode(self, mode: str) -> None:
        with busy_cursor():
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
