from __future__ import annotations

import contextlib
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from image_viewer.image_engine.decoder import get_image_dimensions
from image_viewer.infra.logger import get_logger
from image_viewer.trim.trim import apply_trim_to_file, detect_trim_box_stats
from image_viewer.ui.styles import apply_theme

_logger = get_logger("ui_trim")


class TrimBatchWorker(QObject):
    progress = Signal(str, int, int, str)  # path, index (1-based), total, error
    # Emit path, target_width, target_height (0,0 means no trim detected)
    trim_info = Signal(str, int, int)
    finished = Signal()

    def __init__(self, paths: list[str], profile: str):
        super().__init__()
        self.paths = paths
        self.profile = (profile or "normal").lower()
        # Collect report rows: (path, orig_w, orig_h, trim_w, trim_h)
        self.report_rows: list[tuple[str, int, int, int, int]] = []

    def run(self) -> None:
        try:
            total = len(self.paths)
            for idx, p in enumerate(self.paths, start=1):
                err = None
                try:
                    result = detect_trim_box_stats(p, profile=self.profile)
                    if result:
                        _left, _top, width, height = result
                        # Emit info for UI: target resolution
                        with contextlib.suppress(Exception):
                            self.trim_info.emit(p, width, height)
                        # Skip saving if crop equals original image dimensions
                        orig_w, orig_h = get_image_dimensions(p)
                        if orig_w is None:
                            orig_w = 0
                        if orig_h is None:
                            orig_h = 0
                        # Register row for report
                        self.report_rows.append((p, orig_w, orig_h, width, height))
                        if orig_w is not None and orig_h is not None and width == orig_w and height == orig_h:
                            _logger.debug("ui_trim: skipping %s (crop equals original size)", p)
                        else:
                            apply_trim_to_file(p, result, overwrite=False)  # Save as copy
                    else:
                        # No crop detected - inform UI
                        with contextlib.suppress(Exception):
                            self.trim_info.emit(p, 0, 0)
                        # Ensure original dims are in report rows (no trim)
                        orig_w, orig_h = get_image_dimensions(p)
                        if orig_w is None:
                            orig_w = 0
                        if orig_h is None:
                            orig_h = 0
                        self.report_rows.append((p, orig_w, orig_h, 0, 0))
                except Exception as ex:  # keep worker resilient
                    err = str(ex)
                self.progress.emit(p, idx, total, err)
        finally:
            self.finished.emit()


# No use but for later.
class TrimProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trimming in progress...")
        self.setModal(True)
        try:
            layout = QVBoxLayout(self)
            self._label_summary = QLabel("Waiting...", self)
            self._label_file = QLabel("", self)
            self._bar = QProgressBar(self)
            self._bar.setRange(0, 100)
            self._bar.setValue(0)
            layout.addWidget(self._label_summary)
            layout.addWidget(self._label_file)
            layout.addWidget(self._bar)
        except Exception:
            pass

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        # Center on screen (only if possible)
        try:
            screen = QApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                center = geo.center()
                self.move(center - self.rect().center())
        except Exception:
            # Ignore positioning failure (use default placement)
            pass

    @Slot(int, int, str)
    def on_progress(self, total: int, index: int, name: str) -> None:
        try:
            self._label_summary.setText(f"Processing {index} of {total}")
            self._label_file.setText(name)
            pct = int(index * 100 / max(1, total))
            self._bar.setValue(pct)
        except Exception:
            pass


