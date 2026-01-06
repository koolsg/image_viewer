import pytest

pytest.skip(
    "Legacy QWidget Explorer/View mode test. The app is now QML-first and uses Main(QObject) viewMode.",
    allow_module_level=True,
)
