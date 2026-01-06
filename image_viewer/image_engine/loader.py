"""Image loader with multi-process decoding.

This module provides the Loader class that manages file I/O scheduling
and multi-process image decoding for high performance.
"""

import contextlib
import os
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from image_viewer.logger import get_logger

_logger = get_logger("loader")


class Loader(QObject):
    """Loader that manages file I/O scheduling and multi-process decoding.

    The decode_fn must be a pickleable top-level function of the form:
    (path, target_width, target_height, size) -> (path, array|None, error|None)
    """

    image_decoded = Signal(str, object, object)  # path, numpy_array, error

    def __init__(self, decode_fn: Callable[[str, int | None, int | None, str], tuple]):
        super().__init__()
        self._decode_fn = decode_fn
        # Process pool (for general decoding)
        self.executor = ProcessPoolExecutor()
        max_io = max(2, min(4, (os.cpu_count() or 2)))
        self.io_pool = ThreadPoolExecutor(max_workers=max_io)
        self._pending: set[str] = set()
        self._ignored: set[str] = set()
        self._next_id = 1
        self._latest_id: dict[str, int] = {}
        self._latest_params: dict[str, tuple[int | None, int | None, str]] = {}
        self._lock = threading.Lock()
        _logger.debug("Loader init: process_pool=on, io_workers=%s", max_io)

    def _submit_decode(
        self,
        file_path: str,
        target_width: int | None,
        target_height: int | None,
        size: str = "both",
        req_id: int | None = None,
    ):
        try:
            _logger.debug(
                "submit_decode: path=%s id=%s size=%s target=(%s,%s)",
                file_path,
                req_id,
                size,
                target_width,
                target_height,
            )
            future = self.executor.submit(self._decode_fn, file_path, target_width, target_height, size)
            with contextlib.suppress(Exception):
                future._req_id = req_id  # type: ignore[attr-defined]
                future._path = file_path  # type: ignore[attr-defined]
            future.add_done_callback(self.on_decode_finished)
        except Exception as e:
            _logger.exception("submit decode failed for %s", file_path)
            with self._lock:
                self._pending.discard(file_path)
            self.image_decoded.emit(file_path, None, str(e))

    def on_decode_finished(self, future):
        try:
            path, data, error = future.result()
        except Exception as e:
            _logger.exception("decode future failed")
            # future may not have attrs if error happened before tagging
            try:
                path = getattr(future, "_path", "<unknown>")
            except Exception:
                path = "<unknown>"
            with self._lock:
                self._pending.discard(path)
            self.image_decoded.emit(path, None, str(e))
            return
        try:
            req_id = getattr(future, "_req_id", None)
        except Exception:
            req_id = None
        with self._lock:
            self._pending.discard(path)
            # Avoid unbounded growth; params are only used for pending dedupe.
            with contextlib.suppress(Exception):
                self._latest_params.pop(path, None)
            if path in self._ignored:
                _logger.debug("decode_finished ignored: path=%s id=%s (in ignored)", path, req_id)
                return
            latest = self._latest_id.get(path)
            if latest is not None and req_id is not None and req_id != latest:
                _logger.debug("decode_finished stale: path=%s id=%s latest=%s (dropped)", path, req_id, latest)
                return
        try:
            shape = getattr(data, "shape", None)
            _logger.debug("decode_finished emit: path=%s id=%s shape=%s err=%s", path, req_id, shape, error)
        except Exception:
            _logger.debug("decode_finished emit: path=%s id=%s err=%s", path, req_id, error)
        self.image_decoded.emit(path, data, error)

    def request_load(
        self, path: str, target_width: int | None = None, target_height: int | None = None, size: str = "both"
    ) -> None:
        params = (target_width, target_height, size)
        with self._lock:
            if path in self._ignored:
                _logger.debug("request_load skip(ignored): path=%s", path)
                return

            # If an identical request is already pending, do not queue another.
            if path in self._pending and self._latest_params.get(path) == params:
                _logger.debug(
                    "request_load dedupe(pending): path=%s size=%s target=(%s,%s)",
                    path,
                    size,
                    target_width,
                    target_height,
                )
                return

            # Allow re-request with a new req_id even if pending. If params differ,
            # the previous result will be dropped as stale.
            if path not in self._pending:
                self._pending.add(path)
            req_id = self._next_id
            self._next_id += 1
            self._latest_id[path] = req_id
            self._latest_params[path] = params
            pending_count = len(self._pending)
        _logger.debug(
            "request_load queued: path=%s id=%s size=%s target=(%s,%s) pending=%s",
            path,
            req_id,
            size,
            target_width,
            target_height,
            pending_count,
        )
        self.io_pool.submit(self._submit_decode, path, target_width, target_height, size, req_id)

    def ignore_path(self, path: str):
        with self._lock:
            self._ignored.add(path)
            self._pending.discard(path)
            with contextlib.suppress(Exception):
                self._latest_id.pop(path, None)
            with contextlib.suppress(Exception):
                self._latest_params.pop(path, None)

    def unignore_path(self, path: str):
        with self._lock:
            self._ignored.discard(path)

    def clear_pending(self):
        """Clear all pending requests."""
        with self._lock:
            self._pending.clear()
            self._ignored.clear()
            self._latest_id.clear()
            self._latest_params.clear()

    def shutdown(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.io_pool.shutdown(wait=False, cancel_futures=True)  # type: ignore
        except TypeError:
            self.io_pool.shutdown(wait=False)
