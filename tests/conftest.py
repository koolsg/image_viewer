"""Pytest configuration.

This test suite uses PySide6 widgets in multiple modules.

During `--collect-only` (and sometimes during collection/filtering), pytest may
import Qt modules before any fixture creates a `QApplication`, which can produce
Qt warnings (and, on some platforms, an abnormal process exit).

We create a single `QApplication` for the entire session as early as possible
and cleanly shut it down at the end.
"""

from __future__ import annotations

import contextlib
import gc
import os
from typing import Any

from image_viewer.image_engine.db.db_operator import DbOperator

_APP: Any | None = None


def pytest_configure(config) -> None:
    """Ensure a QApplication exists before collecting/running tests."""

    # Force headless/offscreen Qt to avoid OS "Not Responding" when tests create windows.
    # Use an unconditional assignment to avoid flakiness from external env settings
    # (e.g. a developer shell setting QT_QPA_PLATFORM to 'minimal').
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    # Import lazily so non-Qt environments can still import this conftest.
    try:
        from PySide6.QtWidgets import QApplication  # noqa: PLC0415
    except ImportError:
        return

    app = QApplication.instance()
    # Keep a strong ref so it isn't GC'd mid-session; avoid `global` by writing to globals().
    globals()['_APP'] = QApplication([]) if app is None else app


def pytest_sessionfinish(session, exitstatus) -> None:
    """Attempt a clean Qt shutdown to avoid lingering threads at interpreter exit."""

    try:
        from PySide6.QtWidgets import QApplication  # noqa: PLC0415
    except ImportError:
        return

    app = QApplication.instance()
    if app is None:
        return

    # Proactively close and delete any remaining widgets/windows so Qt Quick
    # resources are torn down while the interpreter is still fully alive.
    try:
        for w in QApplication.topLevelWidgets():
            try:
                w.close()
                w.deleteLater()
            except Exception:
                pass
        app.processEvents()
    except Exception:
        pass

    # Request shutdown and pump events once so timers/posted events can settle.
    app.quit()
    app.processEvents()

    # Ensure any live DbOperator instances are shut down before interpreter exit.
    with contextlib.suppress(Exception):
        DbOperator.shutdown_all()

    # Encourage deterministic destruction order.
    try:
        gc.collect()
        app.processEvents()
        gc.collect()
    except Exception:
        pass
