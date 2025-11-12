from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QStackedWidget,
    QWidget,
)

from .logger import get_logger

_logger = get_logger("ui_settings")


class SettingsDialog(QDialog):
    def __init__(self, viewer, parent=None):
        super().__init__(parent or viewer)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.resize(560, 380)
        self._viewer = viewer

        root = QHBoxLayout(self)

        self._nav = QListWidget()
        self._nav.setFixedWidth(160)
        self._nav.addItem(QListWidgetItem("Thumbnail"))
        self._nav.addItem(QListWidgetItem("View"))
        root.addWidget(self._nav)

        self._pages = QStackedWidget()
        root.addWidget(self._pages, 1)

        # Page: Thumbnail
        self._page_thumb = QWidget()
        form = QFormLayout(self._page_thumb)

        self._spin_thumb_w = QSpinBox()
        self._spin_thumb_w.setRange(32, 1024)
        self._spin_thumb_w.setSingleStep(8)

        self._spin_thumb_h = QSpinBox()
        self._spin_thumb_h.setRange(32, 1024)
        self._spin_thumb_h.setSingleStep(8)

        self._spin_hspacing = QSpinBox()
        self._spin_hspacing.setRange(0, 64)

        form.addRow(QLabel("Thumbnail Width (px)"), self._spin_thumb_w)
        form.addRow(QLabel("Thumbnail Height (px)"), self._spin_thumb_h)
        form.addRow(QLabel("Thumbnail Horizontal Spacing"), self._spin_hspacing)

        self._pages.addWidget(self._page_thumb)

        # Placeholder Page: View (for future expansion)
        self._page_view = QWidget()
        self._pages.addWidget(self._page_view)

        # Navigation behavior
        self._nav.currentRowChanged.connect(self._pages.setCurrentIndex)
        self._nav.setCurrentRow(0)

        # Initialize from settings/grid
        self._init_values()

        # Apply on change immediately
        self._spin_thumb_w.valueChanged.connect(self._on_thumb_changed)
        self._spin_thumb_h.valueChanged.connect(self._on_thumb_changed)
        self._spin_hspacing.valueChanged.connect(self._on_thumb_changed)

    def _init_values(self):
        try:
            width = 256
            height = 195
            hspacing = 10

            grid = getattr(self._viewer.explorer_state, "_explorer_grid", None)
            if grid and hasattr(grid, "get_thumbnail_size"):
                s = grid.get_thumbnail_size()
                if isinstance(s, tuple) and len(s) == 2:
                    width, height = s[0], s[1]
            if grid and hasattr(grid, "get_horizontal_spacing"):
                hs = grid.get_horizontal_spacing()
                if isinstance(hs, int):
                    hspacing = hs

            # Fallback to persisted settings (back-compat: thumbnail_size)
            width = int(
                self._viewer._settings.get("thumbnail_width", self._viewer._settings.get("thumbnail_size", width))
            )
            height = int(
                self._viewer._settings.get("thumbnail_height", self._viewer._settings.get("thumbnail_size", height))
            )
            hspacing = int(self._viewer._settings.get("thumbnail_hspacing", hspacing))

            self._spin_thumb_w.setValue(width)
            self._spin_thumb_h.setValue(height)
            self._spin_hspacing.setValue(hspacing)
        except Exception as ex:
            _logger.debug("init settings failed: %s", ex)

    def _on_thumb_changed(self, *_):
        try:
            width = int(self._spin_thumb_w.value())
            height = int(self._spin_thumb_h.value())
            hspacing = int(self._spin_hspacing.value())
            if hasattr(self._viewer, "apply_thumbnail_settings"):
                self._viewer.apply_thumbnail_settings(width=width, height=height, hspacing=hspacing)
        except Exception as ex:
            _logger.debug("apply settings failed: %s", ex)
