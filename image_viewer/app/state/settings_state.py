from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal


class SettingsState(QObject):
    """User/UX settings that QML binds to."""

    fastViewEnabledChanged = Signal(bool)
    backgroundColorChanged = Signal(str)
    pressZoomMultiplierChanged = Signal(float)
    thumbnailWidthChanged = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fast_view_enabled = False
        self._background_color = "#000000"
        self._press_zoom_multiplier = 3.0
        self._thumbnail_width = 220

    def _get_fast_view_enabled(self) -> bool:
        return bool(self._fast_view_enabled)

    fastViewEnabled = Property(bool, _get_fast_view_enabled, notify=fastViewEnabledChanged)  # type: ignore[arg-type]

    def _get_background_color(self) -> str:
        return str(self._background_color)

    backgroundColor = Property(str, _get_background_color, notify=backgroundColorChanged)  # type: ignore[arg-type]

    def _get_press_zoom_multiplier(self) -> float:
        return float(self._press_zoom_multiplier)

    pressZoomMultiplier = Property(float, _get_press_zoom_multiplier, notify=pressZoomMultiplierChanged)  # type: ignore[arg-type]

    def _get_thumbnail_width(self) -> int:
        return int(self._thumbnail_width)

    thumbnailWidth = Property(int, _get_thumbnail_width, notify=thumbnailWidthChanged)  # type: ignore[arg-type]

    # ---- internal mutation helpers (called by backend) ----
    def _set_fast_view_enabled(self, enabled: bool) -> None:
        v = bool(enabled)
        if v == self._fast_view_enabled:
            return
        self._fast_view_enabled = v
        self.fastViewEnabledChanged.emit(v)

    def _set_background_color(self, color: str) -> None:
        c = str(color).strip()
        if not c or c == self._background_color:
            return
        self._background_color = c
        self.backgroundColorChanged.emit(c)

    def _set_press_zoom_multiplier(self, value: float) -> None:
        v = float(value)
        if v <= 0:
            v = 3.0
        if v == self._press_zoom_multiplier:
            return
        self._press_zoom_multiplier = v
        self.pressZoomMultiplierChanged.emit(v)

    def _set_thumbnail_width(self, width: int) -> None:
        w = int(max(64, min(1024, int(width))))
        if w == self._thumbnail_width:
            return
        self._thumbnail_width = w
        self.thumbnailWidthChanged.emit(w)
