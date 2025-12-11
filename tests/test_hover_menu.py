from pathlib import Path
import sys
from PySide6.QtWidgets import QApplication, QWidget

# Ensure repository root is on path (pytest might not add package layout)
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from image_viewer.ui_hover_menu import HoverDrawerMenu
from PySide6.QtTest import QTest


def test_hover_menu_shows_and_hides():
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.resize(200, 200)
    parent.show()

    menu = HoverDrawerMenu(parent)
    menu.set_parent_size(200, 200)

    # Initially hidden
    assert not menu._is_expanded

    # Simulate hover near left edge
    menu.check_hover_zone(0, 20, parent.rect())
    assert menu._is_expanded

    # Force hide
    menu._hide_menu()
    assert not menu._is_expanded


def test_hover_menu_hides_quickly_with_configured_delay():
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.resize(200, 200)
    parent.show()

    menu = HoverDrawerMenu(parent)
    menu.set_parent_size(200, 200)
    # Use a small hide delay for the test
    menu.set_hide_delay(50)

    menu.check_hover_zone(0, 20, parent.rect())
    assert menu._is_expanded

    # Move outside hover zone to schedule hide
    menu.check_hover_zone(100, 20, parent.rect())
    # Wait longer than the configured hide delay to allow timer to fire
    QTest.qWait(80)
    assert not menu._is_expanded
