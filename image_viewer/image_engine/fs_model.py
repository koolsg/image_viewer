"""Unified file system model for image viewer.

This module provides ImageFileSystemModel, the single source of truth for
file system operations across all modes (View, Explorer, Trim, Converter).
"""

import contextlib
from pathlib import Path

from PySide6.QtCore import QDateTime, QModelIndex, Qt
from PySide6.QtGui import QIcon, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import QFileSystemModel

from image_viewer.busy_cursor import busy_cursor
from image_viewer.logger import get_logger

from .thumbnail_cache import ThumbnailCache

_logger = get_logger("fs_model")


class ImageFileSystemModel(QFileSystemModel):
    """FS model with loader-backed thumbnail cache and extra Resolution column.

    This is the unified model used by all features:
    - View Mode: file list and navigation
    - Explorer Mode: thumbnail grid and detail view
    - Trim: batch processing file list
    - Converter: current folder detection
    """

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
        self._db_cache: ThumbnailCache | None = None
        self._batch_load_done: bool = False

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

    def batch_load_thumbnails(self, root_index: QModelIndex | None = None) -> None:
        """Pre-load thumbnails for all visible files from cache.

        This method should be called after setRootPath to batch-load
        thumbnails from the database, avoiding individual queries per item.

        Uses busy_cursor context manager to show wait cursor during loading.

        Args:
            root_index: Root index to load from (uses current root if None)
        """
        if self._batch_load_done:
            return

        with busy_cursor():
            try:
                if root_index is None:
                    root_path = self.rootPath()
                    if not root_path:
                        return
                    root_index = self.index(root_path)

                if not root_index.isValid():
                    return

                # Collect all image files with their stats
                paths_with_stats = []
                row_count = self.rowCount(root_index)

                for row in range(row_count):
                    index = self.index(row, 0, root_index)
                    if not index.isValid() or self.isDir(index):
                        continue

                    path = self.filePath(index)
                    if not self._is_image_file(path):
                        continue

                    # Get file stats
                    file_path = Path(path)
                    if not file_path.exists():
                        continue

                    try:
                        stat = file_path.stat()
                        paths_with_stats.append((path, stat.st_mtime, stat.st_size))
                    except Exception:
                        continue

                if not paths_with_stats:
                    self._batch_load_done = True
                    return

                # Ensure DB cache is initialized
                if paths_with_stats:
                    self._ensure_db_cache(paths_with_stats[0][0])

                if not self._db_cache:
                    self._batch_load_done = True
                    return

                # Batch load from database
                results = self._db_cache.get_batch(paths_with_stats, self._thumb_size[0], self._thumb_size[1])

                # Update cache and metadata
                for path, (pixmap, orig_width, orig_height) in results.items():
                    self._thumb_cache[path] = QIcon(pixmap)
                    prev = self._meta.get(path, (None, None, None, None))
                    self._meta[path] = (orig_width, orig_height, prev[2], prev[3])

                # Emit dataChanged for all loaded items
                if results:
                    first_index = self.index(0, 0, root_index)
                    last_index = self.index(row_count - 1, 0, root_index)
                    self.dataChanged.emit(first_index, last_index, [Qt.DecorationRole, Qt.DisplayRole])

                _logger.debug("batch loaded %d thumbnails from cache", len(results))

                # Pre-load resolution info for Detail view
                self._preload_resolution_info(root_index, row_count)

                self._batch_load_done = True
            except Exception as exc:
                _logger.debug("batch_load_thumbnails failed: %s", exc)
                self._batch_load_done = True

    def _preload_resolution_info(self, root_index: QModelIndex, row_count: int) -> None:
        """Pre-load resolution information for all image files.

        This is called after thumbnail loading to prepare data for Detail view.
        Reading image headers is fast and prevents lag when switching to Detail mode.

        Args:
            root_index: Root index of the folder
            row_count: Number of rows to process
        """
        try:
            loaded_count = 0
            for row in range(row_count):
                index = self.index(row, 0, root_index)
                if not index.isValid() or self.isDir(index):
                    continue

                path = self.filePath(index)
                if not self._is_image_file(path):
                    continue

                # Skip if resolution already cached
                w, h, _size, _mtime = self._meta.get(path, (None, None, None, None))
                if w is not None and h is not None:
                    continue

                # Read resolution from image header
                try:
                    reader = QImageReader(path)
                    size = reader.size()
                    if size.isValid():
                        w = int(size.width())
                        h = int(size.height())
                        prev = self._meta.get(path, (None, None, None, None))
                        self._meta[path] = (w, h, prev[2], prev[3])
                        loaded_count += 1
                except Exception:
                    pass

            if loaded_count > 0:
                _logger.debug("preloaded %d resolution info", loaded_count)
        except Exception as exc:
            _logger.debug("_preload_resolution_info failed: %s", exc)

    def set_thumb_size(self, width: int, height: int) -> None:
        self._thumb_size = (width, height)
        # Reset batch load flag when thumbnail size changes
        self._batch_load_done = False

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = mode

    def setRootPath(self, path: str) -> QModelIndex:  # type: ignore[override]
        """Override to reset batch load flag when folder changes."""
        # Reset batch load flag for new folder
        self._batch_load_done = False
        return super().setRootPath(path)

    # --- file list access (for unified model) ------------------------------
    def get_image_files(self) -> list[str]:
        """Get all image files in current folder (sorted).

        Returns:
            List of absolute file paths for image files
        """
        try:
            root_path = self.rootPath()
            if not root_path:
                return []

            root_index = self.index(root_path)
            if not root_index.isValid():
                return []

            files = []
            row_count = self.rowCount(root_index)

            for row in range(row_count):
                index = self.index(row, 0, root_index)
                if not index.isValid():
                    continue

                # Skip directories
                if self.isDir(index):
                    continue

                path = self.filePath(index)
                if self._is_image_file(path):
                    files.append(path)

            return sorted(files)
        except Exception as e:
            _logger.debug("get_image_files failed: %s", e)
            return []

    def get_file_at_index(self, idx: int) -> str | None:
        """Get file path at given index in sorted image file list.

        Args:
            idx: Index in the sorted file list

        Returns:
            File path or None if index out of range
        """
        files = self.get_image_files()
        if 0 <= idx < len(files):
            return files[idx]
        return None

    def get_file_index(self, path: str) -> int:
        """Get index of file path in sorted image file list.

        Args:
            path: Absolute file path

        Returns:
            Index in sorted list, or -1 if not found
        """
        files = self.get_image_files()
        try:
            return files.index(path)
        except ValueError:
            return -1

    def get_file_count(self) -> int:
        """Get count of image files in current folder.

        Returns:
            Number of image files
        """
        return len(self.get_image_files())

    def get_current_folder(self) -> str:
        """Get current root folder path.

        Returns:
            Absolute folder path or empty string
        """
        return self.rootPath()

    def _is_image_file(self, path: str) -> bool:
        """Check if file is an image based on extension.

        Args:
            path: File path to check

        Returns:
            True if file has image extension
        """
        try:
            lower = path.lower()
            return lower.endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"))
        except Exception:
            return False

    # --- columns -----------------------------------------------------------
    def columnCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        parent = parent or QModelIndex()
        return super().columnCount(parent) + 1  # add Resolution column

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # type: ignore[override]
        try:
            base_cols = super().columnCount()
            if orientation == Qt.Horizontal and role == Qt.DisplayRole and section == base_cols:
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

            # Early return for roles that don't need file info
            if role not in (Qt.DisplayRole, Qt.ToolTipRole, Qt.DecorationRole, Qt.TextAlignmentRole):
                return super().data(index, role)

            path = self.filePath(index)

            # Resolution column
            if col == base_cols:
                if role in (Qt.DisplayRole, Qt.ToolTipRole):
                    return self._resolution_str(index)
                if role == Qt.DecorationRole:
                    return None
            if col > base_cols:
                return None

            # Type column -> extension only (no file access needed)
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

            # Text alignment per column
            if role == Qt.TextAlignmentRole:
                # Name column: left aligned
                if col == self.COL_NAME:
                    return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                # Size and Resolution: right aligned
                if col in (self.COL_SIZE, base_cols):
                    return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                # Others (Type, Modified): center aligned
                return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter

            # Decoration for thumbnails
            if role == Qt.DecorationRole and self._view_mode == "thumbnail" and col == self.COL_NAME:
                if icon := self._thumb_cache.get(path):
                    return icon
                self._request_thumbnail(path)

            # Tooltip for thumbnails
            if role == Qt.ToolTipRole and self._view_mode == "thumbnail" and col == self.COL_NAME:
                return self._build_tooltip(path)

            return super().data(index, role)
        except Exception as exc:
            _logger.debug("data() failed: %s", exc)
            return super().data(index, role)

    def _resolution_str(self, index: QModelIndex) -> str:
        path = self.filePath(index)
        try:
            # Check cache first (already preloaded)
            w, h, _size_bytes, _mtime = self._meta.get(path, (None, None, None, None))

            # Only read if not cached (new files)
            if w is None or h is None:
                reader = QImageReader(path)
                size = reader.size()
                if size.isValid():
                    w = int(size.width())
                    h = int(size.height())
                    # Update cache with resolution only
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
            # Use cached metadata (already preloaded)
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
        return " · ".join(parts)

    def _build_tooltip(self, path: str) -> str:
        """Build tooltip with file metadata."""
        try:
            filename = Path(path).name
            # Use cached metadata (already preloaded)
            w, h, size_bytes, mtime = self._meta.get(path, (None, None, None, None))

            # Get resolution from cache or read header (new files only)
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

        # Don't start busy cursor here - it's managed by batch_load_thumbnails
        # Individual thumbnail requests happen during scrolling, not initial load
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
            thumb_height, thumb_width, _ = image_data.shape
            bytes_per_line = 3 * thumb_width
            q_image = QImage(image_data.data, thumb_width, thumb_height, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_image)
            if pixmap.isNull():
                # Check if all thumbnails are done
                self._check_thumbnail_completion()
                return
            scaled = pixmap.scaled(
                self._thumb_size[0],
                self._thumb_size[1],
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._thumb_cache[path] = QIcon(scaled)

            # Read original image resolution (not thumbnail size)
            prev = self._meta.get(path, (None, None, None, None))
            orig_width = prev[0]
            orig_height = prev[1]
            with contextlib.suppress(Exception):
                reader = QImageReader(path)
                size = reader.size()
                if size.isValid():
                    orig_width = int(size.width())
                    orig_height = int(size.height())

            self._meta[path] = (orig_width, orig_height, prev[2], prev[3])
            self._save_disk_icon(path, scaled, orig_width, orig_height)
            idx = self.index(path)
            if idx.isValid():
                self.dataChanged.emit(idx, idx, [Qt.DecorationRole, Qt.DisplayRole])
        except Exception as exc:
            _logger.debug("thumbnail_ready failed: %s", exc)

    def _ensure_db_cache(self, path: str) -> None:
        """Ensure database cache is initialized for the given path's directory."""
        if self._db_cache is None:
            cache_dir = Path(path).parent
            self._db_cache = ThumbnailCache(cache_dir, "SwiftView_thumbs.db")

    def _load_disk_icon(self, path: str) -> QIcon | None:
        """Load thumbnail from SQLite cache."""
        try:
            self._ensure_db_cache(path)
            if not self._db_cache:
                return None

            # Get file stats
            file_path = Path(path)
            if not file_path.exists():
                return None
            stat = file_path.stat()
            mtime = stat.st_mtime
            size = stat.st_size

            # Try to load from cache
            result = self._db_cache.get(path, mtime, size, self._thumb_size[0], self._thumb_size[1])
            if result is None:
                return None

            pixmap, orig_width, orig_height = result

            # Update metadata
            prev = self._meta.get(path, (None, None, None, None))
            self._meta[path] = (orig_width, orig_height, prev[2], prev[3])

            return QIcon(pixmap)
        except Exception as exc:
            _logger.debug("failed to load thumbnail from cache: %s", exc)
            return None

    def _save_disk_icon(self, path: str, pixmap: QPixmap, orig_width: int | None, orig_height: int | None) -> None:
        """Save thumbnail to SQLite cache."""
        try:
            self._ensure_db_cache(path)
            if not self._db_cache:
                return

            # Get file stats
            file_path = Path(path)
            if not file_path.exists():
                return
            stat = file_path.stat()
            mtime = stat.st_mtime
            size = stat.st_size

            # Save to cache
            self._db_cache.set(
                path,
                mtime,
                size,
                orig_width,
                orig_height,
                self._thumb_size[0],
                self._thumb_size[1],
                pixmap,
            )
        except Exception as exc:
            _logger.debug("failed to save thumbnail to cache: %s", exc)
