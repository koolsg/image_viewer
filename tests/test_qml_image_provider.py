import pytest
from image_viewer.qml_bridge import EngineImageProvider
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class MockEngine:
    def __init__(self):
        self.cache = {}

    def get_cached_pixmap(self, path):
        return self.cache.get(path)


def test_engine_image_provider_cache_hit():
    engine = MockEngine()
    path = "C:/test.jpg"
    pixmap = QPixmap(10, 10)
    pixmap.fill("red")
    engine.cache[path] = pixmap

    provider = EngineImageProvider(engine)
    # The ID passed to requestPixmap will be the path
    result = provider.requestPixmap(path, None, (0, 0))

    assert not result.isNull()
    assert result.width() == pixmap.width()


def test_engine_image_provider_cache_miss():
    engine = MockEngine()
    _provider = EngineImageProvider(engine)

    result = _provider.requestPixmap("C:/missing.jpg", None, (0, 0))
    assert result.isNull()


def test_engine_image_provider_with_generation():
    engine = MockEngine()
    path = "C:/test.jpg"
    pixmap = QPixmap(10, 10)
    pixmap.fill("blue")
    engine.cache[path] = pixmap

    _provider = EngineImageProvider(engine)


def test_engine_image_provider_percent_encoded_path():
    engine = MockEngine()
    path = "C:/test with spaces.jpg"
    pixmap = QPixmap(10, 10)
    pixmap.fill("green")
    engine.cache[path] = pixmap

    provider = EngineImageProvider(engine)
    # Simulate percent-encoded path passed by QML
    encoded_id = "1/C:/test%20with%20spaces.jpg"
    result = provider.requestPixmap(encoded_id, None, (0, 0))

    assert not result.isNull()
    assert result.width() == pixmap.width()
