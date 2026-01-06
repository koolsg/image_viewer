import pytest

pytest.skip(
    "Legacy ImageViewer/AppController(QWidget) test. The app is now QML-first with a Main(QObject) backend.",
    allow_module_level=True,
)
