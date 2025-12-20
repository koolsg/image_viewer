import contextlib

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget


class DebugOverlay(QLabel):
    """Small translucent overlay that shows transient debug messages in the view's bottom-left

    Specialized for the crop dialog (keeps messages concise and numeric so the overlay can be
    used for quick interactive debugging).
    """

    def __init__(self, parent_viewport: QWidget):
        super().__init__(parent_viewport)
        self.setFixedSize(280, 48)
        style = (
            "background-color: rgba(0, 0, 0, 180); color: #ffffff; "
            "border-radius: 6px; padding-left: 8px; padding-right: 8px;"
        )
        self.setStyleSheet(style)
        font = self.font()
        font.setPointSize(9)
        with contextlib.suppress(Exception):
            font.setFamily("Courier New")
        self.setFont(font)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.hide()

        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.setInterval(50)
        self._pending_message: str | None = None
        self._throttle_timer.timeout.connect(self._apply_pending)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(1800)
        self._hide_timer.timeout.connect(self.hide)

    def _apply_pending(self) -> None:
        if self._pending_message is not None:
            self.setText(self._pending_message)
            self._pending_message = None
        self._hide_timer.start()

    def show_message(self, msg: str) -> None:
        try:
            if not self.isVisible():
                self.show()
            if self._throttle_timer.isActive():
                self._pending_message = msg
                return
            self.setText(msg)
            self._hide_timer.start()
            self._throttle_timer.start()
        except Exception:
            pass

    def reposition(self) -> None:
        try:
            parent = self.parentWidget()
            if parent is None:
                return
            ph = parent.height()
            x = 12
            y = ph - self.height() - 12
            self.move(x, y)
        except Exception:
            pass


class ViewportWatcher(QObject):
    def __init__(self, overlay: DebugOverlay, parent: QObject | None = None):
        super().__init__(parent)
        self._overlay = overlay

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore
        try:
            if event.type() == QEvent.Resize:
                QTimer.singleShot(0, self._overlay.reposition)
        except Exception:
            pass
        return False
