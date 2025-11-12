from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QVBoxLayout

from image_viewer.trim import apply_trim_to_file, detect_trim_box_stats


class TrimBatchWorker(QObject):
    progress = Signal(int, int, str)  # total, index (1-based), filename
    finished = Signal()

    def __init__(self, paths: list[str], profile: str):
        super().__init__()
        self.paths = paths
        self.profile = (profile or "normal").lower()

    def run(self) -> None:
        try:
            total = len(self.paths)
            for idx, p in enumerate(self.paths, start=1):
                err = None
                try:
                    result = detect_trim_box_stats(p, profile=self.profile)
                    if result:
                        apply_trim_to_file(p, result, overwrite=True)
                except Exception as ex:  # keep worker resilient
                    err = str(ex)
                self.progress.emit(p, idx, total, err)
        finally:
            self.finished.emit()


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
