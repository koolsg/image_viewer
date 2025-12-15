"""Unified file system model for image viewer.

This module provides ImageFileSystemModel, the single source of truth for
file system operations across all modes (View, Explorer, Trim, Converter).

Responsibility boundary: UI components do not perform file or DB writes directly.
When the user requests file or cache operations via the UI, those requests are
handled by `ImageFileSystemModel` and the image engine (e.g., `ThumbnailCache`,
`FSDBLoadWorker`, `ThumbDB`). Thumbnail reads/generation and file updates are
performed by the image engine; the UI issues commands and displays results only.
"""

import contextlib
from pathlib import Path

from PySide6.QtCore import QDateTime, QModelIndex, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QFileSystemModel

from image_viewer.logger import get_logger

from .db.thumbdb_bytes_adapter import ThumbDBBytesAdapter
from .decoder import get_image_dimensions
from .fs_db_worker import FSDBLoadWorker
from .fs_model_disk import init_thumbnail_cache_for_path, load_thumbnail_from_cache, save_thumbnail_to_cache
from .meta_utils import to_mtime_ms_from_stat as _to_mtime_ms_from_stat

_logger = get_logger("fs_model")

_EPOCH_MS_THRESHOLD = 10**11


class ImageFileSystemModel(QFileSystemModel):
    progress = Signal(int, int)

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
        self._db_loader_factory = None
        self._thumb_size: tuple[int, int] = (256, 195)
        self._view_mode: str = "thumbnail"
        self._meta: dict[str, tuple[int | None, int | None, int | None, int | None]] = {}
        self._db_cache: ThumbDBBytesAdapter | None = None
        self._batch_load_done: bool = False
        self._pending_removed_paths: list[str] = []
        self._thumb_db_thread: QThread | None = None
        self._thumb_db_worker: FSDBLoadWorker | None = None
        self._thumb_load_generation: int = 0
        self._watcher_ready: bool = False
        # If set, force thumbnail DB location to this directory (absolute Path)
        self._explicit_cache_dir: Path | None = None
        self._db_read_use_operator: bool = True
        self._internal_data_changed: bool = False
        self._decode_reason_logs_left: int = 0

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

    def set_db_loader_factory(self, factory) -> None:
        """Inject a DB loader factory. The factory will be called with keyword args:
        folder_path, db_path, thumb_width, thumb_height, generation
        The returned object must be a QObject with signals and a `run()` method.
        If None, legacy inline worker is used.
        """
        self._db_loader_factory = factory

    def set_db_read_strategy(self, use_operator_for_reads: bool) -> None:
        """Configure whether DB reads should be routed via DbOperator (serialized).

        Default is False (direct reads). Pass True to force operator-mediated reads.
        """
        self._db_read_use_operator = bool(use_operator_for_reads)

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

        # QFileSystemModel may emit rowsInserted/dataChanged while initially populating.
        # Don't treat those as file modifications; enable watcher handling after DB load.
        self._watcher_ready = False
        self._batch_load_done = True
        self._start_thumb_db_loader(root_path)

    def _start_thumb_db_loader(self, folder_path: str) -> None:
        # Stop any previous worker
        self._stop_thumb_db_loader()

        self._thumb_load_generation += 1
        generation = self._thumb_load_generation

        db_path = Path(folder_path) / "SwiftView_thumbs.db"
        # Ensure a ThumbnailCache exists so we can pass operator instance into worker
        with contextlib.suppress(Exception):
            self._ensure_db_cache(folder_path)
        # If a custom DB loader factory was injected, use it. The factory must
        # return a QObject-like worker with signals: chunk_loaded/missing_paths/finished/error
        # and a `run()` method. Otherwise fall back to legacy inline worker.
        if self._db_loader_factory:
            try:
                worker = self._db_loader_factory(
                    folder_path=folder_path,
                    db_path=db_path,
                    thumb_width=self._thumb_size[0],
                    thumb_height=self._thumb_size[1],
                    generation=generation,
                )
            except Exception as exc:
                _logger.debug("db_loader_factory raised: %s", exc)
                worker = None

            if worker is not None:
                thread = QThread(self)
                worker.moveToThread(thread)
                thread.started.connect(worker.run)
                # New loader signals (dict payloads)
                with contextlib.suppress(Exception):
                    worker.chunk_loaded.connect(self._on_thumb_db_chunk)
                with contextlib.suppress(Exception):
                    worker.missing_paths.connect(self._on_thumb_db_missing)
                with contextlib.suppress(Exception):
                    worker.finished.connect(self._on_thumb_db_finished)
                with contextlib.suppress(Exception):
                    worker.error.connect(self._on_thumb_db_error)
                with contextlib.suppress(Exception):
                    worker.progress.connect(self._on_thumb_db_progress)

                # Ensure thread cleanup
                with contextlib.suppress(Exception):
                    worker.finished.connect(thread.quit)
                    worker.finished.connect(worker.deleteLater)
                    thread.finished.connect(thread.deleteLater)

                self._thumb_db_thread = thread
                self._thumb_db_worker = worker
                thread.start()
                return

        # Default worker: use FSDBLoadWorker implementation
        worker = FSDBLoadWorker(
            folder_path=folder_path,
            db_path=str(db_path),
            db_operator=(self._db_cache._db_operator if self._db_cache else None),
            use_operator_for_reads=self._db_read_use_operator,
            thumb_width=self._thumb_size[0],
            thumb_height=self._thumb_size[1],
            generation=generation,
            prefetch_limit=48,
            chunk_size=800,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.chunk_loaded.connect(self._on_thumb_db_chunk)
        worker.missing_paths.connect(self._on_thumb_db_missing)
        worker.finished.connect(self._on_thumb_db_finished)
        with contextlib.suppress(Exception):
            worker.progress.connect(self._on_thumb_db_progress)
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
                    self._thumb_db_worker.stop()
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
                # Support both legacy tuple rows and new dict payloads from injected worker.
                if isinstance(row, dict):
                    path = row.get("path")
                    thumbnail_data = row.get("thumbnail")
                    orig_width = row.get("width")
                    orig_height = row.get("height")
                    mtime = row.get("mtime")
                    size = row.get("size")
                else:
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

    def _on_thumb_db_error(self, info: dict) -> None:
        with contextlib.suppress(Exception):
            _logger.debug("thumb db worker error: %s", info)

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
        self._watcher_ready = True

    def _on_thumb_db_progress(self, processed: int, total: int) -> None:
        # Forward worker progress to interested UI consumers
        try:
            self.progress.emit(int(processed), int(total))
        except Exception:
            return

    def set_thumb_size(self, width: int, height: int) -> None:
        self._thumb_size = (width, height)
        # Reset batch load flag when thumbnail size changes
        self._batch_load_done = False

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = mode

    def setRootPath(self, path: str) -> QModelIndex:  # type: ignore[override]
        """Override to reset batch load flag when folder changes."""
        original_path = path
        p: Path | None = None
        # Normalize the incoming path to an absolute directory path. If a file
        # path is provided, use its parent directory.
        try:
            p = Path(path)
            try:
                p = p.resolve()
            except Exception:
                p = p.absolute()
            if not p.is_dir():
                p = p.parent
            path = str(p)
        except Exception:
            # If normalization fails, fall back to the original string
            p = None
            path = original_path

        # If a DB cache is already initialized (possibly for a different
        # folder), rebind it to the new root folder so we don't keep using a
        # workspace-root DB when the user opens a folder.
        if p is not None:
            existing_db = getattr(self, "_db_cache", None)
            if existing_db is not None:
                with contextlib.suppress(Exception):
                    if existing_db.db_path.parent != p:
                        with contextlib.suppress(Exception):
                            existing_db.close()
                        self._db_cache = None

        # Record explicit cache directory (absolute resolved folder) so that
        # subsequent calls to _ensure_db_cache will prefer this location.
        self._explicit_cache_dir = p
        with contextlib.suppress(Exception):
            _logger.debug("setRootPath: explicit_cache_dir set to %s", self._explicit_cache_dir)

        # Reset batch load flag for new folder
        self._batch_load_done = False
        self._watcher_ready = False
        # Allow a small number of decode-reason logs per folder open.
        self._decode_reason_logs_left = 25
        self._stop_thumb_db_loader()
        self._thumb_cache.clear()
        self._thumb_pending.clear()
        self._meta.clear()
        self._pending_removed_paths.clear()
        return super().setRootPath(path)

    def _log_decode_reason(self, path: str) -> None:
        if self._decode_reason_logs_left <= 0:
            return

        self._decode_reason_logs_left -= 1

        try:
            file_path = Path(path)
            if not file_path.exists():
                _logger.debug("decode_reason: file missing: %s", path)
                return
            stat = file_path.stat()
            mtime_ms = _to_mtime_ms_from_stat(stat)
            size = int(stat.st_size)

            self._ensure_db_cache(path)
            if not self._db_cache:
                _logger.debug("decode_reason: no db_cache; will decode: file=%s", file_path.name)
                return

            probe = self._db_cache.probe(path)
            if not probe:
                _logger.debug(
                    "decode_reason: 1(folder_has_file_db_missing); file=%s fs_mtime_ms=%d fs_size=%d key=%s",
                    file_path.name,
                    mtime_ms,
                    size,
                    path,
                )
                return

            db_mtime = probe.get("mtime")
            db_size = probe.get("size")
            has_thumb = bool(probe.get("has_thumbnail"))
            thumb_len = int(probe.get("thumbnail_len") or 0)
            db_key = probe.get("path")
            tw = probe.get("thumb_width")
            th = probe.get("thumb_height")

            # 2) DB row exists, but there is no thumbnail blob.
            if not has_thumb or thumb_len <= 0:
                _logger.debug(
                    "decode_reason: 2(db_has_file_thumb_missing); file=%s db_mtime_ms=%s db_size=%s "
                    "bytes=%d key=%s want=%dx%d db_thumb=%sx%s",
                    file_path.name,
                    db_mtime,
                    db_size,
                    thumb_len,
                    db_key,
                    self._thumb_size[0],
                    self._thumb_size[1],
                    tw,
                    th,
                )
                return

            # 3) DB row exists and has thumbnail, but it doesn't match current file (mtime/size mismatch)
            #    or we still decided to decode for some other reason.
            mismatch = False
            try:
                mismatch = (db_size is not None and int(db_size) != int(size)) or (
                    db_mtime is not None and int(db_mtime) != int(mtime_ms)
                )
            except Exception:
                mismatch = True

            if mismatch:
                _logger.debug(
                    "decode_reason: 3(db_has_thumb_but_not_current_file); file=%s fs_mtime_ms=%d fs_size=%d "
                    "db_mtime_ms=%s db_size=%s bytes=%d key=%s",
                    file_path.name,
                    mtime_ms,
                    size,
                    db_mtime,
                    db_size,
                    thumb_len,
                    db_key,
                )
            else:
                _logger.debug(
                    "decode_reason: 3(db_has_thumb_matches_but_decode); file=%s fs_mtime_ms=%d fs_size=%d "
                    "db_mtime_ms=%s db_size=%s bytes=%d key=%s",
                    file_path.name,
                    mtime_ms,
                    size,
                    db_mtime,
                    db_size,
                    thumb_len,
                    db_key,
                )
        except Exception:
            return

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
                if path not in self._thumb_pending:
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
                if (
                    prev_size == int(stat.st_size)
                    and prev_mtime is not None
                    and int(prev_mtime) == _to_mtime_ms_from_stat(stat)
                ):
                    continue

                # File changed: keep DB + memory consistent, then regenerate thumbnail.
                w, h = (None, None)
                with contextlib.suppress(Exception):
                    w, h = get_image_dimensions(path)

                self._meta[path] = (w, h, int(stat.st_size), _to_mtime_ms_from_stat(stat))
                self._thumb_cache.pop(path, None)
                self._thumb_pending.discard(path)

                try:
                    self._ensure_db_cache(path)
                    if self._db_cache:
                        # This also clears any existing thumbnail blob (meta-only until re-decoded).
                        self._db_cache.set_meta(
                            path,
                            _to_mtime_ms_from_stat(stat),
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
                                    int(cached_size) != int(stat.st_size)
                                    or int(cached_mtime) != _to_mtime_ms_from_stat(stat)
                                )
                            ):
                                self._thumb_cache.pop(path, None)
                                self._thumb_pending.discard(path)
                                self._meta[path] = (None, None, int(stat.st_size), _to_mtime_ms_from_stat(stat))
                                try:
                                    self._ensure_db_cache(path)
                                    if self._db_cache:
                                        self._db_cache.set_meta(
                                            path,
                                            _to_mtime_ms_from_stat(stat),
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
            mtime = info.lastModified().toMSecsSinceEpoch()
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
                # mtime is stored as epoch-milliseconds for stable comparisons.
                mtime_dt = QDateTime.fromMSecsSinceEpoch(int(mtime))
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
        # This is the point where we decided we cannot use cache and must decode.
        self._log_decode_reason(path)
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
                self._internal_data_changed = True
                try:
                    self.dataChanged.emit(idx, idx, [Qt.DecorationRole, Qt.DisplayRole])
                finally:
                    self._internal_data_changed = False
            else:
                try:
                    root = self.rootPath()
                    root_idx = self.index(root)
                    first = self.index(0, 0, root_idx)
                    last = self.index(self.rowCount(root_idx) - 1, 0, root_idx)
                    self._internal_data_changed = True
                    try:
                        self.dataChanged.emit(first, last, [Qt.DecorationRole, Qt.DisplayRole])
                    finally:
                        self._internal_data_changed = False
                except Exception:
                    pass
        except Exception as exc:
            _logger.debug("thumbnail_ready failed: %s", exc)

    def _ensure_db_cache(self, path: str) -> None:
        """Ensure database cache is initialized for the given path's directory.

        This delegates actual construction to `init_thumbnail_cache_for_path` to
        keep creation logic isolated and testable.
        """
        if self._db_cache is None:
            # If engine (parent) has a current root recorded, prefer that folder
            try:
                parent = self.parent()
                engine_root = getattr(parent, "_current_root", None)
                if engine_root:
                    try:
                        cache_dir = Path(engine_root)
                        try:
                            cache_dir = cache_dir.resolve()
                        except Exception:
                            cache_dir = cache_dir.absolute()
                        _logger.debug("_ensure_db_cache: using engine._current_root=%s", cache_dir)
                        self._db_cache = init_thumbnail_cache_for_path(cache_dir, "SwiftView_thumbs.db")
                        return
                    except Exception:
                        _logger.debug("_ensure_db_cache: failed to use engine._current_root=%s", engine_root)
                        # fall through to other heuristics
            except Exception:
                pass
            # If an explicit cache directory was set via `setRootPath`, prefer it.
            if getattr(self, "_explicit_cache_dir", None) is not None:
                cache_dir = self._explicit_cache_dir
                try:
                    cache_dir = cache_dir.resolve()
                except Exception:
                    cache_dir = cache_dir.absolute()
                _logger.debug("_ensure_db_cache: using explicit cache_dir=%s", cache_dir)
            else:
                p = Path(path)
                # If a directory path was provided, use it directly; otherwise use parent dir
                cache_dir = p if p.is_dir() else p.parent
                # Prefer absolute resolved path for cache location
                try:
                    cache_dir = cache_dir.resolve()
                except Exception:
                    cache_dir = cache_dir.absolute()
                _logger.debug("_ensure_db_cache: derived cache_dir=%s from path=%s", cache_dir, path)

            self._db_cache = init_thumbnail_cache_for_path(cache_dir, "SwiftView_thumbs.db")

    def _load_disk_icon(self, path: str) -> QIcon | None:
        """Load thumbnail from SQLite cache."""
        try:
            self._ensure_db_cache(path)
            if not self._db_cache:
                return None

            result = load_thumbnail_from_cache(self._db_cache, path, self._thumb_size)
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
            mtime = _to_mtime_ms_from_stat(stat)
            size = stat.st_size

            # Save to cache via helper
            save_thumbnail_to_cache(self._db_cache, path, self._thumb_size, pixmap, (orig_width, orig_height))

            # Keep in-memory meta consistent with what we just persisted.
            self._meta[path] = (orig_width, orig_height, int(size), int(mtime))
        except Exception as exc:
            _logger.debug("failed to save thumbnail to cache: %s", exc)
