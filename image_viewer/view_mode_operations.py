"""Legacy QWidget view-mode operations (disabled).

Deletion/navigation interactions must be handled in QML.
Filesystem deletion semantics are in `image_viewer.file_operations` and
`image_viewer.explorer_file_ops`.
"""

from __future__ import annotations

from .logger import get_logger

_logger = get_logger("view_mode")


def delete_current_file(*_args, **_kwargs) -> None:  # pragma: no cover
    raise RuntimeError("view_mode_operations is disabled: handle view-mode actions in QML")


def __getattr__(name: str):  # pragma: no cover
    _logger.error("legacy import attempted: view_mode_operations.%s", name)
    raise AttributeError(name)
