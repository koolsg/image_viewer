"""Legacy QWidget status overlay builder (disabled).

The current UI is QML-first.
Any overlay/status display should be implemented in QML.
"""

from __future__ import annotations

from .logger import get_logger

_logger = get_logger("status_overlay")


def disabled(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError("status_overlay is disabled: implement overlay in QML")


def __getattr__(name: str):  # pragma: no cover
    _logger.error("legacy import attempted: status_overlay.%s", name)
    raise AttributeError(name)
