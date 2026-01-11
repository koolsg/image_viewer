from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication


def main() -> int:
    # Use a non-native style so Controls behave consistently.
    QQuickStyle.setStyle("Fusion")

    app = QApplication(sys.argv)

    qml_engine = QQmlApplicationEngine()

    qml_file = Path(__file__).resolve().parents[1] / "image_viewer" / "ui" / "qml" / "MenuTest.qml"
    qml_engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not qml_engine.rootObjects():
        print(f"Failed to load QML: {qml_file}", file=sys.stderr)
        return 1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
