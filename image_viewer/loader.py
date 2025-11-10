import os
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Callable

from PySide6.QtCore import QObject, Signal


from .logger import get_logger
_logger = get_logger("loader")

class Loader(QObject):
    """파일 I/O 스케줄링 + 다중 프로세스 디코딩을 관리하는 로더.

    decode_fn은 (path, target_width, target_height, size) -> (path, array|None, error|None)
    형태의 픽클 가능한 최상위 함수를 받아야 한다.
    """

    image_decoded = Signal(str, object, object)  # path, numpy_array, error

    def __init__(self, decode_fn: Callable[[str, int | None, int | None, str], tuple]):
        super().__init__()
        self._decode_fn = decode_fn
        self.executor = ProcessPoolExecutor()
        max_io = max(2, min(4, (os.cpu_count() or 2)))
        self.io_pool = ThreadPoolExecutor(max_workers=max_io)
        self._pending = set()
        self._ignored = set()
        self._next_id = 1
        self._latest_id: dict[str, int] = {}
        self._lock = threading.Lock()

    def _submit_decode(self, file_path: str, target_width: int | None, target_height: int | None, size: str = "both", req_id: int | None = None):
        try:
            future = self.executor.submit(self._decode_fn, file_path, target_width, target_height, size)
            try:
                setattr(future, "_req_id", req_id)
                setattr(future, "_path", file_path)
            except Exception:
                pass
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
            if path in self._ignored:
                return
            latest = self._latest_id.get(path)
            if latest is not None and req_id is not None and req_id != latest:
                return
        self.image_decoded.emit(path, data, error)

    def request_load(self, path, target_width: int | None = None, target_height: int | None = None, size: str = "both"):
        with self._lock:
            if path in self._pending or path in self._ignored:
                return
            self._pending.add(path)
            req_id = self._next_id
            self._next_id += 1
            self._latest_id[path] = req_id
        _logger.debug("request_load path=%s id=%s", path, req_id)
        self.io_pool.submit(self._submit_decode, path, target_width, target_height, size, req_id)

    def ignore_path(self, path: str):
        with self._lock:
            self._ignored.add(path)
            self._pending.discard(path)
            try:
                self._latest_id.pop(path, None)
            except Exception:
                pass

    def unignore_path(self, path: str):
        with self._lock:
            self._ignored.discard(path)

    def shutdown(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.io_pool.shutdown(wait=False, cancel_futures=True)  # type: ignore
        except TypeError:
            self.io_pool.shutdown(wait=False)

