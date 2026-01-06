"""Legacy QWidget explorer tree (disabled).

Explorer UI is QML-first. Data should come from `Main` + engine signals/models.
"""

from __future__ import annotations

from .logger import get_logger

_logger = get_logger("ui_explorer_tree")


def disabled(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError("ui_explorer_tree is disabled: use QML explorer")


def __getattr__(name: str):  # pragma: no cover
    _logger.error("legacy import attempted: ui_explorer_tree.%s", name)
    raise AttributeError(name)
