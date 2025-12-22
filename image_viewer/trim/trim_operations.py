"""Trim workflow operations."""

import contextlib
import traceback as _tb
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QThread, Signal

if TYPE_CHECKING:
    import numpy as np
from pathlib import Path

from PySide6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QApplication, QMessageBox

from image_viewer.image_engine.decoder import decode_image, get_image_dimensions
from image_viewer.logger import get_logger
from image_viewer.trim.trim import apply_trim_to_file, detect_trim_box_stats, make_trim_preview
from image_viewer.trim.ui_trim import TrimBatchWorker, TrimPreviewDialog, TrimReportDialog

_logger = get_logger("trim_operations")

# Image channel constants
RGB_CHANNELS = 3
RGBA_CHANNELS = 4


@dataclass
class TrimCandidate:
    """Container for preloaded trim candidate data."""

    path: str
    crop: tuple[int, int, int, int]
    original_pixmap: QPixmap
    trimmed_pixmap: QPixmap
    original_array: "np.ndarray"


class TrimPreloader(QThread):
    """Background thread to preload trim candidates into a queue."""

    candidate_ready = Signal(object)  # Emits TrimCandidate
    finished_loading = Signal()  # Emits when all images processed

    def __init__(self, image_files: list[str], profile: str, max_queue_size: int = 5):
        super().__init__()
        self.image_files = image_files
        self.profile = profile
        self.max_queue_size = max_queue_size
        self._stop_requested = False
        self.queue = deque(maxlen=max_queue_size)

    def stop(self):
        """Request thread to stop."""
        self._stop_requested = True

    def run(self):
        """Preload trim candidates in background."""
        for path in self.image_files:
            if self._stop_requested:
                break

            # Wait if queue is full
            while len(self.queue) >= self.max_queue_size and not self._stop_requested:
                self.msleep(100)

            if self._stop_requested:
                break

            try:
                candidate = self._load_candidate(path)
                if candidate is None:
                    continue

                self.queue.append(candidate)
                self.candidate_ready.emit(candidate)

            except Exception as e:
                _logger.debug("preloader: error processing %s: %s", path, e)
                continue

        self.finished_loading.emit()

    def _load_candidate(self, path: str) -> TrimCandidate | None:
        """Attempt to build a TrimCandidate for a given path, or return None.

        This isolates the complex logic from `run` to reduce branching.
        """
        candidate: TrimCandidate | None = None

        crop = detect_trim_box_stats(path, profile=self.profile)
        if crop:
            _, original_array, _err = decode_image(path)
            if original_array is not None:
                original_pixmap = self._array_to_pixmap(original_array)
                if original_pixmap is not None:
                    preview_array = make_trim_preview(path, crop)
                    if preview_array is not None:
                        trimmed_pixmap = self._array_to_pixmap(preview_array)
                        if trimmed_pixmap is not None:
                            # Skip if no actual trimming
                            h, w, _ = original_array.shape
                            trim_h, trim_w, _ = preview_array.shape
                            if not (trim_w == w and trim_h == h):
                                candidate = TrimCandidate(
                                    path=path,
                                    crop=crop,
                                    original_pixmap=original_pixmap,
                                    trimmed_pixmap=trimmed_pixmap,
                                    original_array=original_array,
                                )

        return candidate

    def _array_to_pixmap(self, arr: "np.ndarray") -> "QPixmap | None":
        """Convert an RGB/RGBA numpy array to a QPixmap. Returns None on unsupported channels.

        Guarded as a separate function to reduce branching complexity in `run`.
        """
        h, w, c = arr.shape
        if c == RGB_CHANNELS:
            qimg = QImage(arr.data, w, h, w * RGB_CHANNELS, QImage.Format.Format_RGB888)
        elif c == RGBA_CHANNELS:
            qimg = QImage(arr.data, w, h, w * RGBA_CHANNELS, QImage.Format.Format_RGBA8888)
        else:
            return None
        return QPixmap.fromImage(qimg)