class TrimReportDialog(QDialog):
    """Dialog that shows a table of files and original vs trimmed resolutions.

    The OK button is disabled until `populate` completes, which should be
    called after the batch operation finishes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trim Report")
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.resize(540, 480)

        layout = QVBoxLayout(self)
        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels(["File", "Original", "Trimmed"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self._table)

        # OK button initially disabled until report is populated
        btn_layout = QHBoxLayout()
        self._ok_btn = QPushButton("OK", self)
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self.accept)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self._ok_btn)
        layout.addLayout(btn_layout)

    def add_row(self, filename: str, orig_w: int, orig_h: int, trim_w: int, trim_h: int) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        self._table.setItem(r, 0, QTableWidgetItem(filename))
        self._table.setItem(r, 1, QTableWidgetItem(f"{orig_w} x {orig_h}" if orig_w and orig_h else "Unknown"))
        if trim_w and trim_h:
            self._table.setItem(r, 2, QTableWidgetItem(f"{trim_w} x {trim_h}"))
        else:
            self._table.setItem(r, 2, QTableWidgetItem("No trim"))

    def populate(self, rows: list[tuple[str, int, int, int, int]]) -> None:
        for p, ow, oh, tw, th in rows:
            self.add_row(Path(p).name, ow, oh, tw, th)
        # Enable OK button now that the report is complete
        self._ok_btn.setEnabled(True)


class TrimPreviewDialog(QDialog):
    """Dialog to show before/after trim comparison in a separate window."""

    def __init__(self, original_pixmap: QPixmap, trimmed_pixmap: QPixmap, filename: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Trim Preview - {filename}")
        self.setModal(False)  # Non-modal so confirmation dialog can be on top

        # Set window flags for proper display
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint
        )

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
            original_pixmap, "Original", original_pixmap.width(), original_pixmap.height()
        )

        # Right side: Trimmed image
        right_widget = self._create_image_widget(
            trimmed_pixmap, "Trimmed", trimmed_pixmap.width(), trimmed_pixmap.height()
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
                view._pixmap = original_pixmap
                view._pixmap_item.setPixmap(original_pixmap)
                if hasattr(view, "_border_rect"):
                    view._border_rect.setRect(view._pixmap_item.boundingRect())
                view._scene.setSceneRect(view._pixmap_item.boundingRect())
                view.fitInView(view._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

        # Update left label
        left_labels = self.left_widget.findChildren(QLabel)
        if left_labels:
            left_labels[0].setText(f"Original: {original_pixmap.width()} x {original_pixmap.height()}")

        # Find and update right (trimmed) image
        right_views = self.right_widget.findChildren(QGraphicsView)
        if right_views:
            view = right_views[0]
            if hasattr(view, "_scene") and hasattr(view, "_pixmap_item"):
                view._pixmap = trimmed_pixmap
                view._pixmap_item.setPixmap(trimmed_pixmap)
                if hasattr(view, "_border_rect"):
                    view._border_rect.setRect(view._pixmap_item.boundingRect())
                view._scene.setSceneRect(view._pixmap_item.boundingRect())
                view.fitInView(view._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

        # Update right label
        right_labels = self.right_widget.findChildren(QLabel)
        if right_labels:
            right_labels[0].setText(f"Trimmed: {trimmed_pixmap.width()} x {trimmed_pixmap.height()}")

    def showEvent(self, event):
        """Handle show event to fit views after widgets are ready."""
        super().showEvent(event)

        QTimer.singleShot(50, self._fit_all_views)

    def _fit_all_views(self):
        """Fit all graphics views to their content."""
        total_width = self.splitter.width()
        self.splitter.setSizes([total_width // 2, total_width // 2])

        for view in self.findChildren(QGraphicsView):
            if hasattr(view, "_pixmap_item"):
                try:
                    view.fitInView(view._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
                except Exception as e:
                    _logger.debug("failed to fit view: %s", e)

    def _create_image_widget(self, pixmap: QPixmap, title: str, width: int, height: int) -> QWidget:
        """Create a widget containing title, resolution info, and image view."""
        # Use the Qt symbol imported at module level

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title and resolution label
        info_label = QLabel(f"{title}: {width} x {height}")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        info_label.setFont(font)
        layout.addWidget(info_label)

        # Graphics view for displaying the image
        scene = QGraphicsScene(widget)
        view = QGraphicsView(scene)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

        # Add pixmap to scene
        pixmap_item = QGraphicsPixmapItem(pixmap)
        scene.addItem(pixmap_item)

        # Add border around image for clear boundary visibility
        border_rect = scene.addRect(pixmap_item.boundingRect(), QPen(Qt.GlobalColor.red, 3))
        border_rect.setZValue(1)

        # Store references to prevent garbage collection
        view._scene = scene
        view._pixmap_item = pixmap_item
        view._border_rect = border_rect
        view._pixmap = pixmap
        view._original_fit = lambda: view.fitInView(pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

        scene.setSceneRect(pixmap_item.boundingRect())
        layout.addWidget(view)
        widget.setLayout(layout)
        return widget

    def _apply_theme(self, parent):
        """Apply the current theme from parent viewer."""
        try:
            if parent and hasattr(parent, "_settings_manager"):
                theme = parent._settings_manager.get("theme", "dark")
                app = QApplication.instance()
                if app:
                    apply_theme(app, theme)
        except Exception as e:
            _logger.debug("failed to apply theme to preview dialog: %s", e)

    def resizeEvent(self, event):
        """Maintain fit on resize for all views."""
        super().resizeEvent(event)
        for view in self.findChildren(QGraphicsView):
            if hasattr(view, "_original_fit"):
                with contextlib.suppress(Exception):
                    view._original_fit()
