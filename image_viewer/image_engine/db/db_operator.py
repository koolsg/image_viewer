from __future__ import annotations

import contextlib
import queue
import sqlite3
import threading
import time
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
    """

    def __init__(self, db_path: Path | str, busy_timeout_ms: int = 5000):
        self._db_path = Path(db_path)
        self._queue: queue.Queue[_DbTask] = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._stop_event = threading.Event()
        self._busy_timeout_ms = int(busy_timeout_ms)
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

    def schedule_write(self, fn: Callable[[sqlite3.Connection, Any], Any], *args, retries: int = 3, **kwargs) -> Future:
        fut: Future = Future()
        task = _DbTask(fn=fn, args=args, kwargs=kwargs, future=fut, retries=retries)
        self._queue.put(task)
        metrics.inc("db_operator.write_queued")
        return fut

    def schedule_write_batch(
        self, funcs: list[tuple[Callable[[sqlite3.Connection, Any], Any], tuple, dict]], retries: int = 3
    ) -> Future:
        """Schedule a batch of write functions to be executed inside a single transaction.

        funcs: list of tuples (fn, args, kwargs)
        """
        fut: Future = Future()

        def _batch(conn):
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

    def _worker(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                task: _DbTask = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
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
                        task.future.set_exception(exc)
                        break
                    finally:
                        if conn:
                            with contextlib.suppress(Exception):
                                conn.close()
            finally:
                self._queue.task_done()

    def shutdown(self, wait: bool = True) -> None:
        self._stop_event.set()
        if wait:
            self._thread.join(timeout=5)

    def is_alive(self) -> bool:
        return self._thread.is_alive()
