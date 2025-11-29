import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Resize to Maximize Example")
        self.resize(800, 600)

        # Central widget with buttons
        central = QWidget()
        layout = QVBoxLayout(central)

        btn1 = QPushButton("Maximize using showMaximized()", self)
        btn1.clicked.connect(self.maximize_normal)
        layout.addWidget(btn1)

        btn2 = QPushButton("Maximize using resize() - Method 1", self)
        btn2.clicked.connect(self.maximize_with_resize_method1)
        layout.addWidget(btn2)

        btn3 = QPushButton("Maximize using resize() - Method 2", self)
        btn3.clicked.connect(self.maximize_with_resize_method2)
        layout.addWidget(btn3)

        btn4 = QPushButton("Restore to 800x600", self)
        btn4.clicked.connect(self.restore_size)
        layout.addWidget(btn4)

        self.setCentralWidget(central)

    def maximize_normal(self):
        """일반적인 maximize 방법"""
        print("Using showMaximized()")
        self.showMaximized()

    def maximize_with_resize_method1(self):
        """resize()를 이용한 maximize - availableGeometry 사용"""
        print("Using resize() with availableGeometry")
        # 현재 화면의 available geometry 가져오기 (작업 표시줄 제외)
        screen = QApplication.primaryScreen()
        available_geometry = screen.availableGeometry()

        print(f"Available geometry: {available_geometry}")

        # 창을 해당 위치와 크기로 설정
        self.setGeometry(available_geometry)
        # 또는
        # self.move(available_geometry.topLeft())
        # self.resize(available_geometry.size())

    def maximize_with_resize_method2(self):
        """resize()를 이용한 maximize - geometry 사용 (작업 표시줄 포함)"""
        print("Using resize() with full screen geometry")
        # 현재 화면의 전체 geometry 가져오기 (작업 표시줄 포함)
        screen = QApplication.primaryScreen()
        full_geometry = screen.geometry()

        print(f"Full geometry: {full_geometry}")

        # 창을 해당 위치와 크기로 설정
        self.setGeometry(full_geometry)

    def restore_size(self):
        """원래 크기로 복원"""
        print("Restoring to 800x600")
        self.showNormal()
        self.resize(800, 600)
        # 화면 중앙으로 이동
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - 800) // 2
        y = (screen_geometry.height() - 600) // 2
        self.move(x, y)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
