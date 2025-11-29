import sys
import ctypes
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Fullscreen Toggle Example')
        self.was_maximized = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        super().keyPressEvent(event)

    def toggle_fullscreen(self):
        hwnd = int(self.winId())
        ctypes.windll.user32.SendMessageW(hwnd, 0x000B, 0, 0)
        try:
            if self.isFullScreen():
                if self.was_maximized:
                    self.showMaximized()
                else:
                    self.showNormal()
            else:
                self.was_maximized = self.isMaximized()
                self.showFullScreen()
            QApplication.processEvents()
        finally:
            ctypes.windll.user32.SendMessageW(hwnd, 0x000B, 1, 0)
            self.repaint()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
