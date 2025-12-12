"""Unified file system model for image viewer.

This module provides ImageFileSystemModel, the single source of truth for
file system operations across all modes (View, Explorer, Trim, Converter).
"""

import contextlib
import sqlite3
from pathlib import Path

from PySide6.QtCore import QDateTime, QModelIndex, QObject, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QFileSystemModel

from image_viewer.logger import get_logger

from .decoder import get_image_dimensions
from .thumbnail_cache import ThumbnailCache

_logger = get_logger("fs_model")


class _ThumbDbLoadWorker(QObject):
    """Loads cached thumbnails/metadata from SQLite without touching Qt GUI objects."""

    chunk_ready = Signal(list)  # list[(path, thumbnail_bytes|None, width|None, height|None, mtime, size)]
    missing_ready = Signal(list)  # list[path] that have no cached thumbnail
    finished = Signal(int)  # generation

    def __init__(  # noqa: PLR0913
        self,
        folder_path: str,
        db_path: Path,
        thumb_width: int,
        thumb_height: int,
        generation: int,
        prefetch_limit: int = 48,
    ) -> None:
        super().__init__()
        self._folder_path = folder_path
        self._db_path = db_path
        self._thumb_width = thumb_width
        self._thumb_height = thumb_height
        self._generation = generation
        self._prefetch_limit = prefetch_limit
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    def run(self) -> None:  # noqa: PLR0912
        try:
            folder = Path(self._folder_path)
            if not folder.is_dir():
                self.finished.emit(self._generation)
                return

            # Scan folder in the worker thread (no Qt model access).
            paths_with_stats: list[tuple[str, float, int]] = []
            for p in folder.iterdir():
                if self._abort:
                    self.finished.emit(self._generation)
                    return
                if not p.is_file():
                    continue
                lower = p.name.lower()
                if not lower.endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff")):
                    continue
                try:
                    stat = p.stat()
                    paths_with_stats.append((str(p), float(stat.st_mtime), int(stat.st_size)))
                except Exception:
                    continue

            if not paths_with_stats or not self._db_path.exists():
                # Nothing cached yet; ask UI to prefetch some thumbnails.
                self.missing_ready.emit([p for (p, _m, _s) in paths_with_stats[: self._prefetch_limit]])
                self.finished.emit(self._generation)
                return

            # SQLite has a max bound-parameter count (commonly 999). Each row uses 3 params.
            chunk_size = 300
            have_thumb: set[str] = set()

            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            try:
                for i in range(0, len(paths_with_stats), chunk_size):
                    if self._abort:
                        self.finished.emit(self._generation)
                        return

                    chunk = paths_with_stats[i : i + chunk_size]
                    placeholders = ",".join(["(?, ?, ?)"] * len(chunk))
                    query = f"""
                        SELECT path, thumbnail, width, height, mtime, size
                        FROM thumbnails
                        WHERE thumb_width = ? AND thumb_height = ?
                          AND (path, mtime, size) IN ({placeholders})
                    """
                    params: list[object] = [self._thumb_width, self._thumb_height]
                    for path, mtime, size in chunk:
                        params.extend([path, mtime, size])

                    rows = conn.execute(query, params).fetchall()
                    if rows:
                        self.chunk_ready.emit(rows)
                        for path, thumbnail_data, _w, _h, _mtime, _size in rows:
                            if thumbnail_data is not None:
                                have_thumb.add(path)
            finally:
                with contextlib.suppress(Exception):
                    conn.close()

            # Trigger initial thumbnail generation for a small number of misses.
            missing = [p for (p, _m, _s) in paths_with_stats if p not in have_thumb]
            if missing:
                self.missing_ready.emit(missing[: self._prefetch_limit])

            self.finished.emit(self._generation)
        except Exception:
            self.finished.emit(self._generation)


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
        self._pending_removed_paths: list[str] = []
        self._thumb_db_thread: QThread | None = None
        self._thumb_db_worker: _ThumbDbLoadWorker | None = None
        self._thumb_load_generation: int = 0
        self._watcher_ready: bool = False
        self._internal_data_changed: bool = False

        # QFileSystemModel already uses OS watchers internally; hook its model signals
        # to keep DB + in-memory caches + UI consistent when files change.
        self.rowsInserted.connect(self._on_rows_inserted)
        self.rowsAboutToBeRemoved.connect(self._on_rows_about_to_be_removed)
        self.rowsRemoved.connect(self._on_rows_removed)
        self.dataChanged.connect(self._on_model_data_changed)
        with contextlib.suppress(Exception):
            self.fileRenamed.connect(self._on_file_renamed)

    # --- loader wiring -----------------------------------------------------
    def set_loader(self, loader) -> None:
        try:
            if self._loader and hasattr(self._loader, "image_decoded"):
                with contextlib.suppress(Exception):
                    self._loader.image_decoded.disconnect(self._on_thumbnail_ready)
            self._loader = loader
            if self._loader and hasattr(self._loader, "image_decoded"):
                _logger.debug(
                    "set_loader: connecting loader image_decoded -> _on_thumbnail_ready: loader=%s", self._loader
                )
                self._loader.image_decoded.connect(self._on_thumbnail_ready)
            else:
                _logger.debug("set_loader: loader is None or lacks signal: %s", self._loader)
        except Exception as exc:
            _logger.debug("set_loader failed: %s", exc)

    def batch_load_thumbnails(self, root_index: QModelIndex | None = None) -> None:
        """Start background loading of cached thumbnails/metadata.

        Must be called after setRootPath. This version is asynchronous to avoid
        blocking the UI thread on directory scanning + SQLite reads.
        """
        if self._batch_load_done:
            return

        root_path = self.rootPath()
        if not root_path:
            return

        self._watcher_ready = True
        self._batch_load_done = True
        self._start_thumb_db_loader(root_path)

    def _start_thumb_db_loader(self, folder_path: str) -> None:
        # Stop any previous worker
        self._stop_thumb_db_loader()

        self._thumb_load_generation += 1
        generation = self._thumb_load_generation

        db_path = Path(folder_path) / "SwiftView_thumbs.db"
        worker = _ThumbDbLoadWorker(
            folder_path,
            db_path,
            self._thumb_size[0],
            self._thumb_size[1],
            generation,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.chunk_ready.connect(self._on_thumb_db_chunk)
        worker.missing_ready.connect(self._on_thumb_db_missing)
        worker.finished.connect(self._on_thumb_db_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._thumb_db_thread = thread
        self._thumb_db_worker = worker
        thread.start()

    def _stop_thumb_db_loader(self) -> None:
        try:
            if self._thumb_db_worker is not None:
                with contextlib.suppress(Exception):
                    self._thumb_db_worker.abort()
            if self._thumb_db_thread is not None:
                with contextlib.suppress(Exception):
                    self._thumb_db_thread.quit()
                    self._thumb_db_thread.wait(250)
        finally:
            self._thumb_db_thread = None
            self._thumb_db_worker = None

    def _on_thumb_db_chunk(self, rows: list) -> None:
        # Runs on the main thread.
        for row in rows:
            try:
                path, thumbnail_data, orig_width, orig_height, mtime, size = row

                # Update metadata first
                self._meta[str(path)] = (
                    orig_width,
                    orig_height,
                    int(size) if size is not None else None,
                    float(mtime) if mtime is not None else None,
                )

                # Materialize thumbnail into QPixmap/QIcon only on the GUI thread.
                if thumbnail_data is not None:
                    pixmap = QPixmap()
                    if pixmap.loadFromData(thumbnail_data):
                        self._thumb_cache[str(path)] = QIcon(pixmap)

                idx = self.index(str(path))
                if idx.isValid():
                    self._internal_data_changed = True
                    try:
                        self.dataChanged.emit(idx, idx, [Qt.DecorationRole, Qt.DisplayRole])
                    finally:
                        self._internal_data_changed = False
            except Exception:
                continue

    def _on_thumb_db_missing(self, paths: list[str]) -> None:
        # Trigger background thumbnail generation (decode happens off the UI thread).
        for path in paths:
            with contextlib.suppress(Exception):
                self._request_thumbnail(path)

    def _on_thumb_db_finished(self, generation: int) -> None:
        # Ignore stale worker completion.
        if generation != self._thumb_load_generation:
            return
        _logger.debug("thumb db loader finished: gen=%d", generation)

    def _preload_resolution_info(self, root_index: QModelIndex, row_count: int) -> None:  # noqa: PLR0912, PLR0915
        """Pre-load resolution information for all image files.

        This is called after thumbnail loading to prepare data for Detail view.
        First checks thumbnail DB for cached resolution, then reads headers for new files.

        Args:
            root_index: Root index of the folder
            row_count: Number of rows to process
        """
        try:
            # Collect files that need resolution info
            files_to_check = []
            for row in range(row_count):
                index = self.index(row, 0, root_index)
                if not index.isValid() or self.isDir(index):
                    continue

                path = self.filePath(index)
                if not self._is_image_file(path):
                    continue

                # Skip if resolution already in memory cache
                w, h, _size, _mtime = self._meta.get(path, (None, None, None, None))
                if w is not None and h is not None:
                    continue

                files_to_check.append(path)

            if not files_to_check:
                return

            # Check thumbnail DB for resolution info
            if self._db_cache:
                db_loaded = 0
                stats: list[tuple[str, float, int]] = []
                for path in files_to_check:
                    try:
                        file_path = Path(path)
                        if not file_path.exists():
                            continue
                        stat = file_path.stat()
                        stats.append((path, stat.st_mtime, stat.st_size))
                    except Exception:
                        continue

                if stats:
                    meta_map = self._db_cache.get_meta_batch(stats)
                    for path, (orig_width, orig_height) in meta_map.items():
                        if orig_width and orig_height:
                            prev = self._meta.get(path, (None, None, None, None))
                            self._meta[path] = (orig_width, orig_height, prev[2], prev[3])
                            with contextlib.suppress(ValueError):
                                files_to_check.remove(path)
                            db_loaded += 1

                if db_loaded > 0:
                    _logger.debug("loaded %d resolution from DB", db_loaded)

            # Read headers for remaining files using libvips (faster than QImageReader)
            header_loaded = 0
            for path in files_to_check:
                try:
                    w, h = get_image_dimensions(path)
                    if w is not None and h is not None:
                        prev = self._meta.get(path, (None, None, None, None))
                        self._meta[path] = (w, h, prev[2], prev[3])
                        header_loaded += 1

                        # Save resolution to DB for future use (without thumbnail)
                        try:
                            self._ensure_db_cache(path)
                            if self._db_cache:
                                file_path = Path(path)
                                if file_path.exists():
                                    stat = file_path.stat()
                                    self._db_cache.set_meta(
                                        path,
                                        stat.st_mtime,
                                        stat.st_size,
                                        w,
                                        h,
                                        self._thumb_size[0],
                                        self._thumb_size[1],
                                    )
                        except Exception:
                            pass  # Don't fail if DB save fails
                except Exception:
                    pass

            if header_loaded > 0:
                _logger.debug("loaded %d resolution from headers", header_loaded)

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
        self._watcher_ready = False
        self._stop_thumb_db_loader()
        self._thumb_cache.clear()
        self._thumb_pending.clear()
        self._meta.clear()
        self._pending_removed_paths.clear()
        return super().setRootPath(path)

    # --- QFileSystemModel watcher integration -----------------------------
    def _on_rows_inserted(self, parent: QModelIndex, start: int, end: int) -> None:
        # Ignore initial model population; batch_load_thumbnails will handle initial load.
        if not self._watcher_ready:
            return

        for row in range(start, end + 1):
            try:
                idx = self.index(row, 0, parent)
                if not idx.isValid() or self.isDir(idx):
                    continue
                path = self.filePath(idx)
                if not self._is_image_file(path):
                    continue

                file_path = Path(path)
                if not file_path.exists():
                    continue
                stat = file_path.stat()

                w, h = (None, None)
                with contextlib.suppress(Exception):
                    w, h = get_image_dimensions(path)

                self._meta[path] = (w, h, int(stat.st_size), float(stat.st_mtime))
                self._thumb_cache.pop(path, None)
                self._thumb_pending.discard(path)

                try:
                    self._ensure_db_cache(path)
                    if self._db_cache:
                        self._db_cache.set_meta(
                            path,
                            stat.st_mtime,
                            stat.st_size,
                            w,
                            h,
                            self._thumb_size[0],
                            self._thumb_size[1],
                        )
                except Exception:
                    pass

                # Proactively generate thumbnail for new image.
                self._request_thumbnail(path)
            except Exception:
                continue

    def _on_rows_about_to_be_removed(self, parent: QModelIndex, start: int, end: int) -> None:
        if not self._watcher_ready:
            return

        # Collect paths before the model removes them.
        for row in range(start, end + 1):
            try:
                idx = self.index(row, 0, parent)
                if not idx.isValid() or self.isDir(idx):
                    continue
                path = self.filePath(idx)
                if path:
                    self._pending_removed_paths.append(path)
            except Exception:
                continue

    def _on_rows_removed(self, parent: QModelIndex, start: int, end: int) -> None:
        if not self._watcher_ready:
            self._pending_removed_paths.clear()
            return

        # Delete DB rows and in-memory caches for removed files.
        for path in self._pending_removed_paths:
            try:
                self._thumb_cache.pop(path, None)
                self._thumb_pending.discard(path)
                self._meta.pop(path, None)

                # Delete from cache DB (safe even if already missing)
                self._ensure_db_cache(path)
                if self._db_cache:
                    self._db_cache.delete(path)
            except Exception:
                continue
        self._pending_removed_paths.clear()

    def _on_model_data_changed(self, top_left: QModelIndex, bottom_right: QModelIndex, roles=None) -> None:
        # Ignore initial model population.
        if not self._watcher_ready:
            return

        # Ignore our own UI refresh emits.
        if self._internal_data_changed:
            return

        parent = top_left.parent()
        for row in range(top_left.row(), bottom_right.row() + 1):
            try:
                idx = self.index(row, 0, parent)
                if not idx.isValid() or self.isDir(idx):
                    continue
                path = self.filePath(idx)
                if not self._is_image_file(path):
                    continue

                file_path = Path(path)
                if not file_path.exists():
                    continue
                stat = file_path.stat()

                _prev_w, _prev_h, prev_size, prev_mtime = self._meta.get(path, (None, None, None, None))
                if prev_size == int(stat.st_size) and prev_mtime == float(stat.st_mtime):
                    continue

                # File changed: keep DB + memory consistent, then regenerate thumbnail.
                w, h = (None, None)
                with contextlib.suppress(Exception):
                    w, h = get_image_dimensions(path)

                self._meta[path] = (w, h, int(stat.st_size), float(stat.st_mtime))
                self._thumb_cache.pop(path, None)
                self._thumb_pending.discard(path)

                try:
                    self._ensure_db_cache(path)
                    if self._db_cache:
                        # This also clears any existing thumbnail blob (meta-only until re-decoded).
                        self._db_cache.set_meta(
                            path,
                            stat.st_mtime,
                            stat.st_size,
                            w,
                            h,
                            self._thumb_size[0],
                            self._thumb_size[1],
                        )
                except Exception:
                    pass

                self._request_thumbnail(path)
            except Exception:
                continue

    def _on_file_renamed(self, directory: str, old_name: str, new_name: str) -> None:
        if not self._watcher_ready:
            return

        try:
            old_path = str(Path(directory) / old_name)
            new_path = str(Path(directory) / new_name)

            # Drop old entry and treat new one as inserted.
            self._thumb_cache.pop(old_path, None)
            self._thumb_pending.discard(old_path)
            self._meta.pop(old_path, None)
            self._ensure_db_cache(old_path)
            if self._db_cache:
                self._db_cache.delete(old_path)

            file_path = Path(new_path)
            if not file_path.exists() or not self._is_image_file(new_path):
                return
            stat = file_path.stat()
            w, h = (None, None)
            with contextlib.suppress(Exception):
                w, h = get_image_dimensions(new_path)
            self._meta[new_path] = (w, h, int(stat.st_size), float(stat.st_mtime))
            self._ensure_db_cache(new_path)
            if self._db_cache:
                self._db_cache.set_meta(
                    new_path,
                    stat.st_mtime,
                    stat.st_size,
                    w,
                    h,
                    self._thumb_size[0],
                    self._thumb_size[1],
                )
            self._request_thumbnail(new_path)
        except Exception:
            return

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

    def data(self, index: QModelIndex, role: int):  # type: ignore[override]  # noqa: PLR0911, PLR0912, PLR0915
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
                    # Avoid serving stale thumbnails if the file changed.
                    try:
                        file_path = Path(path)
                        if file_path.exists():
                            stat = file_path.stat()
                            _w, _h, cached_size, cached_mtime = self._meta.get(path, (None, None, None, None))
                            if (
                                cached_size is not None
                                and cached_mtime is not None
                                and (
                                    int(cached_size) != int(stat.st_size) or float(cached_mtime) != float(stat.st_mtime)
                                )
                            ):
                                self._thumb_cache.pop(path, None)
                                self._thumb_pending.discard(path)
                                self._meta[path] = (None, None, int(stat.st_size), float(stat.st_mtime))
                                try:
                                    self._ensure_db_cache(path)
                                    if self._db_cache:
                                        self._db_cache.set_meta(
                                            path,
                                            stat.st_mtime,
                                            stat.st_size,
                                            None,
                                            None,
                                            self._thumb_size[0],
                                            self._thumb_size[1],
                                        )
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    # Cached icon still valid; return it (no per-file debug to avoid noise)
                    if path in self._thumb_cache:
                        return icon
                # Cache miss; request thumbnail (no per-file debug to reduce verbosity)
                self._request_thumbnail(path)
                # Return OS-provided icon as a fallback so the item shows something.
                # Scale to requested thumbnail size to ensure display in large icon grids.
                try:
                    super_icon = super().data(index, role)
                    if super_icon:
                        try:
                            # If it's a QIcon, get a pixmap for the size and return scaled
                            if isinstance(super_icon, QIcon):
                                pix = super_icon.pixmap(self._thumb_size[0], self._thumb_size[1])
                                if not pix.isNull():
                                    scaled = pix.scaled(
                                        self._thumb_size[0],
                                        self._thumb_size[1],
                                        Qt.KeepAspectRatio,
                                        Qt.SmoothTransformation,
                                    )
                                    # Using scaled OS icon as fallback
                                    return QIcon(scaled)
                            # If it's a QPixmap, scale and return as QIcon
                            if isinstance(super_icon, QPixmap) and not super_icon.isNull():
                                scaled = super_icon.scaled(
                                    self._thumb_size[0],
                                    self._thumb_size[1],
                                    Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation,
                                )
                                # Using scaled OS pixmap as fallback
                                return QIcon(scaled)
                        except Exception:
                            return super_icon
                except Exception:
                    pass

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
            # Use only cached metadata (should be preloaded by batch_load_thumbnails)
            w, h, _size_bytes, _mtime = self._meta.get(path, (None, None, None, None))

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
            # Use only cached metadata (should be preloaded by batch loading)
            w, h, size_bytes, mtime = self._meta.get(path, (None, None, None, None))

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
            return f"{size / mb:.1f} MB"
        if size >= kb:
            return f"{size / kb:.1f} KB"
        return f"{size} B"

    # --- thumbnail load/save ------------------------------------------------
    def _request_thumbnail(self, path: str) -> None:
        # Skip if not a file (e.g., directory)
        if not Path(path).is_file():
            return
        # Skip if not an image (don't attempt to decode non-image files)
        if not self._is_image_file(path):
            return
        if path in self._thumb_cache:
            return
        icon = self._load_disk_icon(path)
        if icon is not None and not icon.isNull():
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
        _logger.debug("_request_thumbnail: queued thumbnail for %s (pending=%d)", path, len(self._thumb_pending))
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
            # If this is not an image file, ignore background decode results silently
            if not self._is_image_file(path):
                return
            if error or image_data is None:
                _logger.debug("_on_thumbnail_ready: error for %s: %s", path, error)
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
            sw = scaled.width()
            sh = scaled.height()
            _logger.debug("_on_thumbnail_ready: thumbnail cached for %s pixmap_size=%dx%d", path, sw, sh)

            # Read original image resolution (not thumbnail size)
            prev = self._meta.get(path, (None, None, None, None))
            orig_width = prev[0]
            orig_height = prev[1]

            # Only read header if resolution not already cached
            if orig_width is None or orig_height is None:
                with contextlib.suppress(Exception):
                    w, h = get_image_dimensions(path)
                    if w is not None and h is not None:
                        orig_width = w
                        orig_height = h

            self._meta[path] = (orig_width, orig_height, prev[2], prev[3])
            self._save_disk_icon(path, scaled, orig_width, orig_height)
            idx = self.index(path)
            if idx.isValid():
                _logger.debug("_on_thumbnail_ready: emitting dataChanged for %s at index valid", path)
                self.dataChanged.emit(idx, idx, [Qt.DecorationRole, Qt.DisplayRole])
            else:
                _logger.debug(
                    "_on_thumbnail_ready: index invalid for %s; emitting dataChanged for current root range", path
                )
                try:
                    root = self.rootPath()
                    root_idx = self.index(root)
                    first = self.index(0, 0, root_idx)
                    last = self.index(self.rowCount(root_idx) - 1, 0, root_idx)
                    self.dataChanged.emit(first, last, [Qt.DecorationRole, Qt.DisplayRole])
                except Exception:
                    pass
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
            if pixmap is None or pixmap.isNull():
                _logger.debug("_load_disk_icon: cached pixmap is null for %s", path)
                return None

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

            # Keep in-memory meta consistent with what we just persisted.
            self._meta[path] = (orig_width, orig_height, int(size), float(mtime))
        except Exception as exc:
            _logger.debug("failed to save thumbnail to cache: %s", exc)
