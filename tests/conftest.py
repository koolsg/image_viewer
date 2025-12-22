"""Pytest configuration.

This test suite uses PySide6 widgets in multiple modules.

During `--collect-only` (and sometimes during collection/filtering), pytest may
import Qt modules before any fixture creates a `QApplication`, which can produce
Qt warnings (and, on some platforms, an abnormal process exit).

We create a single `QApplication` for the entire session as early as possible
and cleanly shut it down at the end.
"""

from __future__ import annotations

from typing import Any


_APP: Any | None = None


def pytest_configure(config) -> None:  # noqa: ARG001
    """Ensure a QApplication exists before collecting/running tests."""

    # Import lazily so non-Qt environments can still import this conftest.
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return

    global _APP

    app = QApplication.instance()
    if app is None:
        # Keep a strong ref so it isn't GC'd mid-session.
        _APP = QApplication([])
    else:
        _APP = app


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    """Attempt a clean Qt shutdown to avoid lingering threads at interpreter exit."""

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return

    app = QApplication.instance()
    if app is None:
        return

    # Request shutdown and pump events once so timers/posted events can settle.
    app.quit()
    app.processEvents()
