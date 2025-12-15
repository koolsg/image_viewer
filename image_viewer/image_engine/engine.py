"""Image Engine - Core backend for image processing.

This module provides ImageEngine, the single entry point for all
data and processing operations in the image viewer application.
"""

import contextlib
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap

from image_viewer.logger import get_logger

from .convert_worker import ConvertWorker
from .decoder import decode_image
from .directory_worker import DirectoryWorker
from .fs_model import ImageFileSystemModel
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
    thumbnail_ready = Signal(str, QIcon)  # path, icon
    file_list_updated = Signal(list)  # new file list

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        # Core components
        self._fs_model = ImageFileSystemModel(self)
        self._loader = Loader(decode_image)
        self._thumb_loader = Loader(decode_image)

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
        # Track the currently opened root folder (absolute path)
        self._current_root: str | None = None

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

        # Directory worker: run folder file-listing off the GUI thread to avoid
        # iterating QFileSystemModel rows on the main thread which can block
        # for large directories.
        self._dir_thread = QThread(self)
        self._dir_worker = DirectoryWorker()
        self._dir_worker.moveToThread(self._dir_thread)
        self._dir_worker.files_ready.connect(self._on_directory_files_ready)
        self._dir_thread.start()
        # Connect fs_model directoryLoaded to starting the background scan
        # Connect directly to the worker slot so the slot executes in the
        # worker's thread (queued connection) instead of running on the GUI
        # thread, which would defeat the purpose.
        self._fs_model.directoryLoaded.connect(self._dir_worker.run)
        _logger.debug("ImageEngine: loader=%s thumb_loader=%s", self._loader, self._thumb_loader)

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
        try:
            p = Path(path)
            try:
                p = p.resolve()
            except Exception:
                p = p.absolute()
            if not p.is_dir():
                _logger.warning("open_folder: not a directory: %s", path)
                return False
            path = str(p)
        except Exception:
            _logger.warning("open_folder: invalid path: %s", path)
            return False

        # Clear caches
        self.clear_cache()
        self._loader.clear_pending()

        # Record current root early so any cache initialization triggered during
        # model root updates prefers the opened folder.
        self._current_root = path

        # Set root path (triggers directoryLoaded signal). The model will
        # normalize to an absolute directory; ensure we pass an absolute path.
        self._fs_model.setRootPath(path)

        # Proactively initialize the cache inside this folder so the DB is
        # created at the expected location.
        with contextlib.suppress(Exception):
            self._fs_model._ensure_db_cache(path)
            # Log where the DB adapter ended up (if available)
            try:
                db_cache = self._fs_model._db_cache
                if db_cache is not None:
                    try:
                        _logger.debug("thumbnail DB initialized at: %s", db_cache.db_path)
                    except Exception:
                        _logger.debug("thumbnail DB initialized (path unknown)")
            except Exception:
                pass
        # Emit an immediate (empty) file list so UI can update quickly while
        # the directory worker gathers the actual list in background.
        try:
            self.folder_changed.emit(path, [])
            self.file_list_updated.emit([])
        except Exception:
            pass
        _logger.debug("open_folder: %s", path)
        return True

    def get_current_folder(self) -> str:
        """Get current folder path.

        Returns:
            Absolute folder path or empty string
        """
        return self._fs_model.get_current_folder()

    def get_image_files(self) -> list[str]:
        """Get all image files in current folder (sorted).

        Returns:
            List of absolute file paths
        """
        return self._fs_model.get_image_files()

    def get_file_at_index(self, idx: int) -> str | None:
        """Get file path at given index.

        Args:
            idx: Index in sorted file list

        Returns:
            File path or None if out of range
        """
        return self._fs_model.get_file_at_index(idx)

    def get_file_index(self, path: str) -> int:
        """Get index of file path.

        Args:
            path: Absolute file path

        Returns:
            Index in sorted list, or -1 if not found
        """
        return self._fs_model.get_file_index(path)

    def get_file_count(self) -> int:
        """Get count of image files.

        Returns:
            Number of image files
        """
        return self._fs_model.get_file_count()

    @property
    def fs_model(self) -> ImageFileSystemModel:
        """Get the underlying file system model.

        This is provided for UI components that need direct model access
        (e.g., QListView for Explorer mode).
        """
        return self._fs_model

    @property
    def thumb_loader(self) -> Loader:
        """Get the thumbnail loader.

        This is provided for UI components that need direct loader access
        (e.g., ThumbnailGridWidget).
        """
        return self._thumb_loader

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
    # Note: Thumbnail management is handled by ImageFileSystemModel.
    # Use fs_model.set_loader() and thumb_loader property for thumbnail operations.

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
            # Use cached metadata (already preloaded)
            w, h, size_bytes, mtime = self._fs_model._meta.get(path, (None, None, None, None))
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
        self._fs_model.set_thumb_size(width, height)

    # ═══════════════════════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════════════════════

    def shutdown(self) -> None:
        """Shutdown the engine and release resources."""
        _logger.debug("ImageEngine shutting down")
        self._loader.shutdown()
        self._thumb_loader.shutdown()
        self._pixmap_cache.clear()
        # Stop convert worker thread
        try:
            if hasattr(self, "_convert_thread") and self._convert_thread.isRunning():
                self._convert_thread.quit()
                self._convert_thread.wait()
        except Exception:  # pragma: no cover - defensive cleanup
            _logger.debug("exception while shutting down convert thread")
        # Stop directory worker thread
        try:
            if hasattr(self, "_dir_thread") and self._dir_thread.isRunning():
                self._dir_thread.quit()
                self._dir_thread.wait()
        except Exception:  # pragma: no cover - defensive cleanup
            _logger.debug("exception while shutting down dir thread")

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

    def _on_directory_loaded(self, path: str) -> None:
        """Handle directory loaded signal from fs_model."""
        # Only process if this is the current root path
        current_root = self._fs_model.rootPath()
        if path != current_root:
            return
        # Legacy handler: prefer the background directory worker which will
        # emit `files_ready` -> `_on_directory_files_ready`. Keep this method
        # minimal to avoid accidental heavy work on the GUI thread.
        _logger.debug("directoryLoaded received for %s (deferred to worker)", path)

    def _on_directory_files_ready(self, path: str, files: list[str]) -> None:
        """Handle file list produced by `DirectoryWorker` (runs on main thread)."""
        try:
            # Normalize the incoming path to an absolute representation and
            # ignore stale notifications for non-current roots.
            try:
                pth = Path(path)
                try:
                    pth = pth.resolve()
                except Exception:
                    pth = pth.absolute()
                path_abs = str(pth)
            except Exception:
                path_abs = path
            current_root = self._fs_model.rootPath()
            if path_abs != current_root:
                return

            # Avoid duplicate emissions when the folder/file list hasn't changed
            if path == self._last_folder_loaded and files == self._last_file_list:
                return

            self._last_folder_loaded = path_abs
            self._last_file_list = list(files)
            _logger.debug("directory loaded: %s (%d files)", path_abs, len(files))

            # Emit folder/file list updates (UI callers will react accordingly)
            self.folder_changed.emit(path_abs, files)
            self.file_list_updated.emit(files)

            # Start thumbnail DB batch load (runs background threads internally)
            with contextlib.suppress(Exception):
                self._fs_model.batch_load_thumbnails()

            # Optionally prefetch a small set of nearby images to warm caches
            try:
                prefetch_list = files[:6]
                if prefetch_list:
                    self.prefetch(prefetch_list)
            except Exception:
                pass
        except Exception as e:
            _logger.debug("_on_directory_files_ready failed: %s", e)
