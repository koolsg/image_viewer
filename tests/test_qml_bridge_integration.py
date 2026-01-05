from image_viewer.qml_bridge import AppController
from PySide6.QtGui import QPixmap


class MockEngine:
    def __init__(self):
        self.request_decode_called = []

    def request_decode(self, path, target):
        self.request_decode_called.append((path, target))


def test_app_controller_emits_image_url():
    engine = MockEngine()
    ctrl = AppController(engine)

    # Track signals
    emitted = []
    ctrl.imageReady.connect(lambda p, url, g: emitted.append((p, url, g)))

    ctrl.setCurrentPathSlot("C:/test.jpg")
    assert ctrl._generation == 1

    pixmap = QPixmap(10, 10)
    ctrl.on_engine_image_ready("C:/test.jpg", pixmap, None)

    assert len(emitted) == 1
    path, url, gen = emitted[0]
    assert path == "C:/test.jpg"
    assert url == "image://engine/1/C:/test.jpg"
    assert gen == 1


def test_app_controller_discards_stale_path():
    engine = MockEngine()
    ctrl = AppController(engine)

    emitted = []
    ctrl.imageReady.connect(lambda p, url, g: emitted.append((p, url, g)))

    ctrl.setCurrentPathSlot("C:/new.jpg")  # gen 1

    pixmap = QPixmap(10, 10)
    # Late result from previous path
    ctrl.on_engine_image_ready("C:/old.jpg", pixmap, None)

    assert len(emitted) == 0
