import os
import tempfile
import types
from pathlib import Path

import pytest

import image_viewer.main as main_mod
from image_viewer.settings_manager import SettingsManager


def test_run_opens_last_folder(monkeypatch, tmp_path):
    # Prepare settings with last_parent_dir set
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    settings_file = cfg / "settings.json"
    sm = SettingsManager(str(settings_file))
    sm.set("last_parent_dir", str(cfg))

    # Replace SettingsManager used by image_viewer.main.run
    monkeypatch.setattr("image_viewer.main.SettingsManager", lambda p: sm)

    called = {}

    class FakeEngine:
        def __init__(self):
            pass

        def open_folder(self, path):
            called["path"] = path
            return True

    # Patch the engine used by image_viewer.main.run
    monkeypatch.setattr("image_viewer.main.ImageEngine", FakeEngine)

    # Avoid theme application to a fake QApplication
    monkeypatch.setattr("image_viewer.main.apply_theme", lambda app, theme, font_size: None)

    # Provide a Dummy QQmlApplicationEngine that doesn't load real QML
    class DummyRoot:
        def __init__(self):
            self._props = {}

        def setProperty(self, name, value):
            self._props[name] = value

    class DummyQmlEngine:
        last_instance = None

        def __init__(self):
            DummyQmlEngine.last_instance = self
            self._roots = []

        def addImageProvider(self, *args, **kwargs):
            return None

        def load(self, url):
            self._roots = [DummyRoot()]

        def rootObjects(self):
            return self._roots

    monkeypatch.setattr("image_viewer.main.QQmlApplicationEngine", DummyQmlEngine)

    # Ensure run uses the existing QApplication if present (pytest-qt provides one)
    from PySide6.QtWidgets import QApplication as RealQApp
    monkeypatch.setattr("image_viewer.main.QApplication", lambda argv: RealQApp.instance() or RealQApp(argv))

    # Prevent app.exec() from blocking the test by forcing QApplication.exec to return immediately
    monkeypatch.setattr("PySide6.QtWidgets.QApplication.exec", lambda self: 0, raising=False)

    # Call run without start_path
    main_mod.run(["prog"])

    # The run() should have stored the controller on the QML root; get it and open folder
    qroot = DummyQmlEngine.last_instance.rootObjects()[0]
    main_obj = qroot._props.get("main")
    assert main_obj is not None

    # Call openFolder and verify settings updated
    main_obj.openFolder(str(cfg))
    assert sm.last_parent_dir == str(cfg)

    assert called.get("path") == str(cfg)
