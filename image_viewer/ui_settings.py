"""Legacy QWidget settings dialog (disabled).

Settings UI must be implemented in QML.
Backend settings storage is `image_viewer.settings_manager.SettingsManager`.
"""

from __future__ import annotations

from .logger import get_logger

_logger = get_logger("ui_settings")


def disabled(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError("ui_settings is disabled: migrate settings UI to QML")


def __getattr__(name: str):  # pragma: no cover
    _logger.error("legacy import attempted: ui_settings.%s", name)
    raise AttributeError(name)
