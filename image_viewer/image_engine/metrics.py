"""Lightweight in-process metrics for development and tests.

This module provides a very small API used by internal components to
record counters and timings. It intentionally avoids external deps so it
can be used in tests and CI without extra setup.

Usage:
    from image_viewer.image_engine.metrics import metrics
    metrics.inc("db_operator.write_attempts")
    with metrics.timed("db_operator.write_duration"):
        ...
    snapshot = metrics.snapshot()
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from threading import RLock
from typing import Any


class _Metrics:
    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._timings: dict[str, list[float]] = defaultdict(list)
        self._lock = RLock()

    def inc(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[key] += int(amount)

    def timed(self, key: str):
        @contextmanager
        def _ctx():
            start = time.perf_counter()
            try:
                yield
            finally:
                elapsed = time.perf_counter() - start
                with self._lock:
                    self._timings[key].append(elapsed)

        return _ctx()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "timings": {k: list(v) for k, v in self._timings.items()},
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._timings.clear()


metrics = _Metrics()
