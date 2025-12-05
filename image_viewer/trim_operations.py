"""Trim workflow operations."""

import contextlib
import traceback as _tb

from PySide6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QMessageBox

from .logger import get_logger
from .trim import apply_trim_to_file, detect_trim_box_stats, make_trim_preview
from .ui_trim import TrimBatchWorker, TrimProgressDialog

_logger = get_logger("trim_operations")


def start_trim_workflow(viewer) -> None:
    """Start the trim workflow.

    Handles two modes:
    1. Batch save as copies: parallel processing with progress dialog
    2. Overwrite existing: file-by-file confirmation with preview

    Args:
        viewer: The ImageViewer instance
    """
    # Prevent re-entry/duplicate execution
    if viewer.trim_state.is_running:
        _logger.debug("trim workflow already running")
        return
    viewer.trim_state.is_running = True
    try:
        if not viewer.image_files:
            return

        # 0) Select trim sensitivity profile (Normal/Aggressive)
        prof_box = QMessageBox(viewer)
        prof_box.setWindowTitle("Trim Sensitivity")
        prof_box.setText("Which profile to use for trimming?")
        btn_norm = prof_box.addButton("Normal", QMessageBox.ButtonRole.AcceptRole)
        btn_agg = prof_box.addButton("Aggressive", QMessageBox.ButtonRole.ActionRole)
        btn_cancel = prof_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        prof_box.setDefaultButton(btn_norm)
        prof_box.exec()
        clicked_prof = prof_box.clickedButton()
        if clicked_prof is btn_cancel or clicked_prof is None:
            return
        profile = "aggressive" if clicked_prof is btn_agg else "normal"

        # 1) Select save mode (Overwrite/Save Copy/Cancel)
        mode_box = QMessageBox(viewer)
        mode_box.setWindowTitle("Trim")
        mode_box.setText(
            "Trimming will be done using the Stats method.\n(Overwrite, Save as Copy, Cancel)"
        )
        overwrite_btn = mode_box.addButton(
            "Overwrite", QMessageBox.ButtonRole.AcceptRole
        )
        _saveas_btn = mode_box.addButton(
            "Save Copy (_trimmed)", QMessageBox.ButtonRole.ActionRole
        )
        cancel_btn = mode_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        mode_box.setDefaultButton(overwrite_btn)
        mode_box.exec()
        clicked = mode_box.clickedButton()
        if clicked is cancel_btn or clicked is None:
            return
        overwrite = clicked is overwrite_btn

        if not overwrite:
            # Save as copy: batch process in a background thread + progress dialog
            paths = list(viewer.image_files)
            dlg = TrimProgressDialog(viewer)

            # Synchronous processing
            worker = TrimBatchWorker(paths, profile)

            def _on_progress(total: int, index: int, name: str):
                dlg.on_progress(total, index, name)

            worker.progress.connect(_on_progress)
            worker.finished.connect(dlg.accept)
            worker.run()
            dlg.exec()
            viewer.maintain_decode_window()
            return

        # Overwrite: per-file approval (preview + Y/N/A shortcuts)
        stop_all = False
        for path in list(viewer.image_files):
            if stop_all:
                break
            try:
                crop = detect_trim_box_stats(path, profile=profile)
            except Exception:
                crop = None
            if not crop:
                continue
            preview_array = make_trim_preview(path, crop)
            if preview_array is None:
                continue

            # Convert numpy array to QPixmap
            try:
                h, w, c = preview_array.shape
                if c == 3:
                    qimg = QImage(preview_array.data, w, h, w * 3, QImage.Format.Format_RGB888)
                elif c == 4:
                    qimg = QImage(preview_array.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
                else:
                    _logger.error("unsupported channel count: %d", c)
                    continue
                preview = QPixmap.fromImage(qimg)
            except Exception as e:
                _logger.error("failed to convert preview to pixmap: %s", e)
                continue

            prev_pix = (
                viewer.canvas._pix_item.pixmap() if viewer.canvas._pix_item else None
            )
            try:
                viewer.trim_state.in_preview = True
                viewer.canvas.set_pixmap(preview)
                viewer.canvas._preset_mode = "fit"
                viewer.canvas.apply_current_view()
            except Exception as e:
                _logger.error("trim preview display error: %s", e)

            box = QMessageBox(viewer)
            box.setWindowTitle("Trim")
            box.setText("Trim this image? (Y/N)")
            yes = box.addButton("Accept (Y)", QMessageBox.ButtonRole.YesRole)
            no = box.addButton("Reject (N)", QMessageBox.ButtonRole.NoRole)
            abort_btn = box.addButton(
                "Abort (A)", QMessageBox.ButtonRole.RejectRole
            )
            # Add Y/N/A shortcuts: trigger button clicks with shortcuts
            try:
                sc_y = QShortcut(QKeySequence("Y"), box)
                sc_n = QShortcut(QKeySequence("N"), box)
                sc_a = QShortcut(QKeySequence("A"), box)
                sc_y.activated.connect(lambda btn=yes: btn.click())
                sc_n.activated.connect(lambda btn=no: btn.click())
                sc_a.activated.connect(lambda btn=abort_btn: btn.click())
            except Exception:
                pass
            box.setDefaultButton(yes)
            box.exec()
            clicked_btn = box.clickedButton()
            if clicked_btn is abort_btn:
                stop_all = True
                accepted = False
            else:
                accepted = clicked_btn is yes

            # Restore original view
            try:
                if prev_pix and not prev_pix.isNull():
                    viewer.canvas.set_pixmap(prev_pix)
                    viewer.canvas.apply_current_view()
                else:
                    viewer.display_image()
            except Exception as e:
                _logger.error("trim preview restore error: %s", e)
                viewer.display_image()
            finally:
                viewer.trim_state.in_preview = False

            if not accepted:
                continue

            # Log: print state just before overwriting
            _logger.debug("[trim] overwrite prep: %s", path)
            displaying = False
            cached = False

            with contextlib.suppress(Exception):
                displaying = (
                    viewer.current_index >= 0
                    and viewer.current_index < len(viewer.image_files)
                    and viewer.image_files[viewer.current_index] == path
                )

            with contextlib.suppress(Exception):
                cached = path in viewer.pixmap_cache

            _logger.debug(
                "[trim] overwrite start: %s, displaying=%s, cached=%s",
                path,
                displaying,
                cached,
            )

            try:
                apply_trim_to_file(path, crop, overwrite=True)
                _logger.debug("[trim] overwrite ok: %s", path)
            except Exception:
                _logger.debug(
                    "[trim] overwrite error: %s\n%s", path, _tb.format_exc()
                )
                QMessageBox.critical(
                    viewer,
                    "Trim Error",
                    f"Failed to save file: {path}",
                )
                continue

            # Invalidate cache and redisplay if necessary
            with contextlib.suppress(Exception):
                viewer.pixmap_cache.pop(path, None)
            if (
                viewer.current_index >= 0
                and viewer.current_index < len(viewer.image_files)
                and viewer.image_files[viewer.current_index] == path
            ):
                viewer.display_image()

        viewer.maintain_decode_window()
    finally:
        # Release the execution flag
        viewer.trim_state.is_running = False
        _logger.debug("trim workflow finished")