def _select_trim_profile(viewer) -> str | None:
    """Show dialog to select trim sensitivity profile.

    Returns:
        "normal", "aggressive", or None if cancelled
    """
    prof_box = QMessageBox(viewer)
    prof_box.setWindowTitle("Trim Sensitivity")
    prof_box.setText("Which profile to use for trimming?")
    btn_norm = prof_box.addButton("Normal", QMessageBox.ButtonRole.AcceptRole)
    btn_agg = prof_box.addButton("Aggressive", QMessageBox.ButtonRole.ActionRole)
    btn_cancel = prof_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    prof_box.setDefaultButton(btn_norm)
    prof_box.exec()

    clicked = prof_box.clickedButton()
    if clicked is btn_cancel or clicked is None:
        return None
    return "aggressive" if clicked is btn_agg else "normal"


def _select_save_mode(viewer) -> bool | None:
    """Show dialog to select save mode.

    Returns:
        True for overwrite, False for save copy, None if cancelled
    """
    mode_box = QMessageBox(viewer)
    mode_box.setWindowTitle("Trim")
    mode_box.setText("Trimming will be done using the Stats method.\n(Overwrite, Save as Copy, Cancel)")
    overwrite_btn = mode_box.addButton("Overwrite", QMessageBox.ButtonRole.AcceptRole)
    mode_box.addButton("Save Copy (_trimmed)", QMessageBox.ButtonRole.ActionRole)
    cancel_btn = mode_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    mode_box.setDefaultButton(overwrite_btn)
    mode_box.exec()

    clicked = mode_box.clickedButton()
    if clicked is cancel_btn or clicked is None:
        return None
    return clicked is overwrite_btn


def _run_batch_trim(viewer, profile: str) -> None:
    """Run batch trim as copies with progress dialog."""

    paths = viewer.engine.get_image_files()
    report_dlg = TrimReportDialog(viewer)
    worker = TrimBatchWorker(paths, profile)

    def _on_progress(path: str, index: int, total: int, error: str):
        _logger.debug("trim batch: %s (%d/%d) %s", Path(path).name, index, total, error or "")

    worker.progress.connect(_on_progress)
    worker.trim_info.connect(lambda *a: None)
    worker.run()
    # populate report dialog and show
    report_dlg.populate(worker.report_rows)
    report_dlg.exec()
    viewer.maintain_decode_window()


