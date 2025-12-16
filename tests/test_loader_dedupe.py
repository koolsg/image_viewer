import pytest


PySide6 = pytest.importorskip("PySide6")  # noqa: F401

from image_viewer.image_engine.loader import Loader


class _FakePool:
    def __init__(self) -> None:
        self.submits: list[tuple[object, tuple, dict]] = []

    def submit(self, fn, /, *args, **kwargs):  # noqa: ANN001
        self.submits.append((fn, args, kwargs))
        return None


def _noop_decode(path: str, target_width, target_height, size: str):  # noqa: ANN001
    return path, None, None


def test_request_load_dedupes_identical_pending_request() -> None:
    loader = Loader(_noop_decode)
    try:
        fake_pool = _FakePool()
        loader.io_pool = fake_pool  # type: ignore[assignment]

        path = "C:/tmp/example.jpg"

        loader.request_load(path, None, None, "both")
        assert len(fake_pool.submits) == 1

        # Identical pending request should be dropped.
        loader.request_load(path, None, None, "both")
        assert len(fake_pool.submits) == 1

        # Different params should be allowed (and will make earlier result stale).
        loader.request_load(path, 123, None, "both")
        assert len(fake_pool.submits) == 2
    finally:
        loader.shutdown()
