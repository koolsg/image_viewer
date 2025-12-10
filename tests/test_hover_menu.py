from pathlib import Path
import sys
from PySide6.QtWidgets import QApplication, QWidget

# Ensure repository root is on path (pytest might not add package layout)
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from image_viewer.ui_hover_menu import HoverDrawerMenu


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
