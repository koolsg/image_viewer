import logging
from types import SimpleNamespace
from pathlib import Path
import sys
import os

# Ensure project package is importable when running tests individually
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

# Create lightweight fakes for PySide6 imports used by the module so tests
# can run in environments without Qt installed.
class _FakeQBuffer:
    def __init__(self):
        pass

class _FakeQIODevice:
    OpenModeFlag = SimpleNamespace(WriteOnly=1)

class _FakeQPixmap:
    def __init__(self):
        pass

import types
sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
sys.modules.setdefault("PySide6.QtCore", types.SimpleNamespace(QBuffer=_FakeQBuffer, QIODevice=_FakeQIODevice))
sys.modules.setdefault("PySide6.QtGui", types.SimpleNamespace(QPixmap=_FakeQPixmap))

from image_viewer.image_engine import thumbnail_cache as tc
from image_viewer.image_engine.thumbnail_cache import ThumbnailCache


class _FakeKernel32:
    def __init__(self, rv: int):
        self._rv = rv

    def SetFileAttributesW(self, path, flags):
        return self._rv


class _FakeCtypes:
    def __init__(self, rv: int):
        self.windll = SimpleNamespace(kernel32=_FakeKernel32(rv))


def _make_uninitialized_cache(tmp_path: Path) -> ThumbnailCache:
    # Create an object without running __init__ and set minimal attributes
    inst = ThumbnailCache.__new__(ThumbnailCache)
    inst.cache_dir = tmp_path
    inst.db_path = tmp_path / "test.db"
    # ensure file exists
    inst.db_path.write_bytes(b"x")
    inst._thumb_db = None
    inst._db_operator = None
    return inst


def test_set_hidden_attribute_success(monkeypatch, tmp_path: Path):
    # Replace module logger to capture messages deterministically
    class _FakeLogger:
        def __init__(self):
            self.messages = []

        def debug(self, msg, *args, **kwargs):
            self.messages.append(msg % args if args else msg)

        def error(self, msg, *args, **kwargs):
            self.messages.append(msg % args if args else msg)

    fake_logger = _FakeLogger()
    monkeypatch.setattr(tc, "_logger", fake_logger)

    monkeypatch.setattr(tc, "platform", SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(tc, "ctypes", _FakeCtypes(1))

    inst = _make_uninitialized_cache(tmp_path)
    inst._set_hidden_attribute()

    assert any(f"set hidden attribute on {inst.db_path}" in m for m in fake_logger.messages)


def test_set_hidden_attribute_failure(monkeypatch, tmp_path: Path):
    class _FakeLogger:
        def __init__(self):
            self.messages = []

        def debug(self, msg, *args, **kwargs):
            self.messages.append(msg % args if args else msg)

        def error(self, msg, *args, **kwargs):
            self.messages.append(msg % args if args else msg)

    fake_logger = _FakeLogger()
    monkeypatch.setattr(tc, "_logger", fake_logger)

    monkeypatch.setattr(tc, "platform", SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(tc, "ctypes", _FakeCtypes(0))

    inst = _make_uninitialized_cache(tmp_path)
    inst._set_hidden_attribute()

    assert any(f"SetFileAttributesW failed for {inst.db_path}" in m for m in fake_logger.messages)


def test_set_hidden_attribute_non_windows(monkeypatch, caplog, tmp_path: Path):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(tc, "platform", SimpleNamespace(system=lambda: "Linux"))
    # Ensure ctypes would be present but not used
    monkeypatch.setattr(tc, "ctypes", _FakeCtypes(1))

    inst = _make_uninitialized_cache(tmp_path)
    inst._set_hidden_attribute()

    assert "set hidden attribute" not in caplog.text
