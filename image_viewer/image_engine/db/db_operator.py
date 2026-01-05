from __future__ import annotations

import contextlib
import queue
import sqlite3
import threading
import time
import weakref
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from image_viewer.logger import get_logger

from ..metrics import metrics

_logger = get_logger("db_operator")


@dataclass
class _DbTask:
    fn: Callable[[sqlite3.Connection, Any], Any]
    args: tuple
    kwargs: dict
    future: Future
    retries: int = 3


class DbOperator:
    """Serialized DB operation queue / worker.

    This class owns a single sqlite3 connection and a worker thread that
    executes queued tasks against that connection. It applies basic PRAGMAs
    (WAL, busy_timeout) and retries transient `sqlite3.OperationalError`.

    Instances are tracked in a weak set so tests can ensure all operators are
    shut down cleanly before interpreter exit, preventing native crashes.
    """

    # Weakly-track live instances for test-time cleanup
    _LIVE: weakref.WeakSet[DbOperator] = weakref.WeakSet()

    def __init__(self, db_path: Path | str, busy_timeout_ms: int = 5000):
        # Register instance before starting the worker thread so registrant
        # sees a valid object even if a thread starts immediately.
        DbOperator._LIVE.add(self)
        self._db_path = Path(db_path)
        # Use Any to allow sentinel objects in the queue for shutdown wake-up
        self._queue: queue.Queue[Any] = queue.Queue()
        # Non-daemon thread so we can reliably join on shutdown and avoid
        # interpreter-exit races where C extensions are unloaded while the
        # thread is still running.
        self._thread = threading.Thread(target=self._worker, daemon=False, name="DbOperatorWorker")
        self._thread_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._busy_timeout_ms = int(busy_timeout_ms)
        # Idle timeout (seconds) after which the worker will exit if no tasks.
        self._idle_timeout_sec = 5
        # Sentinel object used to wake the queue when shutting down
        self._sentinel = object()
        self._thread.start()

    def _open_conn(self) -> sqlite3.Connection:
        # Create a fresh connection per task to avoid long locks/held file handles.
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            _logger.debug("PRAGMA journal_mode=WAL failed", exc_info=True)
        try:
            conn.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)}")
        except Exception:
            _logger.debug("PRAGMA busy_timeout failed", exc_info=True)
        return conn

    def _ensure_worker_running(self) -> None:
        with self._thread_lock:
            if not self._thread.is_alive():
                _logger.debug("DbOperator: restarting worker thread")
                self._thread = threading.Thread(target=self._worker, daemon=False, name="DbOperatorWorker")
                self._thread.start()

    def schedule_write(self, fn: Callable[[sqlite3.Connection, Any], Any], *args, retries: int = 3, **kwargs) -> Future:
        fut: Future = Future()
        task = _DbTask(fn=fn, args=args, kwargs=kwargs, future=fut, retries=retries)
        self._queue.put(task)
        metrics.inc("db_operator.write_queued")
        # Ensure worker running to service this task
        try:
            self._ensure_worker_running()
        except Exception:
            _logger.debug("failed to ensure worker running", exc_info=True)
        return fut

    def schedule_write_batch(
        self, funcs: list[tuple[Callable[[sqlite3.Connection, Any], Any], tuple, dict]], retries: int = 3
    ) -> Future:
        """Schedule a batch of write functions to be executed inside a single transaction.

        funcs: list of tuples (fn, args, kwargs)
        """
        fut: Future = Future()

        def _batch(conn: sqlite3.Connection, *_args, **_kwargs) -> None:
            for fn, args, kwargs in funcs:
                fn(conn, *args, **kwargs)

        task = _DbTask(fn=_batch, args=(), kwargs={}, future=fut, retries=retries)
        self._queue.put(task)
        return fut

    def schedule_read(self, fn: Callable[[sqlite3.Connection, Any], Any], *args, **kwargs) -> Future:
        # For now serialize reads as well to keep a single-threaded connection model.
        fut: Future = Future()
        task = _DbTask(fn=fn, args=args, kwargs=kwargs, future=fut, retries=1)
        self._queue.put(task)
        metrics.inc("db_operator.read_queued")
        return fut

    def _worker(self) -> None:  # noqa: PLR0912, PLR0915
        """Worker loop that executes DB tasks.

        The loop is robust to exceptions and recognizes a sentinel object which
        causes an orderly shutdown even when blocked on queue.get()."""
        while True:
            try:
                try:
                    item = self._queue.get(timeout=0.1)
                except queue.Empty:
                    # Check idle timeout: exit worker if nothing to do for a while
                    if self._stop_event.is_set():
                        break
                    if getattr(self, "_idle_timeout_sec", None):
                        # Wait a bit more to accumulate tasks
                        idle_start = time.time()
                        while time.time() - idle_start < self._idle_timeout_sec:
                            try:
                                item = self._queue.get(timeout=0.1)
                                break
                            except queue.Empty:
                                if self._stop_event.is_set():
                                    break
                        else:
                            _logger.debug("DbOperator worker idle timeout; exiting")
                            break
                    continue

                # Recognize sentinel to allow immediate wake-up during shutdown
                if item is self._sentinel:
                    _logger.debug("DbOperator worker received sentinel; exiting")
                    self._queue.task_done()
                    break

                task: _DbTask = item

                attempt = 0
                while True:
                    conn = None
                    try:
                        with metrics.timed("db_operator.task_duration"):
                            conn = self._open_conn()
                            res = task.fn(conn, *task.args, **task.kwargs)
                        # commit after each write attempt to keep DB durable.
                        with contextlib.suppress(Exception):
                            conn.commit()
                        task.future.set_result(res)
                        break
                    except sqlite3.OperationalError as exc:
                        attempt += 1
                        metrics.inc("db_operator.write_retries")
                        if attempt > (task.retries or 0):
                            task.future.set_exception(exc)
                            break
                        backoff = 0.05 * attempt
                        time.sleep(backoff)
                        continue
                    except Exception as exc:
                        _logger.exception("DbOperator task raised exception: %s", exc)
                        try:
                            task.future.set_exception(exc)
                        except Exception:
                            _logger.debug("Failed to set exception on future", exc_info=True)
                        break
                    finally:
                        if conn:
                            with contextlib.suppress(Exception):
                                conn.close()
            except Exception:
                # Log any unexpected errors and continue; avoid letting the
                # thread die silently due to an unhandled exception.
                _logger.exception("Unexpected exception in DbOperator worker loop")
            finally:
                # Ensure queue.task_done is called if a task was processed
                with contextlib.suppress(Exception):
                    self._queue.task_done()

    def shutdown(self, wait: bool = True) -> None:
        """Signal the worker to stop and optionally wait for it to finish."""
        self._stop_event.set()
        # Put sentinel in queue to wake the worker if it's blocked on get().
        try:
            self._queue.put(self._sentinel)
        except Exception:
            _logger.debug("failed to enqueue sentinel", exc_info=True)
        if wait:
            try:
                self._thread.join(timeout=10)
                if self._thread.is_alive():
                    _logger.warning("DbOperator worker did not stop within timeout")
            except Exception:
                _logger.exception("Exception while joining DbOperator worker")
        # Remove from live set
        with contextlib.suppress(Exception):
            DbOperator._LIVE.discard(self)

    @classmethod
    def shutdown_all(cls, wait: bool = True) -> None:
        """Attempt to shutdown all live operators (used by test cleanup)."""
        for op in list(cls._LIVE):
            try:
                op.shutdown(wait=wait)
            except Exception:
                _logger.exception("shutdown_all: failed to shutdown operator")
        # Clear any remaining references
        with contextlib.suppress(Exception):
            cls._LIVE.clear()

    def is_alive(self) -> bool:
        return self._thread.is_alive()
