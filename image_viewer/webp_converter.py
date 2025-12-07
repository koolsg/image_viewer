"""WebP batch converter with resize and optional delete.

This module provides a ProcessPoolExecutor-based worker for converting images to WebP
using true multiprocessing for parallel conversion across CPU cores.
"""

import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pyvips  # type: ignore
from PySide6.QtCore import QObject, QThread, Signal

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


def _convert_single(
    img_path: Path,
    should_resize: bool,
    target_short: int,
    quality: int,
    delete_original: bool,
) -> tuple[str, bool]:
    """Convert a single image to WebP. Must be pickleable for multiprocessing."""
    try:
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

        if should_resize and short_side > target_short:
            if w < h:
                new_w = target_short
                new_h = int(h * (target_short / w))
            else:
                new_h = target_short
                new_w = int(w * (target_short / h))
            image = image.thumbnail_image(new_w, height=new_h, size=pyvips.Size.FORCE)

        image.write_to_file(str(output_path), Q=quality)

        if delete_original:
            img_path.unlink(missing_ok=True)

        return f"[✓] {img_path.name} -> {output_path.name} ({_format_size(output_path.stat().st_size)})", True

    except Exception as ex:
        return f"[X] {img_path.name}: {ex}", False


class ConvertWorker(QThread):
    """Worker thread that manages ProcessPoolExecutor for parallel conversion."""

    progress = Signal(int, int)  # completed, total
    log = Signal(str)
    finished = Signal(int, int)  # converted_count, total_count
    canceled = Signal()
    error = Signal(str)

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
        self._cancel_requested = False

    def run(self) -> None:
        try:
            images = _iter_images(self.folder)
        except Exception as ex:
            self.error.emit(f"Failed to scan folder: {ex}")
            return

        total = len(images)
        if total == 0:
            self.finished.emit(0, 0)
            return

        converted = 0
        completed = 0

        # Use ProcessPoolExecutor for true parallel processing
        max_workers = max(1, os.cpu_count() or 1)

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_path = {
                executor.submit(
                    _convert_single,
                    img_path,
                    self.should_resize,
                    self.target_short,
                    self.quality,
                    self.delete_original,
                ): img_path
                for img_path in images
            }

            # Process results as they complete
            for future in as_completed(future_to_path):
                if self._cancel_requested:
                    # Cancel remaining futures
                    for f in future_to_path:
                        f.cancel()
                    self.canceled.emit()
                    return

                try:
                    msg, ok = future.result()
                    self.log.emit(msg)
                    if ok:
                        converted += 1
                except Exception as ex:
                    img_path = future_to_path[future]
                    self.log.emit(f"[X] {img_path.name}: {ex}")

                completed += 1
                self.progress.emit(completed, total)

        self.finished.emit(converted, total)

    def cancel(self) -> None:
        self._cancel_requested = True


class ConvertController(QObject):
    """Controller for managing WebP conversion with multiprocessing."""

    progress = Signal(int, int)
    log = Signal(str)
    finished = Signal(int, int)
    canceled = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._worker: ConvertWorker | None = None

    def start(
        self,
        folder: Path,
        should_resize: bool,
        target_short: int,
        quality: int,
        delete_original: bool,
    ) -> None:
        """Start conversion with multiprocessing."""
        self.cancel()

        worker = ConvertWorker(
            folder,
            should_resize=should_resize,
            target_short=target_short,
            quality=quality,
            delete_original=delete_original,
        )

        # Connect signals
        worker.progress.connect(self.progress.emit)
        worker.log.connect(self.log.emit)
        worker.finished.connect(self.finished.emit)
        worker.finished.connect(self._on_worker_finished)
        worker.canceled.connect(self.canceled.emit)
        worker.error.connect(self.error.emit)

        self._worker = worker
        worker.start()

    def cancel(self) -> None:
        """Cancel the current conversion."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(1000)  # Wait up to 1 second
            self._worker = None

    def _on_worker_finished(self) -> None:
        """Clean up worker after completion."""
        self._worker = None
