from pathlib import Path
import sys
import os
import json
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication

# Ensure repo root
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from image_viewer.main import ImageViewer, _BASE_DIR
from image_viewer.settings_manager import SettingsManager


def test_imageviewer_default_settings_path(tmp_path):
    app = QApplication.instance() or QApplication([])
    viewer = ImageViewer()

    from PySide6.QtCore import QStandardPaths

    app_cfg = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
    if app_cfg:
        expected = (Path(app_cfg) / "image_viewer" / "settings.json").as_posix()
    else:
        expected = (Path(_BASE_DIR) / "settings.json").as_posix()
    assert viewer._settings_path == expected

    # Replace settings manager to avoid writing to repo path
    settings_file = str(tmp_path / "settings.json")
    viewer._settings_manager = SettingsManager(settings_file)
    viewer._settings_path = settings_file

    # Save a last_parent_dir key and confirm file contains it
    test_dir = str(tmp_path / "some_folder")
    viewer._save_last_parent_dir(test_dir)

    with open(settings_file, encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("last_parent_dir") == test_dir
