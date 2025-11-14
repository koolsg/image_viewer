from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QShortcut

from .logger import get_logger
from .strategy import FastViewStrategy

if TYPE_CHECKING:
    from .main import ImageViewer

_logger = get_logger("ui_menus")


def build_menus(viewer: "ImageViewer") -> None:
    """Build the menu bar and view menu for the viewer.

    - English UI text
    - Enable/disable items based on current mode
    - Configure action properties attached to viewer
    """
    menu_bar = viewer.menuBar()

    # File menu
    file_menu = menu_bar.addMenu("File(&F)")
    open_action = QAction("Open Folder...(&O)", viewer)
    open_action.setShortcut(QKeySequence("Ctrl+O"))
    open_action.triggered.connect(viewer.open_folder)
    file_menu.addAction(open_action)

    exit_action = QAction("Exit(&X)", viewer)
    exit_action.setShortcut(QKeySequence("Alt+F4"))
    exit_action.triggered.connect(viewer.close)
    file_menu.addAction(exit_action)

    # View menu
    view_menu = menu_bar.addMenu("View(&V)")
    viewer.view_group = QActionGroup(viewer)
    viewer.view_group.setExclusive(True)

    viewer.fit_action = QAction("Fit to Screen(&F)", viewer, checkable=True)
    viewer.fit_action.setShortcut("F")
    viewer.fit_action.setChecked(True)
    viewer.fit_action.triggered.connect(viewer.choose_fit)
    viewer.view_group.addAction(viewer.fit_action)
    view_menu.addAction(viewer.fit_action)

    viewer.actual_action = QAction("Actual Size(&A)", viewer, checkable=True)
    viewer.actual_action.setShortcut("1")
    viewer.actual_action.setChecked(False)
    viewer.actual_action.triggered.connect(viewer.choose_actual)
    viewer.view_group.addAction(viewer.actual_action)
    view_menu.addAction(viewer.actual_action)

    viewer.hq_downscale_action = QAction(
        "High Quality Downscale (Slow)(&Q)", viewer, checkable=True
    )
    viewer.hq_downscale_action.setChecked(False)
    viewer.hq_downscale_action.triggered.connect(viewer.toggle_hq_downscale)
    view_menu.addAction(viewer.hq_downscale_action)
    # Fast view option: Maintain original thumbnail mode behavior
    strategy = getattr(viewer, "decoding_strategy", None)
    is_fast_view = isinstance(strategy, FastViewStrategy)
    viewer.fast_view_action = QAction(
        "Fast View", viewer, checkable=True
    )
    viewer.fast_view_action.setChecked(is_fast_view)
    viewer.fast_view_action.triggered.connect(viewer.toggle_fast_view)
    view_menu.addAction(viewer.fast_view_action)
    viewer.hq_downscale_action.setEnabled(
        is_fast_view and strategy.supports_hq_downscale()
    )

    # Background color submenu
    bg_menu = view_menu.addMenu("Background")
    viewer.bg_black_action = QAction("Black", viewer, checkable=True)
    viewer.bg_white_action = QAction("White", viewer, checkable=True)
    viewer.bg_custom_action = QAction("Custom...", viewer)
    bg_menu.addAction(viewer.bg_black_action)
    bg_menu.addAction(viewer.bg_white_action)
    bg_menu.addAction(viewer.bg_custom_action)
    viewer.bg_black_action.triggered.connect(
        lambda: viewer.set_background_qcolor(QColor(0, 0, 0))
    )
    viewer.bg_white_action.triggered.connect(
        lambda: viewer.set_background_qcolor(QColor(255, 255, 255))
    )
    viewer.bg_custom_action.triggered.connect(viewer.choose_background_custom)
    if hasattr(viewer, "_sync_bg_checks"):
        viewer._sync_bg_checks()

    # Zoom in/out
    zoom_in_action = QAction("Zoom In", viewer)
    zoom_in_action.setShortcut(QKeySequence.ZoomIn)
    zoom_in_action.triggered.connect(lambda: viewer.zoom_by(1.25))
    view_menu.addAction(zoom_in_action)

    zoom_out_action = QAction("Zoom Out", viewer)
    zoom_out_action.setShortcut(QKeySequence.ZoomOut)
    zoom_out_action.triggered.connect(lambda: viewer.zoom_by(0.75))
    view_menu.addAction(zoom_out_action)

    # Trim workflow
    try:
        viewer.trim_action = QAction("Trim...", viewer)
        viewer.trim_action.triggered.connect(viewer.start_trim_workflow)
        view_menu.addAction(viewer.trim_action)
    except Exception as ex:
        _logger.debug("trim menu unavailable: %s", ex)

    # Explorer mode
    viewer.explorer_mode_action = QAction("Explorer Mode(&E)", viewer, checkable=True)
    viewer.explorer_mode_action.setChecked(False)
    viewer.explorer_mode_action.setShortcut("F5")
    viewer.explorer_mode_action.triggered.connect(viewer.toggle_view_mode)
    view_menu.addSeparator()
    view_menu.addAction(viewer.explorer_mode_action)

    # Fullscreen toggle (no default shortcut; use menu or Esc)
    viewer.fullscreen_action = QAction("Fullscreen", viewer, checkable=True)
    viewer.fullscreen_action.triggered.connect(viewer.toggle_fullscreen)
    view_menu.addAction(viewer.fullscreen_action)

    # Keyboard shortcuts (QShortcut: window-wide, similar to ApplicationShortcut)
    try:
        viewer._shortcut_next = QShortcut(QKeySequence(Qt.Key_Right), viewer)
        viewer._shortcut_next.setContext(Qt.WindowShortcut)
        viewer._shortcut_next.activated.connect(viewer.next_image)

        viewer._shortcut_prev = QShortcut(QKeySequence(Qt.Key_Left), viewer)
        viewer._shortcut_prev.setContext(Qt.WindowShortcut)
        viewer._shortcut_prev.activated.connect(viewer.prev_image)

        viewer._shortcut_first = QShortcut(QKeySequence(Qt.Key_Home), viewer)
        viewer._shortcut_first.setContext(Qt.WindowShortcut)
        viewer._shortcut_first.activated.connect(viewer.first_image)

        viewer._shortcut_last = QShortcut(QKeySequence(Qt.Key_End), viewer)
        viewer._shortcut_last.setContext(Qt.WindowShortcut)
        viewer._shortcut_last.activated.connect(viewer.last_image)

        viewer._shortcut_space = QShortcut(QKeySequence(Qt.Key_Space), viewer)
        viewer._shortcut_space.setContext(Qt.WindowShortcut)
        viewer._shortcut_space.activated.connect(viewer.snap_to_global_view)

        viewer._shortcut_zoom_in = QShortcut(QKeySequence(Qt.Key_Up), viewer)
        viewer._shortcut_zoom_in.setContext(Qt.WindowShortcut)
        viewer._shortcut_zoom_in.activated.connect(lambda: viewer.zoom_by(1.25))

        viewer._shortcut_zoom_out = QShortcut(QKeySequence(Qt.Key_Down), viewer)
        viewer._shortcut_zoom_out.setContext(Qt.WindowShortcut)
        viewer._shortcut_zoom_out.activated.connect(lambda: viewer.zoom_by(0.75))
    except Exception as ex:
        _logger.debug("shortcuts unavailable: %s", ex)

    # Settings menu
    try:
        settings_menu = menu_bar.addMenu("Settings(&S)")
        open_settings_action = QAction("Preferences...", viewer)
        open_settings_action.setShortcut("Ctrl+,")
        open_settings_action.triggered.connect(viewer.open_settings)
        settings_menu.addAction(open_settings_action)
    except Exception as ex:
        _logger.debug("settings menu unavailable: %s", ex)
