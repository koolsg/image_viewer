from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .logger import get_logger

_logger = get_logger("ui_settings")


class SettingsDialog(QDialog):
    def __init__(self, viewer, parent=None):  # noqa: PLR0915
        super().__init__(parent or viewer)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.resize(560, 380)
        self._viewer = viewer

        root = QHBoxLayout(self)

        self._nav = QListWidget()
        self._nav.setFixedWidth(160)
        self._nav.addItem(QListWidgetItem("Appearance"))
        self._nav.addItem(QListWidgetItem("Thumbnail"))
        self._nav.addItem(QListWidgetItem("View"))
        root.addWidget(self._nav)

        self._pages = QStackedWidget()

        pages_container = QWidget()
        pages_layout = QVBoxLayout(pages_container)
        pages_layout.setContentsMargins(0, 0, 0, 0)
        pages_layout.addWidget(self._pages, 1)
        root.addWidget(pages_container, 1)

        # Page: Appearance

        self._page_appearance = QWidget()
        appearance_form = QFormLayout(self._page_appearance)

        self._combo_theme = QComboBox()
        self._combo_theme.addItem("Dark", "dark")
        self._combo_theme.addItem("Light", "light")
        appearance_form.addRow(QLabel("Theme"), self._combo_theme)

        self._spin_font_size = QSpinBox()
        self._spin_font_size.setRange(8, 24)
        self._spin_font_size.setSingleStep(1)
        self._spin_font_size.setSuffix(" pt")
        appearance_form.addRow(QLabel("Font Size"), self._spin_font_size)

        self._pages.addWidget(self._page_appearance)

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

        # Hover menu hide delay (milliseconds)
        self._spin_hover_hide_delay = QSpinBox()
        self._spin_hover_hide_delay.setRange(20, 2000)
        self._spin_hover_hide_delay.setSingleStep(10)
        self._spin_hover_hide_delay.setSuffix(" ms")
        view_form.addRow(QLabel("Hover menu hide delay (ms)"), self._spin_hover_hide_delay)

        self._pages.addWidget(self._page_view)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self._btn_apply = QPushButton("Apply && Save")
        self._btn_cancel = QPushButton("Cancel")
        self._btn_apply.setEnabled(False)
        button_row.addWidget(self._btn_apply)
        button_row.addWidget(self._btn_cancel)
        pages_layout.addLayout(button_row)

        # Navigation behavior
        self._nav.currentRowChanged.connect(self._pages.setCurrentIndex)
        self._nav.setCurrentRow(0)

        # Initialize from settings/grid
        self._init_values()
        self._initial_settings = self._collect_settings()
        self._dirty = False

        # Track changes
        self._combo_theme.currentIndexChanged.connect(self._on_setting_changed)
        self._spin_font_size.valueChanged.connect(self._on_setting_changed)
        self._spin_thumb_w.valueChanged.connect(self._on_setting_changed)
        self._spin_thumb_h.valueChanged.connect(self._on_setting_changed)
        self._spin_hspacing.valueChanged.connect(self._on_setting_changed)
        self._spin_press_zoom.valueChanged.connect(self._on_setting_changed)
        self._spin_hover_hide_delay.valueChanged.connect(self._on_setting_changed)

        # Button handlers
        self._btn_apply.clicked.connect(self._on_apply_clicked)
        self._btn_cancel.clicked.connect(self.reject)

    def _init_values(self):
        try:
            # Theme
            theme = str(self._viewer._settings_manager.get("theme", "dark"))
            idx = self._combo_theme.findData(theme)
            if idx >= 0:
                self._combo_theme.setCurrentIndex(idx)

            # Font Size
            font_size = int(self._viewer._settings_manager.get("font_size", 10))
            self._spin_font_size.setValue(font_size)

            width = 256
            height = 195
            hspacing = 10

            grid = getattr(self._viewer.explorer_state, "_explorer_grid", None)
            if grid and hasattr(grid, "get_thumbnail_size"):
                s = grid.get_thumbnail_size()
                if isinstance(s, tuple) and len(s) == 2:  # noqa: PLR2004
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
            self._spin_press_zoom.setValue(float(self._viewer._settings_manager.get("press_zoom_multiplier")))
            # hover hide delay (ms)
            try:
                self._spin_hover_hide_delay.setValue(int(self._viewer._settings_manager.get("hover_hide_delay", 120)))
            except Exception:
                self._spin_hover_hide_delay.setValue(120)
        except Exception as ex:
            _logger.debug("init settings failed: %s", ex)

    def _collect_settings(self) -> dict[str, float | int | str]:
        return {
            "theme": str(self._combo_theme.currentData()),
            "font_size": int(self._spin_font_size.value()),
            "thumbnail_width": int(self._spin_thumb_w.value()),
            "thumbnail_height": int(self._spin_thumb_h.value()),
            "thumbnail_hspacing": int(self._spin_hspacing.value()),
            "press_zoom_multiplier": float(self._spin_press_zoom.value()),
            "hover_hide_delay": int(self._spin_hover_hide_delay.value()),
        }

    def _on_setting_changed(self, *_):
        try:
            current = self._collect_settings()
            self._dirty = current != self._initial_settings
            self._btn_apply.setEnabled(self._dirty)
        except Exception as ex:
            _logger.debug("settings change tracking failed: %s", ex)

    def _on_apply_clicked(self):
        try:
            settings = self._collect_settings()

            # Apply theme
            if hasattr(self._viewer, "apply_theme"):
                self._viewer.apply_theme(str(settings["theme"]), int(settings["font_size"]))

            if hasattr(self._viewer, "apply_thumbnail_settings"):
                self._viewer.apply_thumbnail_settings(
                    width=settings["thumbnail_width"],
                    height=settings["thumbnail_height"],
                    hspacing=settings["thumbnail_hspacing"],
                )
            if hasattr(self._viewer, "set_press_zoom_multiplier"):
                self._viewer.set_press_zoom_multiplier(settings["press_zoom_multiplier"])
            # Apply hover hide delay and persist
            try:
                if hasattr(self._viewer, "_hover_menu") and hasattr(self._viewer, "_save_settings_key"):
                    self._viewer._hover_menu.set_hide_delay(int(settings["hover_hide_delay"]))
                    self._viewer._save_settings_key("hover_hide_delay", int(settings["hover_hide_delay"]))
            except Exception:
                _logger.debug("failed to apply hover_hide_delay")
            self._initial_settings = settings
            self._dirty = False
            self.accept()
        except Exception as ex:
            _logger.debug("apply settings failed: %s", ex)