def _show_trim_confirmation(preview_dialog) -> tuple[bool, bool]:
    """Show confirmation dialog for trimming.

    Returns:
        (accepted, should_abort) tuple
    """

    box = QMessageBox(preview_dialog)
    box.setWindowTitle("Trim")
    box.setText("Trim this image? (Y/N)")
    box.setModal(True)
    yes = box.addButton("Accept (Y)", QMessageBox.ButtonRole.YesRole)
    no_btn = box.addButton("Reject (N)", QMessageBox.ButtonRole.NoRole)
    abort_btn = box.addButton("Abort (A)", QMessageBox.ButtonRole.RejectRole)

    # Add keyboard shortcuts
    try:
        sc_y = QShortcut(QKeySequence("Y"), box)
        sc_n = QShortcut(QKeySequence("N"), box)
        sc_a = QShortcut(QKeySequence("A"), box)
        sc_y.activated.connect(lambda btn=yes: btn.click())
        sc_n.activated.connect(lambda btn=no_btn: btn.click())
        sc_a.activated.connect(lambda btn=abort_btn: btn.click())
    except Exception:
        pass

    box.setDefaultButton(yes)

    # Center on screen
    screen = QApplication.primaryScreen()
    if screen:
        geom = screen.geometry()
        box.adjustSize()
        size = box.size()
        box.move((geom.width() - size.width()) // 2, (geom.height() - size.height()) // 2)

    box.raise_()
    box.activateWindow()
    box.exec()

    clicked = box.clickedButton()
    if clicked is None or clicked is abort_btn:
        return False, True  # Not accepted, should abort
    return clicked is yes, False  # Accepted or rejected, don't abort


def _apply_trim_and_update(viewer, path: str, crop: tuple[int, int, int, int]) -> bool:
    """Apply trim to file and update viewer state.

    Returns:
        True if successful
    """
    engine = viewer.engine

    _logger.debug("[trim] overwrite prep: %s", path)
    displaying = False
    cached = False

    with contextlib.suppress(Exception):
        current_path = engine.get_file_at_index(viewer.current_index)
        displaying = current_path == path

    with contextlib.suppress(Exception):
        cached = engine.is_cached(path)

    _logger.debug("[trim] overwrite start: %s, displaying=%s, cached=%s", path, displaying, cached)

    try:
        # Avoid overwriting if crop equals original image (no-op)
        orig_w, orig_h = get_image_dimensions(path)
        _left, _top, width, height = crop
        if orig_w is not None and orig_h is not None and width == orig_w and height == orig_h:
            _logger.debug("[trim] overwrite skipped (crop equals original size): %s", path)
        else:
            apply_trim_to_file(path, crop, overwrite=True)
        _logger.debug("[trim] overwrite ok: %s", path)
    except Exception:
        _logger.debug("[trim] overwrite error: %s\n%s", path, _tb.format_exc())
        QMessageBox.critical(viewer, "Trim Error", f"Failed to save file: {path}")
        return False

    # Invalidate cache and redisplay if necessary
    with contextlib.suppress(Exception):
        engine.remove_from_cache(path)

    current_path = engine.get_file_at_index(viewer.current_index)
    if current_path == path:
        viewer.display_image()

    return True


def _run_overwrite_trim(viewer, profile: str) -> None:
    """Run overwrite trim with per-file confirmation."""
    # Path available at module level

    engine = viewer.engine
    preview_dialog = None
    preloader = TrimPreloader(engine.get_image_files(), profile, max_queue_size=5)
    preloader_finished = False

    def _on_preloader_finished():
        nonlocal preloader_finished
        preloader_finished = True

    preloader.finished_loading.connect(_on_preloader_finished)
    preloader.start()

    try:
        while True:
            # Wait for queue to have data or preloader to finish
            while len(preloader.queue) == 0 and not preloader_finished:
                QCoreApplication.processEvents()
                preloader.msleep(50)

            # Exit if queue empty and preloader finished
            if len(preloader.queue) == 0:
                if preloader_finished:
                    break
                continue

            candidate = preloader.queue.popleft()

            # Create or update preview dialog
            if preview_dialog is None:
                preview_dialog = TrimPreviewDialog(
                    candidate.original_pixmap, candidate.trimmed_pixmap, Path(candidate.path).name, viewer
                )
                preview_dialog.showMaximized()
            else:
                preview_dialog.update_images(
                    candidate.original_pixmap, candidate.trimmed_pixmap, Path(candidate.path).name
                )
                preview_dialog.raise_()
                preview_dialog.activateWindow()

            # Get user confirmation
            accepted, should_abort = _show_trim_confirmation(preview_dialog)
            if should_abort:
                break
            if not accepted:
                continue

            # Apply trim
            _apply_trim_and_update(viewer, candidate.path, candidate.crop)

    finally:
        preloader.stop()
        preloader.wait(2000)
        if preview_dialog is not None:
            preview_dialog.close()

    viewer.maintain_decode_window()


def start_trim_workflow(viewer) -> None:
    """Start the trim workflow.

    Handles two modes:
    1. Batch save as copies: parallel processing with progress dialog
    2. Overwrite existing: file-by-file confirmation with preview in separate dialog

    Args:
        viewer: The ImageViewer instance
    """
    if viewer.trim_state.is_running:
        _logger.debug("trim workflow already running")
        return

    viewer.trim_state.is_running = True
    try:
        if not viewer.engine.get_image_files():
            return

        # Select profile
        profile = _select_trim_profile(viewer)
        if profile is None:
            return

        # Select save mode
        overwrite = _select_save_mode(viewer)
        if overwrite is None:
            return

        # Run appropriate workflow
        if overwrite:
            _run_overwrite_trim(viewer, profile)
        else:
            _run_batch_trim(viewer, profile)

    finally:
        viewer.trim_state.is_running = False
        _logger.debug("trim workflow finished")
