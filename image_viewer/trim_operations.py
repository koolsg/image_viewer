"""Trim workflow operations."""

import contextlib
import traceback as _tb
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, Signal

if TYPE_CHECKING:
    import numpy as np
from PySide6.QtGui import QFont, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .logger import get_logger
from .trim import apply_trim_to_file, detect_trim_box_stats, make_trim_preview
from .ui_trim import TrimBatchWorker, TrimProgressDialog

_logger = get_logger("trim_operations")


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
                # Detect trim box
                crop = detect_trim_box_stats(path, profile=self.profile)
                if not crop:
                    continue

                # Load original image
                from .decoder import decode_image
                _, original_array, err = decode_image(path)
                if original_array is None:
                    _logger.debug("preloader: failed to load %s: %s", path, err)
                    continue

                # Convert original to QPixmap
                h, w, c = original_array.shape
                if c == 3:
                    qimg_orig = QImage(original_array.data, w, h, w * 3, QImage.Format.Format_RGB888)
                elif c == 4:
                    qimg_orig = QImage(original_array.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
                else:
                    continue
                original_pixmap = QPixmap.fromImage(qimg_orig)

                # Load trimmed preview
                preview_array = make_trim_preview(path, crop)
                if preview_array is None:
                    continue

                # Convert trimmed to QPixmap
                trim_h, trim_w, c = preview_array.shape
                if c == 3:
                    qimg = QImage(preview_array.data, trim_w, trim_h, trim_w * 3, QImage.Format.Format_RGB888)
                elif c == 4:
                    qimg = QImage(preview_array.data, trim_w, trim_h, trim_w * 4, QImage.Format.Format_RGBA8888)
                else:
                    continue
                trimmed_pixmap = QPixmap.fromImage(qimg)

                # Skip if no actual trimming
                if trim_w == w and trim_h == h:
                    _logger.debug("preloader: skipping %s (no trim needed)", path)
                    continue

                # Create candidate and add to queue
                candidate = TrimCandidate(
                    path=path,
                    crop=crop,
                    original_pixmap=original_pixmap,
                    trimmed_pixmap=trimmed_pixmap,
                    original_array=original_array
                )
                self.queue.append(candidate)
                self.candidate_ready.emit(candidate)

            except Exception as e:
                _logger.debug("preloader: error processing %s: %s", path, e)
                continue

        self.finished_loading.emit()


class TrimPreviewDialog(QDialog):
    """Dialog to show before/after trim comparison in a separate window."""

    def __init__(self, original_pixmap: QPixmap, trimmed_pixmap: QPixmap, filename: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Trim Preview - {filename}")
        self.setModal(False)  # Non-modal so confirmation dialog can be on top

        # Set window flags for proper display
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)

        # Apply theme
        self._apply_theme(parent)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Splitter for left/right comparison
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(8)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background: #555555;
                border: 1px solid #333333;
            }
            QSplitter::handle:hover {
                background: #666666;
            }
        """)

        # Left side: Original image
        left_widget = self._create_image_widget(
            original_pixmap,
            "Original",
            original_pixmap.width(),
            original_pixmap.height()
        )

        # Right side: Trimmed image
        right_widget = self._create_image_widget(
            trimmed_pixmap,
            "Trimmed",
            trimmed_pixmap.width(),
            trimmed_pixmap.height()
        )

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)

        main_layout.addWidget(self.splitter)
        self.setLayout(main_layout)

        # Store widget references for updates
        self.left_widget = left_widget
        self.right_widget = right_widget

    def update_images(self, original_pixmap: QPixmap, trimmed_pixmap: QPixmap, filename: str):
        """Update dialog with new images without recreating the window."""
        self.setWindowTitle(f"Trim Preview - {filename}")

        # Find and update left (original) image
        left_views = self.left_widget.findChildren(QGraphicsView)
        if left_views:
            view = left_views[0]
            if hasattr(view, "_scene") and hasattr(view, "_pixmap_item"):
                # Update pixmap
                view._pixmap = original_pixmap
                view._pixmap_item.setPixmap(original_pixmap)
                # Update border
                if hasattr(view, "_border_rect"):
                    view._border_rect.setRect(view._pixmap_item.boundingRect())
                view._scene.setSceneRect(view._pixmap_item.boundingRect())
                view.fitInView(view._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

        # Update left label
        left_labels = self.left_widget.findChildren(QLabel)
        if left_labels:
            left_labels[0].setText(f"Original: {original_pixmap.width()} × {original_pixmap.height()}")

        # Find and update right (trimmed) image
        right_views = self.right_widget.findChildren(QGraphicsView)
        if right_views:
            view = right_views[0]
            if hasattr(view, "_scene") and hasattr(view, "_pixmap_item"):
                # Update pixmap
                view._pixmap = trimmed_pixmap
                view._pixmap_item.setPixmap(trimmed_pixmap)
                # Update border
                if hasattr(view, "_border_rect"):
                    view._border_rect.setRect(view._pixmap_item.boundingRect())
                view._scene.setSceneRect(view._pixmap_item.boundingRect())
                view.fitInView(view._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

        # Update right label
        right_labels = self.right_widget.findChildren(QLabel)
        if right_labels:
            right_labels[0].setText(f"Trimmed: {trimmed_pixmap.width()} × {trimmed_pixmap.height()}")

    def showEvent(self, event):
        """Handle show event to fit views after widgets are ready."""
        super().showEvent(event)
        # Fit all views after a short delay
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self._fit_all_views)

    def _fit_all_views(self):
        """Fit all graphics views to their content."""
        # Set splitter sizes to equal
        total_width = self.splitter.width()
        self.splitter.setSizes([total_width // 2, total_width // 2])

        # Fit each view
        for view in self.findChildren(QGraphicsView):
            if hasattr(view, "_pixmap_item"):
                try:
                    view.fitInView(view._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
                except Exception as e:
                    _logger.debug("failed to fit view: %s", e)

    def _create_image_widget(self, pixmap: QPixmap, title: str, width: int, height: int) -> QWidget:
        """Create a widget containing title, resolution info, and image view."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title and resolution label
        info_label = QLabel(f"{title}: {width} × {height}")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        info_label.setFont(font)
        layout.addWidget(info_label)

        # Graphics view for displaying the image
        scene = QGraphicsScene(widget)  # Set parent to prevent deletion
        view = QGraphicsView(scene)
        from PySide6.QtGui import QPainter
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

        # Add pixmap to scene
        pixmap_item = QGraphicsPixmapItem(pixmap)
        scene.addItem(pixmap_item)

        # Add border around image for clear boundary visibility
        from PySide6.QtCore import Qt as QtCore
        from PySide6.QtGui import QPen
        border_rect = scene.addRect(
            pixmap_item.boundingRect(),
            QPen(QtCore.GlobalColor.red, 3)  # 3px red border
        )
        border_rect.setZValue(1)  # Draw border on top of image

        # Store references to prevent garbage collection
        view._scene = scene
        view._pixmap_item = pixmap_item
        view._border_rect = border_rect
        view._pixmap = pixmap  # Keep pixmap reference
        view._original_fit = lambda: view.fitInView(pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

        # Set scene rect to pixmap bounds
        scene.setSceneRect(pixmap_item.boundingRect())

        layout.addWidget(view)
        widget.setLayout(layout)
        return widget

    def _apply_theme(self, parent):
        """Apply the current theme from parent viewer."""
        try:
            if parent and hasattr(parent, "_settings_manager"):
                theme = parent._settings_manager.get("theme", "dark")
                from PySide6.QtWidgets import QApplication

                from image_viewer.styles import apply_theme
                app = QApplication.instance()
                if app:
                    apply_theme(app, theme)
        except Exception as e:
            _logger.debug("failed to apply theme to preview dialog: %s", e)

    def resizeEvent(self, event):
        """Maintain fit on resize for all views."""
        super().resizeEvent(event)
        # Find all QGraphicsView widgets and refit
        for view in self.findChildren(QGraphicsView):
            if hasattr(view, "_original_fit"):
                try:
                    view._original_fit()
                except Exception:
                    pass


def start_trim_workflow(viewer) -> None:
    """Start the trim workflow.

    Handles two modes:
    1. Batch save as copies: parallel processing with progress dialog
    2. Overwrite existing: file-by-file confirmation with preview in separate dialog

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

            def _on_progress(path: str, index: int, total: int, error: str):
                from pathlib import Path
                dlg.on_progress(total, index, Path(path).name)

            worker.progress.connect(_on_progress)
            worker.finished.connect(dlg.accept)
            worker.run()
            dlg.exec()
            viewer.maintain_decode_window()
            return

        # Overwrite: per-file approval with preloading queue (max 5 images ahead)
        stop_all = False
        preview_dialog = None  # Reuse dialog for all images

        # Start preloader thread
        preloader = TrimPreloader(list(viewer.image_files), profile, max_queue_size=5)
        preloader_finished = False

        def _on_preloader_finished():
            nonlocal preloader_finished
            preloader_finished = True

        preloader.finished_loading.connect(_on_preloader_finished)
        preloader.start()

        # Process candidates from queue
        from pathlib import Path

        from PySide6.QtCore import QCoreApplication

        while not stop_all:
            # Wait for queue to have data or preloader to finish
            while len(preloader.queue) == 0 and not preloader_finished:
                QCoreApplication.processEvents()
                preloader.msleep(50)

            # Exit if queue empty and preloader finished
            if len(preloader.queue) == 0 and preloader_finished:
                break

            # Get next candidate from queue
            if len(preloader.queue) == 0:
                continue

            candidate = preloader.queue.popleft()
            path = candidate.path
            crop = candidate.crop
            original_pixmap = candidate.original_pixmap
            trimmed_pixmap = candidate.trimmed_pixmap
            original_array = candidate.original_array

            # Create or update preview dialog
            if preview_dialog is None:
                preview_dialog = TrimPreviewDialog(original_pixmap, trimmed_pixmap, Path(path).name, viewer)
                preview_dialog.showMaximized()
            else:
                # Update existing dialog with new images
                preview_dialog.update_images(original_pixmap, trimmed_pixmap, Path(path).name)
                preview_dialog.raise_()
                preview_dialog.activateWindow()

            # Ask user for confirmation - parent is preview_dialog to keep it on top
            box = QMessageBox(preview_dialog)
            box.setWindowTitle("Trim")
            box.setText("Trim this image? (Y/N)")
            box.setModal(True)  # Block other operations
            yes = box.addButton("Accept (Y)", QMessageBox.ButtonRole.YesRole)
            _no = box.addButton("Reject (N)", QMessageBox.ButtonRole.NoRole)
            abort_btn = box.addButton(
                "Abort (A)", QMessageBox.ButtonRole.RejectRole
            )
            # Add Y/N/A shortcuts: trigger button clicks with shortcuts
            try:
                sc_y = QShortcut(QKeySequence("Y"), box)
                sc_n = QShortcut(QKeySequence("N"), box)
                sc_a = QShortcut(QKeySequence("A"), box)
                sc_y.activated.connect(lambda btn=yes: btn.click())
                sc_n.activated.connect(lambda btn=_no: btn.click())
                sc_a.activated.connect(lambda btn=abort_btn: btn.click())
            except Exception:
                pass
            box.setDefaultButton(yes)

            # Center dialog on screen
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.geometry()
                box.adjustSize()
                dialog_size = box.size()
                x = (screen_geometry.width() - dialog_size.width()) // 2
                y = (screen_geometry.height() - dialog_size.height()) // 2
                box.move(x, y)

            # Ensure dialog stays on top
            box.raise_()
            box.activateWindow()

            box.exec()
            clicked_btn = box.clickedButton()

            # Handle X button (None) or Abort button as abort
            if clicked_btn is None or clicked_btn is abort_btn:
                stop_all = True
                accepted = False
            else:
                accepted = clicked_btn is yes

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

        # Stop preloader and wait for it to finish
        if 'preloader' in locals():
            preloader.stop()
            preloader.wait(2000)  # Wait up to 2 seconds

        # Close preview dialog at the end
        if preview_dialog is not None:
            preview_dialog.close()
    finally:
        # Release the execution flag
        viewer.trim_state.is_running = False
        _logger.debug("trim workflow finished")
