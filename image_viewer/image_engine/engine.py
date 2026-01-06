"""Image Engine - Core backend for image processing.

This module provides ImageEngine, the single entry point for all
data and processing operations in the image viewer application.
"""

import contextlib
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QImage, QPixmap

from image_viewer.logger import get_logger
from image_viewer.path_utils import abs_path, abs_path_str, db_key

from .convert_worker import ConvertWorker
from .decoder import decode_image
from .engine_core import EngineCore
from .loader import Loader
from .strategy import DecodingStrategy, FastViewStrategy, FullStrategy

if TYPE_CHECKING:
    pass

_logger = get_logger("engine")


class ImageEngine(QObject):
    """Image processing engine - single entry point for all data/processing.

    This class provides a clean API for:
    - File system operations (open folder, get files, etc.)
    - Image decoding (request decode, get cached, prefetch)
    - Thumbnail management
    - Metadata access

    Signals:
        image_ready: Emitted when an image is decoded (path, pixmap, error)
        folder_changed: Emitted when folder changes (path, file_list)
        thumbnail_ready: Emitted when a thumbnail is ready (path, icon)
        file_list_updated: Emitted when file list changes (file_list)
    """

    # Signals for UI notification
    image_ready = Signal(str, QPixmap, object)  # path, pixmap, error
    folder_changed = Signal(str, list)  # folder_path, file_list
    file_list_updated = Signal(list)  # new file list

    # Explorer-mode snapshots (UI-thread model consumes these)
    explorer_entries_changed = Signal(str, list)  # folder_path, entries(list[dict])
    explorer_thumb_rows = Signal(list)  # list[dict]
    explorer_thumb_generated = Signal(dict)  # dict payload

    # Internal cross-thread bridges to EngineCore
    _core_open_folder = Signal(str)
    _core_request_thumbnail = Signal(str)
    _core_set_thumb_size = Signal(int, int)
    _core_shutdown = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        # UI-thread decode pipeline for full-resolution images (creates QPixmap on UI thread)
        self._loader = Loader(decode_image)

        # Core engine thread (folder scan + DB + thumbnail bytes)
        self._core_thread = QThread(self)
        self._core = EngineCore()
        self._core.moveToThread(self._core_thread)
        self._core_thread.started.connect(self._core.initialize)
        self._core_open_folder.connect(self._core.open_folder)
        self._core_request_thumbnail.connect(self._core.request_thumbnail)
        self._core_set_thumb_size.connect(self._core.set_thumb_size)
        self._core_shutdown.connect(self._core.shutdown)
        self._core.folder_scanned.connect(self._on_core_folder_scanned)
        self._core.thumb_db_chunk.connect(self._on_core_thumb_db_chunk)
        self._core.thumb_generated.connect(self._on_core_thumb_generated)
        self._core.error.connect(self._on_core_error)
        self._core_thread.start()

        # Pixmap cache (LRU)
        self._pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._cache_size = 20

        # Decoding strategy - create shared instances to avoid duplicate init/logging
        self._full_strategy: DecodingStrategy = FullStrategy()
        self._fast_strategy: DecodingStrategy = FastViewStrategy()
        self._decoding_strategy: DecodingStrategy = self._full_strategy
        # Cache last folder and file list to avoid noisy duplicate signals
        self._last_folder_loaded: str | None = None
        self._last_file_list: list[str] | None = None
        # Cached file list for callers that need a quick answer without
        # iterating the QFileSystemModel on the GUI thread.
        self._file_list_cache: list[str] = []
        # Track the currently opened root folder (absolute path)
        self._current_root: str | None = None
        # Metadata cache populated by EngineCore DB preload.
        # key -> (width, height, size_bytes, mtime_ms)
        self._meta_cache: dict[str, tuple[int | None, int | None, int | None, int | None]] = {}

        # Internal signal connections
        # Offload numpy->QImage conversion to a background worker thread
        self._convert_thread = QThread(self)
        self._convert_worker = ConvertWorker()
        self._convert_worker.moveToThread(self._convert_thread)
        self._convert_thread.start()
        # Connect loader results directly to the worker (queued across threads)
        self._loader.image_decoded.connect(self._convert_worker.convert)
        # Receive converted QImage back on the main thread for finalization
        self._convert_worker.image_converted.connect(self._on_image_converted)

        _logger.debug("ImageEngine: loader=%s", self._loader)

        _logger.debug("ImageEngine initialized")

    # ═══════════════════════════════════════════════════════════════════════
    # File System API
    # ═══════════════════════════════════════════════════════════════════════

    def open_folder(self, path: str) -> bool:
        """Open a folder and load its image files.

        Args:
            path: Folder path to open

        Returns:
            True if folder was opened successfully
        """
        p = abs_path(path)
        if not p.is_dir():
            _logger.warning("open_folder: not a directory: %s", path)
            return False
        path = abs_path_str(p)

        # If UI triggers duplicate open_folder calls for the same folder (e.g.
        # tree selection + grid load), avoid clearing caches / emitting empty
        # snapshots. Let the core thread decide whether a refresh is needed.
        if self._current_root == path:
            self._core_open_folder.emit(path)
            _logger.debug("open_folder (same folder): %s", path)
            return True

        # Clear caches
        self.clear_cache()
        self._loader.clear_pending()
        self._meta_cache.clear()
        # Clear file list cache immediately; the directory worker will repopulate.
        self._file_list_cache = []
        self._last_folder_loaded = None
        self._last_file_list = None

        # Record current root and kick the core thread. Emit immediate empty
        # lists so UI can update while the core scans.
        self._current_root = path
        self.folder_changed.emit(path, [])
        self.file_list_updated.emit([])
        self.explorer_entries_changed.emit(path, [])
        self._core_open_folder.emit(path)
        _logger.debug("open_folder: %s", path)
        return True

    def get_current_folder(self) -> str:
        """Get current folder path.

        Returns:
            Absolute folder path or empty string
        """
        return self._current_root or ""

    def get_image_files(self) -> list[str]:
        """Get all image files in current folder (sorted).

        Returns:
            List of absolute file paths
        """
        # IMPORTANT: Do not iterate QFileSystemModel here; that can block the
        # GUI thread for large folders. The directory worker populates the
        # canonical list asynchronously.
        return list(self._file_list_cache)

    def get_file_at_index(self, idx: int) -> str | None:
        """Get file path at given index.

        Args:
            idx: Index in sorted file list

        Returns:
            File path or None if out of range
        """
        files = self._file_list_cache
        if 0 <= idx < len(files):
            return files[idx]
        return None

    def get_file_index(self, path: str) -> int:
        """Get index of file path.

        Args:
            path: Absolute file path

        Returns:
            Index in sorted list, or -1 if not found
        """
        try:
            return self._file_list_cache.index(path)
        except ValueError:
            return -1

    def get_file_count(self) -> int:
        """Get count of image files.

        Returns:
            Number of image files
        """
        return len(self._file_list_cache)

    def request_thumbnail(self, path: str) -> None:
        """Request thumbnail generation for a specific file (engine core thread)."""
        try:
            if path:
                self._core_request_thumbnail.emit(str(Path(path)))
        except Exception:
            return

    # ═══════════════════════════════════════════════════════════════════════
    # Image Decoding API
    # ═══════════════════════════════════════════════════════════════════════

    def request_decode(
        self,
        path: str,
        target_size: tuple[int, int] | None = None,
        priority: bool = False,
    ) -> None:
        """Request image decoding.

        If the image is cached, emits image_ready immediately.
        Otherwise, queues the decode request.

        Args:
            path: Image file path
            target_size: Optional (width, height) for resized decode
            priority: If True, process this request first (reserved for future use)
        """
        # Check cache first
        if path in self._pixmap_cache:
            # Move to end (LRU)
            pix = self._pixmap_cache.pop(path)
            self._pixmap_cache[path] = pix
            _logger.debug("request_decode: cache hit for %s", path)
            self.image_ready.emit(path, pix, None)
            return

        # Queue decode request
        tw, th = target_size or (None, None)
        _logger.debug("request_decode: queuing %s target=(%s,%s)", path, tw, th)
        self._loader.request_load(path, tw, th, "both")

    def get_cached_pixmap(self, path: str) -> QPixmap | None:
        """Get cached pixmap if available.

        Args:
            path: Image file path

        Returns:
            Cached QPixmap or None
        """
        return self._pixmap_cache.get(path)

    def is_cached(self, path: str) -> bool:
        """Check if image is cached.

        Args:
            path: Image file path

        Returns:
            True if cached
        """
        return path in self._pixmap_cache

    def prefetch(
        self,
        paths: list[str],
        target_size: tuple[int, int] | None = None,
    ) -> None:
        """Prefetch multiple images.

        Args:
            paths: List of image file paths
            target_size: Optional (width, height) for resized decode
        """
        tw, th = target_size or (None, None)
        for path in paths:
            if path not in self._pixmap_cache:
                self._loader.request_load(path, tw, th, "both")

    def cancel_pending(self, path: str | None = None) -> None:
        """Cancel pending decode requests.

        Args:
            path: Specific path to cancel, or None for all
        """
        if path:
            self._loader.ignore_path(path)
        else:
            self._loader.clear_pending()

    def clear_cache(self) -> None:
        """Clear the pixmap cache."""
        self._pixmap_cache.clear()
        _logger.debug("pixmap cache cleared")

    def remove_from_cache(self, path: str) -> bool:
        """Remove a specific path from the pixmap cache.

        Args:
            path: Image file path to remove

        Returns:
            True if path was in cache and removed
        """
        removed = self._pixmap_cache.pop(path, None) is not None
        if removed:
            _logger.debug("removed from cache: %s", path)
        return removed

    def ignore_path(self, path: str) -> None:
        """Ignore a path in the loader (skip pending requests).

        Args:
            path: Image file path to ignore
        """
        self._loader.ignore_path(path)

    def unignore_path(self, path: str) -> None:
        """Unignore a path in the loader.

        Args:
            path: Image file path to unignore
        """
        self._loader.unignore_path(path)

    # ═══════════════════════════════════════════════════════════════════════
    # Thumbnail API
    # ═══════════════════════════════════════════════════════════════════════
    # Note: Thumbnail generation/DB is managed by EngineCore.

    # ═══════════════════════════════════════════════════════════════════════
    # Metadata API
    # ═══════════════════════════════════════════════════════════════════════

    def get_file_info(self, path: str) -> dict:
        """Get file metadata.

        Args:
            path: Image file path

        Returns:
            Dict with keys: resolution, size, mtime, etc.
        """
        info = {}
        try:
            # Use cached metadata (populated by engine core DB preload)
            w, h, size_bytes, mtime = self._meta_cache.get(db_key(path), (None, None, None, None))
            if w and h:
                info["resolution"] = (w, h)
            if size_bytes is not None:
                info["size"] = size_bytes
            if mtime is not None:
                info["mtime"] = mtime
        except Exception as e:
            _logger.debug("get_file_info failed: %s", e)
        return info

    def get_resolution(self, path: str) -> tuple[int, int] | None:
        """Get image resolution.

        Args:
            path: Image file path

        Returns:
            (width, height) or None
        """
        info = self.get_file_info(path)
        return info.get("resolution")

    # ═══════════════════════════════════════════════════════════════════════
    # Settings API
    # ═══════════════════════════════════════════════════════════════════════

    def set_decoding_strategy(self, strategy: DecodingStrategy) -> None:
        """Set the decoding strategy.

        Args:
            strategy: DecodingStrategy instance
        """
        self._decoding_strategy = strategy
        _logger.debug("decoding strategy set to: %s", strategy.get_name())

    def get_decoding_strategy(self) -> DecodingStrategy:
        """Get current decoding strategy.

        Returns:
            Current DecodingStrategy instance
        """
        return self._decoding_strategy

    def get_full_strategy(self) -> DecodingStrategy:
        """Get the full decoding strategy instance."""
        return self._full_strategy

    def get_fast_strategy(self) -> DecodingStrategy:
        """Get the fast decoding strategy instance."""
        return self._fast_strategy

    def set_cache_size(self, size: int) -> None:
        """Set pixmap cache size.

        Args:
            size: Maximum number of cached pixmaps
        """
        self._cache_size = max(1, size)
        # Trim cache if needed
        while len(self._pixmap_cache) > self._cache_size:
            self._pixmap_cache.popitem(last=False)
        _logger.debug("cache size set to: %d", self._cache_size)

    def set_thumbnail_size(self, width: int, height: int) -> None:
        """Set default thumbnail size.

        Args:
            width: Thumbnail width
            height: Thumbnail height
        """
        self._core_set_thumb_size.emit(int(width), int(height))

    # ═══════════════════════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════════════════════

    def shutdown(self) -> None:
        """Shutdown the engine and release resources."""
        _logger.debug("ImageEngine shutting down")
        self._loader.shutdown()
        self._pixmap_cache.clear()
        # Stop convert worker thread
        try:
            if hasattr(self, "_convert_thread") and self._convert_thread.isRunning():
                self._convert_thread.quit()
                self._convert_thread.wait()
        except Exception:  # pragma: no cover - defensive cleanup
            _logger.debug("exception while shutting down convert thread")
        # Stop core engine thread
        try:
            if hasattr(self, "_core"):
                with contextlib.suppress(Exception):
                    self._core_shutdown.emit()
            if hasattr(self, "_core_thread") and self._core_thread.isRunning():
                self._core_thread.quit()
                self._core_thread.wait()
        except Exception:  # pragma: no cover - defensive cleanup
            _logger.debug("exception while shutting down core thread")

    # ═══════════════════════════════════════════════════════════════════════
    # Internal Handlers
    # ═══════════════════════════════════════════════════════════════════════

    def _on_image_decoded(self, path: str, image_data, error) -> None:
        """Handle decoded image from loader."""
        # Legacy hook - the loader is connected directly to the convert worker
        # which will handle both normal and error cases. Keep this method for
        # completeness but prefer the worker pipeline above.
        if error or image_data is None:
            _logger.debug("decode error for %s: %s", path, error)
            self.image_ready.emit(path, QPixmap(), error)
            return

        # Normal conversion now occurs in the ConvertWorker running in a
        # background thread; results are handled in `_on_image_converted`.

    def _on_image_converted(self, path: str, qimage: QImage, error) -> None:
        """Handle QImage produced by the ConvertWorker and make a QPixmap.

        This method runs on the main thread and is responsible for creating a
        QPixmap (GUI resource), caching it, and emitting `image_ready`.
        """
        try:
            if error or qimage.isNull():
                _logger.debug("image conversion failed for %s: %s", path, error)
                self.image_ready.emit(path, QPixmap(), error)
                return

            pixmap = QPixmap.fromImage(qimage)
            if pixmap.isNull():
                _logger.debug("failed to create pixmap for %s", path)
                self.image_ready.emit(path, QPixmap(), "Failed to create pixmap")
                return

            # Cache the pixmap (LRU)
            if path in self._pixmap_cache:
                self._pixmap_cache.pop(path)
            self._pixmap_cache[path] = pixmap
            if len(self._pixmap_cache) > self._cache_size:
                self._pixmap_cache.popitem(last=False)

            _logger.debug(
                "image converted: %s (%dx%d) cache_size=%d",
                path,
                pixmap.width(),
                pixmap.height(),
                len(self._pixmap_cache),
            )
            self.image_ready.emit(path, pixmap, None)

        except Exception as e:
            _logger.exception("failed to finalize image: %s", path)
            self.image_ready.emit(path, QPixmap(), str(e))

    def _on_core_folder_scanned(self, folder_path: str, entries: list[dict], image_paths: list[str]) -> None:
        """Receive core scan snapshot on UI thread."""
        try:
            folder_abs = abs_path_str(folder_path)
        except Exception:
            folder_abs = folder_path

        if self._current_root and folder_abs != self._current_root:
            return

        # Explorer snapshot
        self.explorer_entries_changed.emit(folder_abs, entries)

        # View-mode file list (images only)
        files = list(image_paths)

        if folder_abs == self._last_folder_loaded and files == self._last_file_list:
            return
        self._last_folder_loaded = folder_abs
        self._last_file_list = list(files)
        self._file_list_cache = list(files)

        self.folder_changed.emit(folder_abs, files)
        self.file_list_updated.emit(files)

        # Warm cache by prefetching a small set
        with contextlib.suppress(Exception):
            prefetch_list = files[:6]
            if prefetch_list:
                self.prefetch(prefetch_list)

    def _on_core_thumb_db_chunk(self, rows: list) -> None:
        """Receive DB preload rows on UI thread."""
        # Update metadata cache for get_file_info and emit to explorer model.
        try:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                path = row.get("path")
                if not path:
                    continue
                key = db_key(str(path))
                w = row.get("width")
                h = row.get("height")
                size = row.get("size")
                mtime = row.get("mtime")
                self._meta_cache[key] = (
                    int(w) if w is not None else None,
                    int(h) if h is not None else None,
                    int(size) if size is not None else None,
                    int(mtime) if mtime is not None else None,
                )
        except Exception:
            pass
        self.explorer_thumb_rows.emit(rows)

    def _on_core_thumb_generated(self, payload: dict) -> None:
        try:
            path = payload.get("path")
            if path:
                key = db_key(str(path))
                w = payload.get("width")
                h = payload.get("height")
                size = payload.get("size")
                mtime = payload.get("mtime")
                self._meta_cache[key] = (
                    int(w) if w is not None else None,
                    int(h) if h is not None else None,
                    int(size) if size is not None else None,
                    int(mtime) if mtime is not None else None,
                )
        except Exception:
            pass
        self.explorer_thumb_generated.emit(payload)

    def _on_core_error(self, where: str, message: str) -> None:
        _logger.debug("EngineCore error (%s): %s", where, message)
