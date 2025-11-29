import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QTextEdit
from PySide6.QtCore import Qt, QDataStream, QIODevice

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Check Saved Geometry State")
        self.resize(800, 600)

        # Central widget
        central = QWidget()
        layout = QVBoxLayout(central)

        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        layout.addWidget(self.text_output)

        btn1 = QPushButton("Save Current Geometry", self)
        btn1.clicked.connect(self.save_and_analyze)
        layout.addWidget(btn1)

        btn2 = QPushButton("Maximize Window", self)
        btn2.clicked.connect(self.showMaximized)
        layout.addWidget(btn2)

        btn3 = QPushButton("Normal Window", self)
        btn3.clicked.connect(self.showNormal)
        layout.addWidget(btn3)

        self.setCentralWidget(central)
        self.saved_geometry = None

    def save_and_analyze(self):
        """현재 geometry를 저장하고 분석"""
        self.saved_geometry = self.saveGeometry()

        output = []
        output.append("=" * 60)
        output.append("Current Window State:")
        output.append(f"  isMaximized: {self.isMaximized()}")
        output.append(f"  isFullScreen: {self.isFullScreen()}")
        output.append(f"  isMinimized: {self.isMinimized()}")
        output.append(f"  windowState: {self.windowState()}")
        output.append("")

        output.append("Saved Geometry Info:")
        output.append(f"  Size: {len(self.saved_geometry)} bytes")
        output.append(f"  Hex (first 50 bytes): {self.saved_geometry[:50].toHex().data().decode()}")
        output.append("")

        # Method 1: windowState()를 별도로 저장
        output.append("Method 1: Save windowState separately")
        window_state = self.windowState()
        is_maximized = bool(window_state & Qt.WindowState.WindowMaximized)
        output.append(f"  WindowState value: {window_state}")
        output.append(f"  Is Maximized: {is_maximized}")
        output.append("")

        # Method 2: restoreGeometry 후 상태 확인
        output.append("Method 2: Test restore and check state")
        output.append("  (This would require actually restoring)")
        output.append("")

        # Method 3: QDataStream으로 파싱 (복잡하지만 가능)
        output.append("Method 3: Parse QByteArray with QDataStream")
        try:
            stream = QDataStream(self.saved_geometry, QIODevice.ReadOnly)
            magic = stream.readUInt32()
            version = stream.readUInt16()
            output.append(f"  Magic number: 0x{magic:08X}")
            output.append(f"  Version: {version}")

            # Qt의 saveGeometry 포맷:
            # - frameGeometry (QRect)
            # - normalGeometry (QRect)
            # - screen number
            # - maximized flag
            # - fullscreen flag

            # frameGeometry 읽기
            frame_x = stream.readInt32()
            frame_y = stream.readInt32()
            frame_w = stream.readInt32()
            frame_h = stream.readInt32()
            output.append(f"  Frame geometry: ({frame_x}, {frame_y}, {frame_w}, {frame_h})")

            # normalGeometry 읽기
            normal_x = stream.readInt32()
            normal_y = stream.readInt32()
            normal_w = stream.readInt32()
            normal_h = stream.readInt32()
            output.append(f"  Normal geometry: ({normal_x}, {normal_y}, {normal_w}, {normal_h})")

            # screen number
            screen_num = stream.readInt32()
            output.append(f"  Screen number: {screen_num}")

            # maximized flag
            maximized_flag = stream.readUInt8()
            output.append(f"  Maximized flag: {maximized_flag}")

            # fullscreen flag
            fullscreen_flag = stream.readUInt8()
            output.append(f"  Fullscreen flag: {fullscreen_flag}")

        except Exception as e:
            output.append(f"  Error parsing: {e}")

        output.append("=" * 60)

        self.text_output.append("\n".join(output))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_S:
            self.save_and_analyze()
        super().keyPressEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
