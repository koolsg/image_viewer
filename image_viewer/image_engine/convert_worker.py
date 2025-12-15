"""Worker to convert decoded numpy arrays into QImage on a background thread.

QImage creation from raw buffers can be done off the GUI thread; creating a
QPixmap must be done on the main thread. This worker converts a numpy RGB
array into a `QImage` and emits it back to the engine for finalization.
"""

from typing import Any

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage

_RGB_CHANNELS = 3
_EXPECTED_NDIM = 3


class ConvertWorker(QObject):
    """Background worker that creates QImage objects from numpy arrays."""

    # Emits: path, qimage, error
    image_converted = Signal(str, QImage, object)

    @Slot(str, object, object)
    def convert(self, path: str, image_data: Any, error: object) -> None:
        """Convert a numpy array (H,W,3 uint8) into a QImage.

        Emits `image_converted(path, qimage, error)` on completion. If `error`
        is truthy or `image_data` is None, an empty QImage is emitted with the
        original error.
        """
        if error or image_data is None:
            self.image_converted.emit(path, QImage(), error)
            return

        try:
            # Ensure contiguous C-ordered array
            arr = np.ascontiguousarray(image_data)
            if arr.ndim != _EXPECTED_NDIM or arr.shape[2] < _RGB_CHANNELS:
                raise ValueError("unexpected image array shape")
            height, width = arr.shape[0], arr.shape[1]
            bytes_per_line = _RGB_CHANNELS * width
            # qimage copies the buffer when .copy() is called so we don't
            # keep a reference to the numpy array lifetime across threads.
            qimg = QImage(arr.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).copy()
            self.image_converted.emit(path, qimg, None)
        except Exception as e:  # pragma: no cover - defensive
            self.image_converted.emit(path, QImage(), str(e))
