import pytest

pytest.skip(
    "Legacy AppController/ImageViewer(QWidget) pass-through tests. QML now calls Main(QObject) directly.",
    allow_module_level=True,
)
