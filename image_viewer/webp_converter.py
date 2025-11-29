"""WebP batch converter with resize and optional delete.

This module provides a QRunnable-based worker for converting images to WebP
without blocking the UI. It intentionally stays dependency-light (pyvips only).
"""

from __future__ import annotations

import math
import threading
from pathlib import Path

import pyvips  # type: ignore
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

VALID_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".gif"}


def _iter_images(folder: Path) -> list[Path]:
    return [p for p in folder.rglob("*") if p.suffix.lower() in VALID_EXTS]


def _format_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0B"
    if size_bytes < 0:
        raise ValueError("size_bytes must be non-negative")
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = math.floor(math.log(size_bytes, 1024))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


class ConvertSignals(QObject):
    progress = Signal(int, int)  # completed, total
    log = Signal(str)
    finished = Signal(int, int)  # converted_count, total_count
    canceled = Signal()
    error = Signal(str)


class ConvertTask(QRunnable):
    def __init__(
        self,
        folder: Path,
        should_resize: bool = True,
        target_short: int = 2160,
        quality: int = 90,
        delete_original: bool = True,
    ):
        super().__init__()
        self.folder = folder
        self.should_resize = should_resize
        self.target_short = target_short
        self.quality = quality
        self.delete_original = delete_original
        self.signals = ConvertSignals()
        self._cancel = threading.Event()

    @Slot()
    def run(self) -> None:  # type: ignore[override]
        try:
            images = _iter_images(self.folder)
        except Exception as ex:
            self.signals.error.emit(f"Failed to scan folder: {ex}")
            return

        total = len(images)
        if total == 0:
            self.signals.finished.emit(0, 0)
            return

        converted = 0
        for idx, img_path in enumerate(images, 1):
            if self._cancel.is_set():
                self.signals.canceled.emit()
                return
            try:
                msg, ok = self._convert_single(img_path)
                self.signals.log.emit(msg)
                if ok:
                    converted += 1
            except Exception as ex:
                self.signals.log.emit(f"[X] {img_path.name}: {ex}")
            self.signals.progress.emit(idx, total)

        self.signals.finished.emit(converted, total)

    def cancel(self) -> None:
        self._cancel.set()

    def _convert_single(self, img_path: Path) -> tuple[str, bool]:
        # Skip unsupported or existing targets
        if img_path.suffix.lower() not in VALID_EXTS:
            return f"[ ] Skip (ext): {img_path.name}", False

        output_path = img_path.with_suffix(".webp")
        if output_path.exists():
            return f"[ ] Exists: {output_path.name}", False

        # Load with autorotate for JPEG
        if img_path.suffix.lower() in {".jpg", ".jpeg"}:
            image = pyvips.Image.new_from_file(str(img_path), autorotate=True)
        else:
            image = pyvips.Image.new_from_file(str(img_path))

        w, h = image.width, image.height
        short_side = min(w, h)

        if self.should_resize and short_side > self.target_short:
            if w < h:
                new_w = self.target_short
                new_h = int(h * (self.target_short / w))
            else:
                new_h = self.target_short
                new_w = int(w * (self.target_short / h))
            image = image.thumbnail_image(new_w, height=new_h, size=pyvips.Size.FORCE)

        image.write_to_file(str(output_path), Q=self.quality)

        if self.delete_original:
            img_path.unlink(missing_ok=True)

        return f"[✓] {img_path.name} -> {output_path.name} ({_format_size(output_path.stat().st_size)})", True


class ConvertController(QObject):
    progress = Signal(int, int)
    log = Signal(str)
    finished = Signal(int, int)
    canceled = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.pool = QThreadPool.globalInstance()
        self._task: ConvertTask | None = None

    def start(
        self,
        folder: Path,
        should_resize: bool,
        target_short: int,
        quality: int,
        delete_original: bool,
    ) -> None:
        self.cancel()
        task = ConvertTask(
            folder,
            should_resize=should_resize,
            target_short=target_short,
            quality=quality,
            delete_original=delete_original,
        )
        task.signals.progress.connect(self.progress.emit)
        task.signals.log.connect(self.log.emit)
        task.signals.finished.connect(self.finished.emit)
        task.signals.canceled.connect(self.canceled.emit)
        task.signals.error.connect(self.error.emit)
        self._task = task
        self.pool.start(task)

    def cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
