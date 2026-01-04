from types import SimpleNamespace
from pathlib import Path

import pytest

from image_viewer.image_engine.db import thumbdb_bytes_adapter as tba


class _FakeKernel32:
    def __init__(self, rv: int):
        self._rv = rv

    def SetFileAttributesW(self, path, flags):
        return self._rv


class _FakeCtypes:
    def __init__(self, rv: int):
        self.windll = SimpleNamespace(kernel32=_FakeKernel32(rv))


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
    monkeypatch.setattr(tba, "_logger", fake_logger)

    monkeypatch.setattr(tba, "platform", SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(tba, "ctypes", _FakeCtypes(1))

    db_path = tmp_path / "test.db"
    db_path.write_bytes(b"x")

    tba._set_hidden_attribute_on_path(db_path)

    assert any(f"set hidden attribute on {db_path}" in m for m in fake_logger.messages)


def test_set_hidden_attribute_failure(monkeypatch, tmp_path: Path):
    class _FakeLogger:
        def __init__(self):
            self.messages = []

        def debug(self, msg, *args, **kwargs):
            self.messages.append(msg % args if args else msg)

        def error(self, msg, *args, **kwargs):
            self.messages.append(msg % args if args else msg)

    fake_logger = _FakeLogger()
    monkeypatch.setattr(tba, "_logger", fake_logger)

    monkeypatch.setattr(tba, "platform", SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(tba, "ctypes", _FakeCtypes(0))

    db_path = tmp_path / "test.db"
    db_path.write_bytes(b"x")

    tba._set_hidden_attribute_on_path(db_path)

    assert any(f"SetFileAttributesW failed for {db_path}" in m for m in fake_logger.messages)


def test_set_hidden_attribute_non_windows(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(tba, "platform", SimpleNamespace(system=lambda: "Linux"))
    # Ensure ctypes would be present but not used
    monkeypatch.setattr(tba, "ctypes", _FakeCtypes(1))

    db_path = tmp_path / "test.db"
    db_path.write_bytes(b"x")

    # Should be a no-op (and must not crash).
    tba._set_hidden_attribute_on_path(db_path)
