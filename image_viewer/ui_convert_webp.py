# ruff: noqa: I001,PLR0915
"""WebP conversion dialog for batch processing."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
)

from .logger import get_logger
from .webp_converter import ConvertController

_logger = get_logger("convert_webp")


class WebPConvertDialog(QDialog):
    def __init__(self, parent=None, start_folder: Path | None = None):
        super().__init__(parent)
        self.setWindowTitle("Convert to WebP")
        self.setModal(True)
        self.resize(520, 420)

        self.controller = ConvertController()
        self.controller.progress.connect(self._on_progress)
        self.controller.log.connect(self._append_log)
        self.controller.finished.connect(self._on_finished)
        self.controller.canceled.connect(self._on_canceled)
        self.controller.error.connect(self._on_error)

        self.folder_edit = QLineEdit(str(start_folder) if start_folder else "")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._choose_folder)

        self.resize_cb = QCheckBox("Resize short side to")
        self.resize_cb.setChecked(True)
        self.target_spin = QSpinBox()
        self.target_spin.setRange(256, 8000)
        self.target_spin.setValue(2160)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(50, 100)
        self.quality_spin.setValue(90)
        self.delete_cb = QCheckBox("Delete originals after convert")
        self.delete_cb.setChecked(True)
        warn = QLabel("Warning: originals will be removed when enabled.")
        warn.setStyleSheet("color: #d32f2f; font-weight: bold;")

        form = QFormLayout()
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(browse_btn)
        form.addRow("Folder", folder_row)
        resize_row = QHBoxLayout()
        resize_row.addWidget(self.resize_cb)
        resize_row.addWidget(self.target_spin)
        resize_row.addWidget(QLabel("px"))
        form.addRow("Resize", resize_row)
        form.addRow("Quality", self.quality_spin)
        form.addRow("Delete originals", self.delete_cb)
        form.addRow("", warn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        self.start_btn = QPushButton("Start")
        self.cancel_btn = QPushButton("Cancel")
        self.close_btn = QPushButton("Close")
        self.cancel_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start)
        self.cancel_btn.clicked.connect(self._cancel)
        self.close_btn.clicked.connect(self.close)

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self.start_btn)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.close_btn)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.progress)
        layout.addWidget(self.log_view)
        layout.addLayout(btns)
        self.setLayout(layout)

    def _choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select folder", self.folder_edit.text() or "")
        if path:
            self.folder_edit.setText(path)

    def _start(self):
        folder = Path(self.folder_edit.text()).expanduser()
        if not folder.exists() or not folder.is_dir():
            QMessageBox.warning(self, "Invalid folder", "Please choose a valid folder.")
            return
        should_resize = self.resize_cb.isChecked()
        target = int(self.target_spin.value())
        quality = int(self.quality_spin.value())
        delete_original = self.delete_cb.isChecked()

        self.log_view.clear()
        self.progress.setValue(0)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.controller.start(folder, should_resize, target, quality, delete_original)

    def _cancel(self):
        self.controller.cancel()
        self.cancel_btn.setEnabled(False)

    def _on_progress(self, completed: int, total: int):
        pct = 0 if total == 0 else int(completed * 100 / total)
        self.progress.setValue(pct)

    def _append_log(self, line: str):
        self.log_view.appendPlainText(line)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def _on_finished(self, converted: int, total: int):
        self._append_log(f"Done: {converted}/{total} converted.")
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._restore_cursor()

    def _on_canceled(self):
        self._append_log("Canceled.")
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._restore_cursor()

    def _on_error(self, msg: str):
        self._append_log(msg)
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._restore_cursor()

    def _restore_cursor(self):
        """Restore cursor to normal state (fix for cursor stuck in wait state)."""
        try:
            # Restore all override cursors to ensure clean state
            while QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        except Exception as ex:
            _logger.debug("cursor restore failed: %s", ex)
