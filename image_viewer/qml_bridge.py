from __future__ import annotations

import base64
import inspect
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from PySide6.QtGui import QPixmap


class AppController(QObject):
    """Minimal QML POC controller.

    This is intentionally small and test-driven:
    - Tracks a current path and a monotonically increasing generation.
    - Requests preview decodes via the existing ImageEngine.
    - Converts received QPixmap previews to a PNG data URL.
    """

    imageReady = Signal(str, object, int)  # path, payload (data-url), generation

    def __init__(self, engine: Any | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self.currentPath: str = ""
        self.zoom: float = 1.0
        self._generation: int = 0
        self._image_data_url: str = ""

    # ---- API used by tests / QML ----

    def currentGeneration(self) -> int:
        return int(self._generation)

    def setCurrentPathSlot(self, path: str) -> None:
        self.currentPath = str(path)
        self._generation += 1

    def requestPreview(self, path: str, size: int) -> None:
        """Ask the engine to decode a square preview for `path`."""
        if not self._engine:
            return

        target = (int(size), int(size))

        # NOTE: Some unit tests monkeypatch engine.request_decode using MethodType
        # but provide a function that does not accept `self`. To be resilient,
        # inspect the underlying function signature.
        meth = getattr(self._engine, "request_decode", None)
        if meth is None:
            return

        func = getattr(meth, "__func__", None)
        if func is not None:
            try:
                params = list(inspect.signature(func).parameters)
            except Exception:
                params = []
            if params and params[0] != "self":
                func(str(path), target)  # type: ignore[misc]
                return

        # Normal (bound) instance method path
        meth(str(path), target)

    def getImageDataUrl(self) -> str:
        return self._image_data_url

    # ---- Integration hook for the main window ----

    def on_engine_image_ready(self, path: str, pixmap: QPixmap, error: object | None) -> None:
        if error is not None:
            return
        if not path:
            return
        if self.currentPath and str(path) != self.currentPath:
            return

        self._image_data_url = _pixmap_to_png_data_url(pixmap)
        self.imageReady.emit(str(path), self._image_data_url, self.currentGeneration())


def _pixmap_to_png_data_url(pixmap: QPixmap) -> str:
    """Encode a QPixmap as a PNG data URL (base64)."""
    try:
        image = pixmap.toImage()
        # Use Qt to save as PNG into an in-memory byte array
        from PySide6.QtCore import QBuffer, QByteArray  # noqa: PLC0415

        ba = QByteArray()
        qbuf = QBuffer(ba)
        qbuf.open(QBuffer.OpenModeFlag.WriteOnly)
        # Stubs expect a bytes-like format
        image.save(qbuf, b"PNG")
        raw = bytes(ba)
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        # Fallback: empty data URL
        return "data:image/png;base64,"
