import pytest

pytest.skip(
    "Legacy QQuickWidget keybinding tests. The app is now QML-first; keybindings live in QML and call Main(QObject).",
    allow_module_level=True,
)
