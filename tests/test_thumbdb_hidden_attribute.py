from types import SimpleNamespace
from pathlib import Path
import sys
import os

# Ensure project package is importable when running tests individually
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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


def _make_db_path(tmp_path: Path) -> Path:
    p = tmp_path / "SwiftView_thumbs.db"
    return p


def test_thumbdb_sets_hidden_on_success(monkeypatch, tmp_path: Path):
    # Replace module logger with a fake one to capture messages
    class _FakeLogger:
        def __init__(self):
            self.messages = []

        def debug(self, msg, *args, **kwargs):
            try:
                self.messages.append(msg % args if args else msg)
            except Exception:
                self.messages.append(msg)

        def error(self, msg, *args, **kwargs):
            try:
                self.messages.append(msg % args if args else msg)
            except Exception:
                self.messages.append(msg)

    fake_logger = _FakeLogger()
    monkeypatch.setattr(tba, "_logger", fake_logger)
    monkeypatch.setattr(tba, "platform", SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(tba, "ctypes", _FakeCtypes(1))

    db_path = _make_db_path(tmp_path)
    # Ensure file exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"x")

    tba._set_hidden_attribute_on_path(db_path)

    assert any(f"set hidden attribute on {db_path}" in m for m in fake_logger.messages)


def test_thumbdb_logs_failure(monkeypatch, tmp_path: Path):
    class _FakeLogger:
        def __init__(self):
            self.messages = []

        def debug(self, msg, *args, **kwargs):
            try:
                self.messages.append(msg % args if args else msg)
            except Exception:
                self.messages.append(msg)

        def error(self, msg, *args, **kwargs):
            try:
                self.messages.append(msg % args if args else msg)
            except Exception:
                self.messages.append(msg)

    fake_logger = _FakeLogger()
    monkeypatch.setattr(tba, "_logger", fake_logger)
    monkeypatch.setattr(tba, "platform", SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(tba, "ctypes", _FakeCtypes(0))

    db_path = _make_db_path(tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"x")

    tba._set_hidden_attribute_on_path(db_path)

    assert any("SetFileAttributesW failed for" in m for m in fake_logger.messages)


def test_thumbdb_skips_on_non_windows(monkeypatch, tmp_path: Path):
    class _FakeLogger:
        def __init__(self):
            self.messages = []

        def debug(self, msg, *args, **kwargs):
            try:
                self.messages.append(msg % args if args else msg)
            except Exception:
                self.messages.append(msg)

        def error(self, msg, *args, **kwargs):
            try:
                self.messages.append(msg % args if args else msg)
            except Exception:
                self.messages.append(msg)

    fake_logger = _FakeLogger()
    monkeypatch.setattr(tba, "_logger", fake_logger)
    monkeypatch.setattr(tba, "platform", SimpleNamespace(system=lambda: "Linux"))
    monkeypatch.setattr(tba, "ctypes", _FakeCtypes(1))

    db_path = _make_db_path(tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"x")

    tba._set_hidden_attribute_on_path(db_path)

    assert all("set hidden attribute" not in m for m in fake_logger.messages)
