from __future__ import annotations

import os
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar


class TrimBatchWorker(QObject):
    progress = Signal(int, int, str)  # total, index (1-based), filename
    finished = Signal()

    def __init__(self, paths: list[str], profile: str):
        super().__init__()
        self.paths = paths
        self.profile = (profile or "normal").lower()

    @Slot()
    def run(self) -> None:
        try:
            from image_viewer.trim import (
                detect_trim_box_stats,
                apply_trim_to_file,
            )
        except Exception:
            self.finished.emit()
            return
        total = len(self.paths)
        for i, path in enumerate(self.paths, 1):
            try:
                crop = detect_trim_box_stats(path, profile=self.profile)
                if crop:
                    apply_trim_to_file(path, crop, overwrite=False, alg="stats")
            except Exception:
                pass
            try:
                name = os.path.basename(path)
            except Exception:
                name = path
            self.progress.emit(total, i, name)
        self.finished.emit()


class TrimProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("트림 처리 중...")
        self.setModal(True)
        try:
            layout = QVBoxLayout(self)
            self._label_summary = QLabel("대기 중...", self)
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
        try:
            super().showEvent(event)
        except Exception:
            pass
        # 화면 정중앙 배치
        try:
            parent = self.parent()
            if parent is not None and hasattr(parent, 'frameGeometry'):
                pg = parent.frameGeometry()
                center = pg.center()
                self.adjustSize()
                self.move(center - self.rect().center())
            else:
                from PySide6.QtWidgets import QApplication
                screen = QApplication.primaryScreen()
                if screen is not None:
                    center = screen.availableGeometry().center()
                    self.adjustSize()
                    self.move(center - self.rect().center())
        except Exception:
            pass

    @Slot(int, int, str)
    def on_progress(self, total: int, index: int, name: str) -> None:
        try:
            self._label_summary.setText(f"{total}개 중 {index}개 처리 중")
            self._label_file.setText(name)
            pct = int(index * 100 / max(1, total))
            self._bar.setValue(pct)
        except Exception:
            pass

