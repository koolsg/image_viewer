from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal


class TasksState(QObject):
    """State for long-running background tasks.

    Tasks should primarily communicate via backend.taskEvent(dict), but a small
    amount of bindable state is practical for enabling/disabling UI controls.
    """

    webpConvertRunningChanged = Signal(bool)
    webpConvertPercentChanged = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._webp_running = False
        self._webp_percent = 0

    def _get_webp_running(self) -> bool:
        return bool(self._webp_running)

    webpConvertRunning = Property(bool, _get_webp_running, notify=webpConvertRunningChanged)  # type: ignore[arg-type]

    def _get_webp_percent(self) -> int:
        return int(self._webp_percent)

    webpConvertPercent = Property(int, _get_webp_percent, notify=webpConvertPercentChanged)  # type: ignore[arg-type]

    def _set_webp_running(self, running: bool) -> None:
        v = bool(running)
        if v == self._webp_running:
            return
        self._webp_running = v
        self.webpConvertRunningChanged.emit(v)

    def _set_webp_percent(self, percent: int) -> None:
        p = int(max(0, min(100, int(percent))))
        if p == self._webp_percent:
            return
        self._webp_percent = p
        self.webpConvertPercentChanged.emit(p)
