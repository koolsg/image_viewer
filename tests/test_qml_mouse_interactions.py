import pytest

pytest.skip(
    "Legacy QQuickWidget mouse interaction tests. The app is now QML-first; input handling is tested at the QML layer.",
    allow_module_level=True,
)
