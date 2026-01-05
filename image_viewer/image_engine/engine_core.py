"""EngineCore: background (non-GUI) engine running in its own QThread.

This module implements the "engine runs in a thread" redesign:
- Folder scanning and DB operations live in EngineCore's thread.
- No Qt GUI objects (QPixmap/QIcon/QWidget) are created here.
- Payloads crossing thread boundaries are plain Python types (str/int/bytes/dict/list).

The UI thread should host view models and convert bytes -> QIcon/QPixmap.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QFileSystemWatcher,
    QIODevice,
    QObject,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QImage, QImageWriter

from image_viewer.logger import get_logger
from image_viewer.path_utils import abs_dir, abs_dir_str, db_key

from .db.thumbdb_bytes_adapter import ThumbDBBytesAdapter
from .decoder import encode_image_to_png, get_image_dimensions
from .fs_db_worker import FSDBLoadWorker
from .loader import Loader

# Optional dependency: pyvips may not be available in all environments; keep a
# top-level reference so imports are resolved at module import time and linters
# can reason about the name.
try:
    import pyvips  # type: ignore
except Exception:
    pyvips = None  # type: ignore

_logger = get_logger("engine_core")


_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff")
_THUMB_DB_BASENAME = "swiftview_thumbs.db"
_RGB_DIMS = 3
_RGB_CHANNELS = 3


@dataclass(frozen=True)
class FileEntry:
    path: str
    name: str
    suffix: str
    size: int
    mtime_ms: int
    is_image: bool


class EngineCore(QObject):
    """Non-GUI engine core.

    Lives in a dedicated QThread. It is responsible for:
    - Folder scanning (file list + basic stat metadata)
    - Thumbnail DB read prefetch (bytes + width/height/meta)
    - Thumbnail generation for missing entries (decode + QImage->PNG bytes)

    It must not create QPixmap/QIcon.
    """

    folder_scanned = Signal(str, list, list)  # folder_path, entries(list[dict]), image_paths(list[str])
    thumb_db_chunk = Signal(list)  # list[dict] compatible with FSDBLoadWorker payload
    thumb_db_finished = Signal(int)  # generation
    thumb_generated = Signal(dict)  # {path, thumbnail, width, height, mtime, size, thumb_width, thumb_height}
    error = Signal(str, str)  # where, message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_folder: str | None = None
        self._thumb_size: tuple[int, int] = (256, 195)

        # Current-folder watcher (Qt-only). Created in initialize() after moveToThread.
        self._watcher: QFileSystemWatcher | None = None
        self._refresh_timer: QTimer | None = None

        self._db: ThumbDBBytesAdapter | None = None
        self._db_was_created: bool = False
        self._db_loader_thread: QThread | None = None
        self._db_loader_worker: FSDBLoadWorker | None = None
        self._db_generation: int = 0

        self._thumb_loader: Loader | None = None
        self._thumb_pending: set[str] = set()
        # key -> (mtime_ms, size_bytes, thumb_w, thumb_h)
        # Used to suppress redundant re-decodes when the UI requests thumbnails
        # repeatedly while the previous result is being finalized/propagated.
        self._thumb_done: dict[str, tuple[int, int, int, int]] = {}

        # Missing/outdated thumbnails can be numerous (esp. when DB is empty).
        # We queue them and request thumbnails in small batches to avoid a decode storm.
        self._missing_thumb_queue: deque[str] = deque()
        self._missing_thumb_seen: set[str] = set()
        self._missing_thumb_timer: QTimer | None = None

        # Watcher suppression + change detection.
        # QFileSystemWatcher will fire when we update the thumbnail DB in the folder.
        # Keep a short suppression window for self-induced writes, and only refresh
        # when the visible directory contents (excluding the DB) actually change.
        self._suppress_watch_until: float = 0.0
        self._last_dir_sig: tuple[tuple[str, int, int], ...] | None = None

    # ---- lifecycle -------------------------------------------------
    def initialize(self) -> None:
        """Called once after the core has been moved to its thread."""
        if self._thumb_loader is not None:
            return

        # Watcher + debounce timer live in the EngineCore thread.
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)
        self._watcher.fileChanged.connect(self._on_file_changed)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self._refresh_current_folder)

        self._missing_thumb_timer = QTimer(self)
        self._missing_thumb_timer.setSingleShot(True)
        self._missing_thumb_timer.setInterval(0)
        self._missing_thumb_timer.timeout.connect(self._pump_missing_thumb_queue)

        # Thumbnails are encoded directly to PNG bytes by the loader to avoid
        # materializing intermediate numpy arrays and extra copies.
        self._thumb_loader = Loader(encode_image_to_png)
        self._thumb_loader.image_decoded.connect(self._on_thumb_decoded)
        _logger.debug("EngineCore initialized in thread")

    def shutdown(self) -> None:
        # Stop watcher/timer first to avoid late refreshes during teardown.
        with contextlib.suppress(Exception):
            if self._refresh_timer is not None:
                self._refresh_timer.stop()

        with contextlib.suppress(Exception):
            if self._missing_thumb_timer is not None:
                self._missing_thumb_timer.stop()

        with contextlib.suppress(Exception):
            if self._watcher is not None:
                # Remove all watched paths
                for p in list(self._watcher.directories()):
                    with contextlib.suppress(Exception):
                        self._watcher.removePath(p)
                for p in list(self._watcher.files()):
                    with contextlib.suppress(Exception):
                        self._watcher.removePath(p)

        self._stop_db_loader()
        if self._thumb_loader is not None:
            with contextlib.suppress(Exception):
                self._thumb_loader.shutdown()
        if self._db is not None:
            with contextlib.suppress(Exception):
                self._db.close()
        self._thumb_pending.clear()
        self._thumb_done.clear()
        self._missing_thumb_queue.clear()
        self._missing_thumb_seen.clear()

    # ---- configuration --------------------------------------------
    def set_thumb_size(self, width: int, height: int) -> None:
        self._thumb_size = (int(width), int(height))
        # Size change invalidates completion cache.
        self._thumb_pending.clear()
        self._thumb_done.clear()

    # ---- public API (slots) ---------------------------------------
    def open_folder(self, folder_path: str) -> None:
        """Scan folder and start DB preload in the core thread."""
        try:
            p = abs_dir(folder_path)
        except Exception as exc:
            self.error.emit("open_folder", f"invalid folder: {folder_path} ({exc})")
            return

        folder_abs = abs_dir_str(p)
        if not p.is_dir():
            self.error.emit("open_folder", f"not a directory: {folder_abs}")
            return

        # If the UI triggers duplicate open_folder calls for the same folder
        # (e.g. tree selection + grid load), avoid clearing pending thumbnails
        # and avoid forcing a full refresh.
        if self._current_folder == folder_abs:
            self._set_watched_folder(folder_abs)
            self._scan_emit_and_prefetch(p, folder_abs, force=False)
            return

        self._current_folder = folder_abs
        self._thumb_pending.clear()
        self._thumb_done.clear()
        self._missing_thumb_queue.clear()
        self._missing_thumb_seen.clear()
        with contextlib.suppress(Exception):
            if self._missing_thumb_timer is not None:
                self._missing_thumb_timer.stop()
        self._last_dir_sig = None
        self._db_was_created = False

        self._set_watched_folder(folder_abs)

        self._scan_emit_and_prefetch(p, folder_abs, force=True)

    def _scan_emit_and_prefetch(self, p: Path, folder_abs: str, *, force: bool = False) -> None:
        """Scan the folder and emit a snapshot; then start DB preload.

        If `force` is False, the scan only triggers a refresh when the directory
        signature (excluding thumbnail DB artifacts) actually changes.
        """
        entries, image_paths, dir_sig = self._scan_folder(p)

        if not force and self._last_dir_sig == dir_sig:
            _logger.debug("watcher: no meaningful dir changes; skip refresh")
            return

        self._last_dir_sig = dir_sig

        self.folder_scanned.emit(
            folder_abs,
            [
                {
                    "path": e.path,
                    "name": e.name,
                    "suffix": e.suffix,
                    "size": e.size,
                    "mtime_ms": e.mtime_ms,
                    "is_image": e.is_image,
                }
                for e in entries
            ],
            list(image_paths),
        )

        # Initialize DB for this folder and start prefetch.
        try:
            self._ensure_db(folder_abs)
            # If the DB did not exist, don't waste time running the DB preload
            # worker just to discover everything is missing. Immediately queue
            # thumbnail generation for all image files.
            if self._db_was_created:
                self._db_was_created = False
                for img_path in image_paths:
                    with contextlib.suppress(Exception):
                        self.request_thumbnail(img_path)
            else:
                self._start_db_loader(folder_abs, image_count=len(image_paths))
        except Exception as exc:
            self.error.emit("db_init", str(exc))

    def _scan_folder(self, p: Path) -> tuple[list[FileEntry], list[str], tuple[tuple[str, int, int], ...]]:
        entries: list[FileEntry] = []
        image_paths: list[str] = []

        try:
            for child in p.iterdir():
                if not child.is_file():
                    continue

                name = child.name
                lower_name = name.lower()

                # Ignore our own SQLite DB artifacts to avoid watcher loops.
                if lower_name.startswith(_THUMB_DB_BASENAME):
                    continue

                suffix = child.suffix.lower()
                is_image = suffix in _IMAGE_EXTS

                try:
                    stat = child.stat()
                    size = int(stat.st_size)
                    # mtime stored in ms for easier comparisons with DB.
                    mtime_ms = int(stat.st_mtime * 1000)
                except Exception:
                    size = 0
                    mtime_ms = 0

                path_str = str(child)
                entries.append(
                    FileEntry(
                        path=path_str,
                        name=name,
                        suffix=suffix.lstrip("."),
                        size=size,
                        mtime_ms=mtime_ms,
                        is_image=is_image,
                    )
                )
                if is_image:
                    image_paths.append(path_str)

            # Sort like QFileSystemModel default: name asc.
            entries.sort(key=lambda e: e.name.lower())
            image_paths.sort(key=lambda s: Path(s).name.lower())
        except Exception as exc:
            self.error.emit("scan", str(exc))

        # Directory signature: (name, size, mtime_ms) tuples, sorted.
        # This purposefully ignores the DB file so that our own thumbnail writes
        # don't cause rescan storms.
        dir_sig: tuple[tuple[str, int, int], ...] = tuple((e.name.lower(), e.size, e.mtime_ms) for e in entries)
        return entries, image_paths, dir_sig

    def _set_watched_folder(self, folder_abs: str) -> None:
        """Watch only the current folder path (directoryChanged)."""
        if self._watcher is None:
            return

        # Remove previous directory watches (current-folder-only policy)
        for d in list(self._watcher.directories()):
            if d != folder_abs:
                with contextlib.suppress(Exception):
                    self._watcher.removePath(d)

        if folder_abs and folder_abs not in self._watcher.directories():
            with contextlib.suppress(Exception):
                self._watcher.addPath(folder_abs)

    def _on_directory_changed(self, path: str) -> None:
        # Debounce refresh storms.
        if time.monotonic() < self._suppress_watch_until:
            return
        _logger.debug("watcher: directoryChanged %s", path)
        self._schedule_refresh()

    def _on_file_changed(self, path: str) -> None:
        # We do not add per-file watches (too expensive); keep for completeness.
        if time.monotonic() < self._suppress_watch_until:
            return
        _logger.debug("watcher: fileChanged %s", path)
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_timer is None:
            return
        # Ignore watcher activity caused by our own DB writes.
        if time.monotonic() < self._suppress_watch_until:
            return
        self._refresh_timer.start()

    def _refresh_current_folder(self) -> None:
        folder = self._current_folder
        if not folder:
            return
        try:
            p = abs_dir(folder)
        except Exception as exc:
            self.error.emit("watch_refresh", f"invalid folder: {folder} ({exc})")
            return
        if not p.is_dir():
            # Folder deleted/moved.
            self.error.emit("watch_refresh", f"folder missing: {folder}")
            return

        # Rescan + restart DB preload only if something meaningful changed.
        self._scan_emit_and_prefetch(p, abs_dir_str(p), force=False)

    def request_thumbnail(self, path: str) -> None:
        """Request a thumbnail decode+store for a single path."""
        if not path:
            return
        if self._thumb_loader is None:
            return

        key = db_key(path)
        if key in self._thumb_pending:
            return

        # If we've already generated a thumbnail for this file at the current
        # size and it hasn't changed, avoid re-decoding.
        done = self._thumb_done.get(key)
        if done is not None:
            try:
                st = os.stat(path)
                size = int(st.st_size)
                mtime_ms = int(st.st_mtime * 1000)
            except Exception:
                size = -1
                mtime_ms = -1

            tw, th = self._thumb_size
            if (mtime_ms, size, tw, th) == done:
                return

        self._thumb_pending.add(key)

        tw, th = self._thumb_size
        self._thumb_loader.request_load(path, tw, th, "both")

    # ---- DB preload ------------------------------------------------
    def _ensure_db(self, folder_abs: str) -> None:
        db_path = Path(folder_abs) / "SwiftView_thumbs.db"
        # Replace DB when folder changes.
        if self._db is not None and self._db.db_path != db_path:
            with contextlib.suppress(Exception):
                self._db.close()
            self._db = None
            self._db_was_created = False

        if self._db is None:
            exists_before = db_path.exists()
            # Creating/opening the DB can trigger watcher events in the same folder.
            self._suppress_watch_until = max(self._suppress_watch_until, time.monotonic() + 0.75)
            self._db = ThumbDBBytesAdapter(db_path)
            self._db_was_created = not exists_before

    def _start_db_loader(self, folder_abs: str, *, image_count: int | None = None) -> None:
        self._stop_db_loader()
        if self._db is None:
            return

        # If the DB exists but contains no thumbnails yet, the preload worker will
        # report everything as missing. For small folders we can just generate all
        # thumbnails up-front so the grid isn't sparsely populated.
        # For large folders we cap this to avoid a decode storm.
        prefetch_limit = 48
        if image_count is not None:
            try:
                n = int(image_count)
            except Exception:
                n = 0
            if n > 0:
                prefetch_limit = min(n, 256)

        self._db_generation += 1
        generation = self._db_generation

        worker = FSDBLoadWorker(
            folder_path=folder_abs,
            db_path=str(Path(folder_abs) / "SwiftView_thumbs.db"),
            db_operator=self._db.operator,
            use_operator_for_reads=True,
            thumb_width=self._thumb_size[0],
            thumb_height=self._thumb_size[1],
            generation=generation,
            prefetch_limit=prefetch_limit,
            chunk_size=800,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.chunk_loaded.connect(self._on_db_chunk)
        worker.chunk_loaded.connect(self.thumb_db_chunk)
        worker.finished.connect(self.thumb_db_finished)
        worker.missing_paths.connect(self._on_db_missing_paths)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._db_loader_thread = thread
        self._db_loader_worker = worker
        thread.start()

    def _on_db_chunk(self, rows: list[dict]) -> None:
        """Update thumbnail-done cache from DB preload rows.

        This lets `request_thumbnail()` short-circuit (mtime/size/target match)
        even if the UI asks for thumbnails before the bytes are displayed.
        """
        try:
            tw, th = self._thumb_size
        except Exception:
            tw, th = (256, 195)

        for row in rows:
            if not isinstance(row, dict):
                continue
            path = row.get("path")
            if not path:
                continue
            thumb = row.get("thumbnail")
            try:
                if thumb is None or len(thumb) == 0:
                    continue
            except Exception:
                continue

            try:
                key = db_key(str(path))
            except Exception:
                continue

            mtime = row.get("mtime")
            size = row.get("size")
            try:
                mtime_ms = int(mtime) if mtime is not None else None
                size_b = int(size) if size is not None else None
            except Exception:
                continue

            if mtime_ms is None or size_b is None:
                continue

            # Record as done for current target size.
            self._thumb_done[key] = (mtime_ms, size_b, int(tw), int(th))

    def _stop_db_loader(self) -> None:
        try:
            if self._db_loader_worker is not None:
                with contextlib.suppress(Exception):
                    self._db_loader_worker.stop()
            if self._db_loader_thread is not None:
                with contextlib.suppress(Exception):
                    self._db_loader_thread.quit()
                    self._db_loader_thread.wait(250)
        finally:
            self._db_loader_worker = None
            self._db_loader_thread = None

    def _on_db_missing_paths(self, paths: list[str]) -> None:
        try:
            sample = [str(p) for p in paths[:3]]
        except Exception:
            sample = []
        _logger.debug("db preload missing_paths: count=%d sample=%s", len(paths), sample)

        # Queue and throttle so we can eventually generate all thumbs.
        for path in paths:
            try:
                # FSDBLoadWorker returns canonical db_key() paths (forward slashes).
                # Convert to a local filesystem path before handing off to the decoder.
                p = str(Path(path))
                if Path(p).suffix.lower() not in _IMAGE_EXTS:
                    continue
                key = db_key(p)
                if key in self._missing_thumb_seen:
                    continue
                self._missing_thumb_seen.add(key)
                self._missing_thumb_queue.append(p)
            except Exception:
                continue

        with contextlib.suppress(Exception):
            if self._missing_thumb_timer is not None and not self._missing_thumb_timer.isActive():
                self._missing_thumb_timer.start()

    def _pump_missing_thumb_queue(self) -> None:
        """Drain missing thumbnail queue in small batches."""
        # Keep this conservative; the Loader has its own concurrency, but the queue
        # can be huge and we don't want to enqueue everything immediately.
        batch = 8
        for _ in range(batch):
            try:
                p = self._missing_thumb_queue.popleft()
            except IndexError:
                break
            with contextlib.suppress(Exception):
                self.request_thumbnail(p)

        with contextlib.suppress(Exception):
            if self._missing_thumb_queue and self._missing_thumb_timer is not None:
                self._missing_thumb_timer.start()

    # ---- thumbnail generation --------------------------------------
    def _on_thumb_decoded(self, path: str, image_data, error) -> None:
        # Runs in the thread that owns this EngineCore (queued).
        try:
            key = db_key(path)
            if error or image_data is None:
                self.error.emit("thumb_decode", f"{path}: {error}")
                return

            # Loader returns PNG bytes directly (preferred) to avoid extra copies.
            png_bytes: bytes | None = None
            if isinstance(image_data, (bytes, bytearray, memoryview)):
                png_bytes = bytes(image_data)
            else:
                # If we receive a numpy array, attempt to encode it — but this is
                # considered a secondary path and will produce an error if encoding
                # fails. The loader should be using `encode_image_to_png` instead.
                arr = np.asarray(image_data)
                if arr.ndim != _RGB_DIMS or arr.shape[2] != _RGB_CHANNELS:
                    self.error.emit("thumb_decode", f"unexpected array shape for {path}: {arr}")
                    return

                h, w, _ = arr.shape
                # Ensure contiguous bytes
                rgb = np.ascontiguousarray(arr, dtype=np.uint8)

                try:
                    png_bytes = self._numpy_to_png_bytes_vips(rgb)
                except Exception as e:  # pragma: no cover - surface vips failures as thumb_encode errors
                    self.error.emit("thumb_encode", f"pyvips failed to encode png for {path}: {e}")
                    return

                if not png_bytes:
                    self.error.emit("thumb_encode", f"pyvips produced empty png for {path} (thumb={w}x{h})")
                    return

            # Stat for meta.
            try:
                stat = os.stat(path)
                size = int(stat.st_size)
                mtime_ms = int(stat.st_mtime * 1000)
            except Exception:
                size = 0
                mtime_ms = 0

            # Determine original dimensions (cheap header read). If it fails, store None.
            try:
                ow, oh = get_image_dimensions(path)
            except Exception:
                ow, oh = (None, None)

            tw, th = self._thumb_size

            # Store via bytes adapter (no Qt GUI types).
            if self._db is not None:
                # DB updates will change the directory and can trigger watcher events.
                self._suppress_watch_until = max(self._suppress_watch_until, time.monotonic() + 0.75)
                self._db.upsert_meta(
                    path,
                    mtime_ms,
                    size,
                    meta={
                        "width": ow,
                        "height": oh,
                        "thumb_width": tw,
                        "thumb_height": th,
                        "thumbnail": png_bytes,
                        "created_at": time.time(),
                    },
                )

            # Mark complete before releasing the pending gate.
            self._thumb_done[key] = (mtime_ms, size, tw, th)

            self.thumb_generated.emit(
                {
                    "path": str(Path(path)),
                    "thumbnail": png_bytes,
                    "width": ow,
                    "height": oh,
                    "mtime": mtime_ms,
                    "size": size,
                    "thumb_width": tw,
                    "thumb_height": th,
                }
            )
        except Exception as exc:
            self.error.emit("thumb_pipeline", str(exc))
        finally:
            with contextlib.suppress(Exception):
                self._thumb_pending.discard(db_key(path))

    @staticmethod
    def _qimage_to_png_bytes(qimg: QImage) -> bytes:
        try:
            if qimg.isNull():
                return b""

            # Encode from a 32-bit format to avoid edge cases with 24-bit scanlines
            # (e.g., odd widths / non-4-byte aligned bytesPerLine) and to keep the PNG
            # writer path consistent.
            try:
                img = qimg.convertToFormat(QImage.Format.Format_ARGB32)
            except Exception:
                img = qimg

            arr = QByteArray()
            buf = QBuffer(arr)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)

            writer = QImageWriter(buf, b"png")
            writer.setQuality(100)
            ok = writer.write(img)

            buf.close()
            if not ok:
                return b""
            return bytes(arr.data())
        except Exception:
            return b""

    @staticmethod
    def _numpy_to_png_bytes_vips(rgb: np.ndarray) -> bytes:
        """Encode an RGB numpy array to PNG bytes using pyvips.

        This method prefers pyvips for direct encoding from memory to avoid the
        `QImage -> QImageWriter` round-trip. It requires `pyvips` to be available
        in the environment and raises on failure so callers can decide how to
        handle the error (we intentionally do not fall back to QImage here).
        """
        # Require pyvips to be available; we intentionally do not fall back to
        # QImage encoding here (caller will handle error reporting).
        if pyvips is None:
            raise RuntimeError("pyvips is not available in this environment")

        if rgb.ndim != _RGB_DIMS or rgb.shape[2] != _RGB_CHANNELS:
            raise ValueError("expected RGB numpy array with shape (h, w, 3)")

        h, w, _ = rgb.shape
        if rgb.dtype != np.uint8:
            rgb = rgb.astype(np.uint8)

        # pyvips expects a contiguous bytes buffer in C order
        buf = rgb.tobytes()
        img: Any = pyvips.Image.new_from_memory(buf, w, h, _RGB_CHANNELS, "uchar")
        # Ensure interpretation is sRGB for consistent PNGs; ignore if not supported
        with contextlib.suppress(Exception):
            img = img.copy(interpretation="srgb")

        out = img.write_to_buffer(".png")
        # Normalize to bytes in case pyvips returns a memoryview-like object
        if isinstance(out, bytes):
            return out
        return bytes(out)
