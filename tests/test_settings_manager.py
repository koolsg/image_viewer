from __future__ import annotations

from pathlib import Path

from image_viewer.settings_manager import SettingsManager


def test_last_open_dir_is_normalized_and_directory(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    sm = SettingsManager(str(settings_path))

    folder = tmp_path / "some_folder"
    folder.mkdir()

    sm.set("last_open_dir", str(folder))

    # Stored values are normalized to absolute, OS-native directory paths.
    assert sm.last_open_dir is not None
    assert Path(sm.last_open_dir).is_dir()
    assert Path(sm.last_open_dir) == folder.resolve()


def test_setting_last_open_dir_to_file_coerces_to_parent_dir(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    sm = SettingsManager(str(settings_path))

    folder = tmp_path / "some_folder"
    folder.mkdir()

    file_path = folder / "x.txt"
    file_path.write_text("x", encoding="utf-8")

    sm.set("last_open_dir", str(file_path))

    assert sm.last_open_dir == str(folder.resolve())
