"""Legacy QWidget menus (disabled).

The application is now QML-first (see `image_viewer/main.py` and `image_viewer/qml/`).
All QWidget-based UI modules under `image_viewer/ui_*.py` are intentionally disabled.

If something still imports this module, that code path is legacy and must be removed
or migrated to QML.
"""

from __future__ import annotations

from .logger import get_logger

_logger = get_logger("ui_menus")


def disabled(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError("ui_menus is disabled: QML-first UI is in use")


def __getattr__(name: str):  # pragma: no cover
    _logger.error("legacy import attempted: ui_menus.%s", name)
    raise AttributeError(name)
