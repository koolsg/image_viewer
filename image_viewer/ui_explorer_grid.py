"""Legacy QWidget explorer grid/detail view (disabled).

Explorer UI is QML-first.

NOTE: File operations (copy/cut/paste/delete) remain available in
`image_viewer.explorer_file_ops` for shared non-UI semantics.
"""

from __future__ import annotations

from .logger import get_logger

_logger = get_logger("ui_explorer_grid")


def disabled(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError("ui_explorer_grid is disabled: use QML explorer")


def __getattr__(name: str):  # pragma: no cover
    _logger.error("legacy import attempted: ui_explorer_grid.%s", name)
    raise AttributeError(name)
