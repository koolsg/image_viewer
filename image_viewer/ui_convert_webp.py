"""Legacy QWidget WebP conversion dialog (disabled).

Tool UIs should be implemented in QML.
Conversion logic remains in `image_viewer/webp_converter.py`.
"""

from __future__ import annotations

from .logger import get_logger

_logger = get_logger("ui_convert_webp")


def disabled(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError("ui_convert_webp is disabled: migrate tool UI to QML")


def __getattr__(name: str):  # pragma: no cover
    _logger.error("legacy import attempted: ui_convert_webp.%s", name)
    raise AttributeError(name)
