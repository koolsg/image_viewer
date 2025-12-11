from pathlib import Path
import sys
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication

# Ensure repo root
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from image_viewer.ui_settings import SettingsDialog
from image_viewer.settings_manager import SettingsManager


class FakeHover:
    def __init__(self):
        self._hide_delay = None

    def set_hide_delay(self, ms: int):
        self._hide_delay = int(ms)


class FakeViewer:
    def __init__(self, settings_path: str):
        self._settings_manager = SettingsManager(settings_path)
        self.explorer_state = SimpleNamespace(_explorer_grid=None)
        self._hover_menu = FakeHover()

    def _save_settings_key(self, key: str, value):
        self._settings_manager.set(key, value)

    def set_press_zoom_multiplier(self, v):
        pass


def test_settings_applies_hover_delay(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings_file = str(tmp_path / "settings.json")
    viewer = FakeViewer(settings_file)

    from PySide6.QtWidgets import QWidget
    parent = QWidget()
    dlg = SettingsDialog(viewer, parent=parent)

    # set a small hide delay and apply
    dlg._spin_hover_hide_delay.setValue(50)
    dlg._on_apply_clicked()

    assert viewer._hover_menu._hide_delay == 50
    assert int(viewer._settings_manager.get("hover_hide_delay")) == 50
