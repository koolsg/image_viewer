from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
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

        # Placeholder Page: View (for mouse + view tweaks)
        self._page_view = QWidget()
        view_form = QFormLayout(self._page_view)

        self._spin_press_zoom = QDoubleSpinBox()
        self._spin_press_zoom.setRange(1.0, 10.0)
        self._spin_press_zoom.setSingleStep(0.1)
        self._spin_press_zoom.setDecimals(2)
        view_form.addRow(QLabel("Left-click zoom multiplier"), self._spin_press_zoom)

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
        self._spin_press_zoom.valueChanged.connect(self._on_view_changed)

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
            width = int(self._viewer._settings_manager.get("thumbnail_width"))
            height = int(self._viewer._settings_manager.get("thumbnail_height"))
            hspacing = int(self._viewer._settings_manager.get("thumbnail_hspacing"))

            self._spin_thumb_w.setValue(width)
            self._spin_thumb_h.setValue(height)
            self._spin_hspacing.setValue(hspacing)
            self._spin_press_zoom.setValue(
                float(self._viewer._settings_manager.get("press_zoom_multiplier"))
            )
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

    def _on_view_changed(self, *_):
        try:
            if hasattr(self._viewer, "set_press_zoom_multiplier"):
                self._viewer.set_press_zoom_multiplier(float(self._spin_press_zoom.value()))
        except Exception as ex:
            _logger.debug("apply view settings failed: %s", ex)
