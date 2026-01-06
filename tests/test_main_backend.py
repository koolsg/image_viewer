from __future__ import annotations

from pathlib import Path

import pytest

from image_viewer.main import Main
from image_viewer.settings_manager import SettingsManager


class FakeEngine:
    def __init__(self) -> None:
        self.opened: list[str] = []
        self.decoded: list[tuple[str, tuple[int, int]]] = []

    def open_folder(self, path: str) -> None:
        self.opened.append(str(path))

    def request_decode(self, path: str, target_size: tuple[int, int]) -> None:
        self.decoded.append((str(path), target_size))

    def get_cached_pixmap(self, path: str):
        return None


def test_main_open_folder_persists_settings(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    sm = SettingsManager(str(settings_file))
    engine = FakeEngine()

    main = Main(engine=engine, settings=sm)

    folder = tmp_path / "images"
    folder.mkdir()

    main.openFolder(str(folder))

    assert sm.last_parent_dir == str(folder)
    assert engine.opened == [str(folder)]


def test_main_navigation_updates_current_path(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    sm = SettingsManager(str(settings_file))
    engine = FakeEngine()

    main = Main(engine=engine, settings=sm)

    files = [str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg"), str(tmp_path / "c.jpg")]
    main._on_engine_file_list_updated(files)

    assert main.currentIndex == 0
    assert main.currentPath == files[0]

    main.nextImage()
    assert main.currentIndex == 1
    assert main.currentPath == files[1]

    main.lastImage()
    assert main.currentIndex == 2
    assert main.currentPath == files[2]

    main.firstImage()
    assert main.currentIndex == 0
    assert main.currentPath == files[0]
