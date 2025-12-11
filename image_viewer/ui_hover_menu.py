"""Hover drawer menu for View mode.

This module provides a slide-out menu that appears when the mouse
approaches the left edge of the screen in View mode.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, Signal
import contextlib
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from image_viewer.logger import get_logger

_logger = get_logger("hover_menu")


class HoverDrawerMenu(QWidget):
    """A drawer menu that slides in from the left when mouse hovers near the edge."""

    # Signals
    crop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # State - define before _setup_ui()
        self._is_expanded = False
        self._hover_zone_width = 20  # Pixels from left edge to trigger hover
        self._menu_width = 80  # Width of the expanded menu
        # Hide delay in milliseconds when mouse leaves hover zone
        self._hide_delay = 120

        self._setup_ui()
        self._setup_animations()
        self._setup_timers()

    def _setup_ui(self):
        """Setup the UI components."""
        self.setFixedWidth(self._menu_width)
        self.setStyleSheet("""
            HoverDrawerMenu {
                background-color: rgba(40, 40, 40, 200);
                border: 1px solid rgba(80, 80, 80, 150);
                border-radius: 8px;
            }
            QPushButton {
                background-color: rgba(60, 60, 60, 150);
                border: 1px solid rgba(100, 100, 100, 100);
                border-radius: 6px;
                color: white;
                font-size: 12px;
                padding: 8px;
                margin: 2px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 200);
                border: 1px solid rgba(120, 120, 120, 150);
            }
            QPushButton:pressed {
                background-color: rgba(50, 50, 50, 200);
            }
        """)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Crop button
        self._crop_btn = QPushButton("Crop")
        self._crop_btn.setToolTip("Open crop/trim tool")
        self._crop_btn.clicked.connect(self.crop_requested.emit)
        layout.addWidget(self._crop_btn)

        # Add stretch to push buttons to top
        layout.addStretch()

    def _setup_animations(self):
        """Setup slide animations."""
        self._slide_animation = QPropertyAnimation(self, b"pos")
        self._slide_animation.setDuration(200)  # 200ms animation
        self._slide_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _setup_timers(self):
        """Setup hover detection timers."""
        # Timer to delay hiding when mouse leaves
        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_menu)

    def set_parent_size(self, width: int, height: int):
        """Update menu position based on parent size."""
        if not self.parent():
            return

        # Position menu on left edge, vertically centered
        menu_height = min(200, height // 2)  # Adaptive height
        self.setFixedHeight(menu_height)

        # Calculate positions
        self._hidden_x = -self._menu_width + 5  # Mostly hidden, 5px visible
        self._visible_x = 10  # Fully visible with margin

        y = (height - menu_height) // 2

        # Set initial position (hidden)
        self.move(self._hidden_x, y)

    def set_hide_delay(self, ms: int) -> None:
        """Adjust the hide delay for the hover menu in milliseconds."""

        with contextlib.suppress(Exception):
            # Prevent too small values which may cause flicker
            self._hide_delay = max(20, int(ms))

    def check_hover_zone(self, mouse_x: int, mouse_y: int, parent_rect: QRect):
        """Check if mouse is in hover zone and show/hide menu accordingly."""
        if not parent_rect.contains(mouse_x, mouse_y):
            # Mouse outside parent widget
            self._schedule_hide()
            return

        # Check if mouse is in left hover zone
        in_hover_zone = mouse_x <= self._hover_zone_width

        # Check if mouse is over the menu itself
        menu_rect = self.geometry()
        over_menu = menu_rect.contains(mouse_x, mouse_y)

        _logger.debug(
            "check_hover_zone: mouse %d,%d in_hover_zone=%s over_menu=%s parent_rect=%s",
            mouse_x,
            mouse_y,
            in_hover_zone,
            over_menu,
            parent_rect,
        )

        if in_hover_zone or over_menu:
            self._show_menu()
        else:
            self._schedule_hide()

    def _show_menu(self):
        """Show the menu with slide animation."""
        if self._is_expanded:
            return

        self._hide_timer.stop()  # Cancel any pending hide
        self._is_expanded = True

        # Animate to visible position
        self._slide_animation.setStartValue(self.pos())
        # Simplified: just set target position
        target_pos = self.pos()
        target_pos.setX(self._visible_x)
        self._slide_animation.setEndValue(target_pos)
        self._slide_animation.start()

        _logger.debug("showing hover menu")

    def _schedule_hide(self):
        """Schedule menu hiding with delay."""
        if not self._is_expanded:
            return

        # Start timer to hide after configured delay
        self._hide_timer.start(self._hide_delay)

    def _hide_menu(self):
        """Hide the menu with slide animation."""
        if not self._is_expanded:
            return

        self._is_expanded = False

        # Animate to hidden position
        self._slide_animation.setStartValue(self.pos())
        target_pos = self.pos()
        target_pos.setX(self._hidden_x)
        self._slide_animation.setEndValue(target_pos)
        self._slide_animation.start()

        _logger.debug("hiding hover menu")

    def paintEvent(self, event):
        """Custom paint to add subtle visual effects."""
        super().paintEvent(event)

        # Add a subtle left border to indicate it's a slide-out menu
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(Qt.GlobalColor.white)
        pen.setWidth(2)
        painter.setPen(pen)

        # Draw left edge highlight
        painter.drawLine(1, 10, 1, self.height() - 10)

        painter.end()
