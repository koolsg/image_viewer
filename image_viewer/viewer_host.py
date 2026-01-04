from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QVBoxLayout, QWidget


class ViewerHostWidget(QWidget):
    """Minimal Qt Quick host widget (POC).

    The real app can evolve this into an actual QML-backed viewer. For now, this
    object exists to support the QML POC tests:
    - `getQmlSource()` returns a default QML path.
    - Fullscreen is simulated by hiding `container` and tracking `_detached_view`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._detached_view: object | None = None

        self.container = QWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.container)

    def getQmlSource(self) -> str:
        qml = Path(__file__).parent / "qml" / "ViewerPage.qml"
        return str(qml)

    def detach_fullscreen(self) -> None:
        if self._detached_view is not None:
            return
        # Keep it simple for now: tests only check not-None.
        self._detached_view = object()
        self.container.setVisible(False)

    def restore_from_fullscreen(self) -> None:
        if self._detached_view is None:
            return
        self._detached_view = None
        self.container.setVisible(True)
