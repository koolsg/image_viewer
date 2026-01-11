from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal


class ViewerState(QObject):
    """State bound by the Viewer (View mode) UI."""

    viewModeChanged = Signal(bool)
    currentPathChanged = Signal(str)
    imageUrlChanged = Signal(str)
    zoomChanged = Signal(float)
    fitModeChanged = Signal(bool)
    rotationChanged = Signal(float)
    statusOverlayTextChanged = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._view_mode = False
        self._current_path = ""
        self._image_url = ""
        self._zoom = 1.0
        self._fit_mode = True
        self._rotation = 0.0
        self._status_overlay_text = ""

    # ---- read-only properties (mutate via backend) ----
    def _get_view_mode(self) -> bool:
        return bool(self._view_mode)

    viewMode = Property(bool, _get_view_mode, notify=viewModeChanged)  # type: ignore[arg-type]

    def _get_current_path(self) -> str:
        return str(self._current_path)

    currentPath = Property(str, _get_current_path, notify=currentPathChanged)  # type: ignore[arg-type]

    def _get_image_url(self) -> str:
        return str(self._image_url)

    imageUrl = Property(str, _get_image_url, notify=imageUrlChanged)  # type: ignore[arg-type]

    def _get_zoom(self) -> float:
        return float(self._zoom)

    zoom = Property(float, _get_zoom, notify=zoomChanged)  # type: ignore[arg-type]

    def _get_fit_mode(self) -> bool:
        return bool(self._fit_mode)

    fitMode = Property(bool, _get_fit_mode, notify=fitModeChanged)  # type: ignore[arg-type]

    def _get_rotation(self) -> float:
        return float(self._rotation)

    rotation = Property(float, _get_rotation, notify=rotationChanged)  # type: ignore[arg-type]

    def _get_status_overlay_text(self) -> str:
        return str(self._status_overlay_text)

    statusOverlayText = Property(str, _get_status_overlay_text, notify=statusOverlayTextChanged)  # type: ignore[arg-type]

    # ---- internal mutation helpers (called by backend) ----
    def _set_view_mode(self, value: bool) -> None:
        v = bool(value)
        if v == self._view_mode:
            return
        self._view_mode = v
        self.viewModeChanged.emit(v)

    def _set_current_path(self, path: str) -> None:
        p = str(path)
        if p == self._current_path:
            return
        self._current_path = p
        self.currentPathChanged.emit(p)

    def _set_image_url(self, url: str) -> None:
        u = str(url)
        if u == self._image_url:
            return
        self._image_url = u
        self.imageUrlChanged.emit(u)

    def _set_zoom(self, value: float) -> None:
        z = float(value)
        if z == self._zoom:
            return
        self._zoom = z
        self.zoomChanged.emit(z)

    def _set_fit_mode(self, value: bool) -> None:
        v = bool(value)
        if v == self._fit_mode:
            return
        self._fit_mode = v
        self.fitModeChanged.emit(v)

    def _set_rotation(self, value: float) -> None:
        r = float(value)
        if r == self._rotation:
            return
        self._rotation = r
        self.rotationChanged.emit(r)

    def _set_status_overlay_text(self, text: str) -> None:
        t = str(text)
        if t == self._status_overlay_text:
            return
        self._status_overlay_text = t
        self.statusOverlayTextChanged.emit(t)
