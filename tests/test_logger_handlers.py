import logging
import sys

import pytest

from image_viewer import logger as iv_logger


def _unwrap(s):
    return getattr(s, "_orig", s)


def test_setup_logger_idempotent_handlers(tmp_path, monkeypatch):
    """Calling setup_logger() repeatedly should leave exactly one stderr StreamHandler."""
    monkeypatch.chdir(tmp_path)
    base = iv_logger.setup_logger(level=logging.DEBUG)
    _ = iv_logger.setup_logger(level=logging.DEBUG)

    handlers = [
        h
        for h in base.handlers
        if isinstance(h, logging.StreamHandler)
        and _unwrap(getattr(h, "stream", None)) is _unwrap(sys.stderr)
    ]

    assert len(handlers) == 1


def test_setup_logger_with_external_wrapper(tmp_path, monkeypatch):
    """If stderr is wrapped externally between calls, setup_logger still won't add a second handler."""
    monkeypatch.chdir(tmp_path)

    base = iv_logger.setup_logger(level=logging.DEBUG)

    # Simulate an external wrapper that wraps the current stderr
    class DummyWrapper:
        def __init__(self, orig):
            self._orig = orig
            self._filtered_by_image_viewer = True

        def write(self, s):
            return self._orig.write(s)

        def flush(self):
            return getattr(self._orig, "flush", lambda: None)()

    monkeypatch.setattr(sys, "stderr", DummyWrapper(sys.stderr))

    _ = iv_logger.setup_logger(level=logging.DEBUG)

    handlers = [
        h
        for h in base.handlers
        if isinstance(h, logging.StreamHandler)
        and _unwrap(getattr(h, "stream", None)) is _unwrap(sys.stderr)
    ]

    assert len(handlers) == 1
