from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal


class CropState(QObject):
    """State bound by the QML Crop UI.

    Design:
    - Crop rect is stored in normalized coordinates (0..1) relative to the full image.
    - QML may propose rect updates, but Python is authoritative for clamping,
      aspect ratio enforcement, and min-size rules.
    """

    activeChanged = Signal(bool)
    currentPathChanged = Signal(str)
    imageUrlChanged = Signal(str)
    imageWidthChanged = Signal(int)
    imageHeightChanged = Signal(int)

    rectXChanged = Signal(float)
    rectYChanged = Signal(float)
    rectWChanged = Signal(float)
    rectHChanged = Signal(float)

    aspectRatioChanged = Signal(float)
    previewEnabledChanged = Signal(bool)

    zoomChanged = Signal(float)
    fitModeChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._active = False
        self._current_path = ""
        self._image_url = ""
        self._image_w = 0
        self._image_h = 0

        # Normalized rect (0..1)
        self._x = 0.25
        self._y = 0.25
        self._w = 0.5
        self._h = 0.5

        # 0.0 means free (no constraint). Otherwise width/height.
        self._aspect_ratio = 0.0
        self._preview_enabled = False

        self._zoom = 1.0
        self._fit_mode = True

    # ---- read-only properties (mutate via backend) ----
    def _get_active(self) -> bool:
        return bool(self._active)

    active = Property(bool, _get_active, notify=activeChanged)  # type: ignore[arg-type]

    def _get_current_path(self) -> str:
        return str(self._current_path)

    currentPath = Property(str, _get_current_path, notify=currentPathChanged)  # type: ignore[arg-type]

    def _get_image_url(self) -> str:
        return str(self._image_url)

    imageUrl = Property(str, _get_image_url, notify=imageUrlChanged)  # type: ignore[arg-type]

    def _get_image_width(self) -> int:
        return int(self._image_w)

    imageWidth = Property(int, _get_image_width, notify=imageWidthChanged)  # type: ignore[arg-type]

    def _get_image_height(self) -> int:
        return int(self._image_h)

    imageHeight = Property(int, _get_image_height, notify=imageHeightChanged)  # type: ignore[arg-type]

    def _get_x(self) -> float:
        return float(self._x)

    rectX = Property(float, _get_x, notify=rectXChanged)  # type: ignore[arg-type]

    def _get_y(self) -> float:
        return float(self._y)

    rectY = Property(float, _get_y, notify=rectYChanged)  # type: ignore[arg-type]

    def _get_w(self) -> float:
        return float(self._w)

    rectW = Property(float, _get_w, notify=rectWChanged)  # type: ignore[arg-type]

    def _get_h(self) -> float:
        return float(self._h)

    rectH = Property(float, _get_h, notify=rectHChanged)  # type: ignore[arg-type]

    def _get_aspect_ratio(self) -> float:
        return float(self._aspect_ratio)

    aspectRatio = Property(float, _get_aspect_ratio, notify=aspectRatioChanged)  # type: ignore[arg-type]

    def _get_preview_enabled(self) -> bool:
        return bool(self._preview_enabled)

    previewEnabled = Property(bool, _get_preview_enabled, notify=previewEnabledChanged)  # type: ignore[arg-type]

    def _get_zoom(self) -> float:
        return float(self._zoom)

    zoom = Property(float, _get_zoom, notify=zoomChanged)  # type: ignore[arg-type]

    def _get_fit_mode(self) -> bool:
        return bool(self._fit_mode)

    fitMode = Property(bool, _get_fit_mode, notify=fitModeChanged)  # type: ignore[arg-type]

    # ---- internal mutation helpers (called by backend) ----
    def _set_active(self, value: bool) -> None:
        v = bool(value)
        if v == self._active:
            return
        self._active = v
        self.activeChanged.emit(v)

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

    def _set_image_size(self, w: int, h: int) -> None:
        iw = int(w)
        ih = int(h)
        if iw != self._image_w:
            self._image_w = iw
            self.imageWidthChanged.emit(iw)
        if ih != self._image_h:
            self._image_h = ih
            self.imageHeightChanged.emit(ih)

    def _set_rect(self, x: float, y: float, w: float, h: float) -> None:
        nx = float(x)
        ny = float(y)
        nw = float(w)
        nh = float(h)

        if nx != self._x:
            self._x = nx
            self.rectXChanged.emit(nx)
        if ny != self._y:
            self._y = ny
            self.rectYChanged.emit(ny)
        if nw != self._w:
            self._w = nw
            self.rectWChanged.emit(nw)
        if nh != self._h:
            self._h = nh
            self.rectHChanged.emit(nh)

    def _set_aspect_ratio(self, value: float) -> None:
        r = float(value)
        if r == self._aspect_ratio:
            return
        self._aspect_ratio = r
        self.aspectRatioChanged.emit(r)

    def _set_preview_enabled(self, value: bool) -> None:
        v = bool(value)
        if v == self._preview_enabled:
            return
        self._preview_enabled = v
        self.previewEnabledChanged.emit(v)

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
