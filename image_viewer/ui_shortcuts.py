"""Legacy QWidget shortcuts (disabled).

Keyboard shortcuts are handled in QML.
This stub exists only to prevent accidental legacy imports from pulling QWidget
code back into the runtime.
"""

from __future__ import annotations

from .logger import get_logger

_logger = get_logger("ui_shortcuts")


def dispatch_key_event(*_args, **_kwargs) -> bool:
    """Legacy entrypoint kept as a no-op.

    Returns False so callers can continue default processing.
    """

    _logger.debug("dispatch_key_event called but ui_shortcuts is disabled (QML-first)")
    return False


def __getattr__(name: str):  # pragma: no cover
    _logger.error("legacy import attempted: ui_shortcuts.%s", name)
    raise AttributeError(name)
