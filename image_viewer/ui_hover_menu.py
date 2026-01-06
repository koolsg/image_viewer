"""Legacy QWidget hover menu (disabled).

All hover/overlay UI should be implemented in QML.
"""

from __future__ import annotations

from .logger import get_logger

_logger = get_logger("ui_hover_menu")


def disabled(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError("ui_hover_menu is disabled: QML-first UI is in use")


def __getattr__(name: str):  # pragma: no cover
    _logger.error("legacy import attempted: ui_hover_menu.%s", name)
    raise AttributeError(name)
