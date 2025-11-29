from __future__ import annotations

import json
import os
from typing import Any

from PySide6.QtGui import QColor

from .logger import get_logger

_logger = get_logger("settings")


class SettingsManager:
    def __init__(self, settings_path: str):
        self.settings_path = settings_path
        self._settings: dict[str, Any] = {}
        self.load()

    DEFAULTS: dict[str, Any] = {
        "background_color": "#000000",
        "fast_view_enabled": False,
        "press_zoom_multiplier": 3.0,
        "thumbnail_width": 256,
        "thumbnail_height": 195,
        "thumbnail_size": 256,
        "thumbnail_hspacing": 10,
        "thumbnail_cache_name": "image_viewer_thumbs",
    }

    def load(self) -> None:
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._settings = data
                        _logger.debug("settings loaded: %s", self.settings_path)
                        return
        except Exception as e:
            _logger.warning("settings load failed: %s", e)
        self._settings = {}

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
            _logger.debug("settings saved: %s", self.settings_path)
        except Exception as e:
            _logger.error("settings save failed: %s", e)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._settings:
            return self._settings[key]
        if default is not None:
            return default
        return self.DEFAULTS.get(key)

    def has(self, key: str) -> bool:
        return key in self._settings

    def set(self, key: str, value: Any) -> None:
        self._settings[key] = value
        self.save()

    @property
    def data(self) -> dict[str, Any]:
        return self._settings

    @property
    def fast_view_enabled(self) -> bool:
        return bool(self.get("fast_view_enabled", False))

    @property
    def last_parent_dir(self) -> str | None:
        val = self.get("last_parent_dir")
        return val if isinstance(val, str) and os.path.isdir(val) else None

    def determine_startup_background(self) -> QColor:
        try:
            hexcol = self.get("background_color")
            if isinstance(hexcol, str):
                color = QColor(hexcol)
                if color.isValid():
                    return color
                _logger.warning("saved background_color invalid: %s", hexcol)
        except Exception as e:
            _logger.warning("failed to parse background_color: %s", e)
        return QColor(0, 0, 0)
