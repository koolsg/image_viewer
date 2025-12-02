from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

def apply_dark_theme(app: QApplication):
    """Apply a modern dark theme to the application using Fusion style and QPalette."""
    app.setStyle("Fusion")

    dark_palette = QPalette()

    # Base colors
    white = QColor(255, 255, 255)
    black = QColor(0, 0, 0)
    red = QColor(255, 0, 0)
    
    # Modern Dark Colors (inspired by VS Code Dark / Material)
    background = QColor(30, 30, 30)
    surface = QColor(45, 45, 45)
    primary = QColor(0, 122, 204)  # A nice blue
    text = QColor(220, 220, 220)
    disabled_text = QColor(128, 128, 128)
    
    dark_palette.setColor(QPalette.Window, background)
    dark_palette.setColor(QPalette.WindowText, text)
    dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.AlternateBase, surface)
    dark_palette.setColor(QPalette.ToolTipBase, white)
    dark_palette.setColor(QPalette.ToolTipText, white)
    dark_palette.setColor(QPalette.Text, text)
    dark_palette.setColor(QPalette.Button, surface)
    dark_palette.setColor(QPalette.ButtonText, text)
    dark_palette.setColor(QPalette.BrightText, red)
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, primary)
    dark_palette.setColor(QPalette.HighlightedText, white)
    dark_palette.setColor(QPalette.Disabled, QPalette.Text, disabled_text)
    dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_text)

    app.setPalette(dark_palette)

    # Additional Stylesheet for finer control
    app.setStyleSheet("""
        QToolTip { 
            color: #ffffff; 
            background-color: #2a2a2a; 
            border: 1px solid #454545; 
        }
        QMenuBar {
            background-color: #1e1e1e;
            color: #dcdcdc;
        }
        QMenuBar::item {
            background-color: transparent;
        }
        QMenuBar::item:selected {
            background-color: #3d3d3d;
        }
        QMenu {
            background-color: #252525;
            color: #dcdcdc;
            border: 1px solid #454545;
        }
        QMenu::item {
            padding: 5px 20px;
        }
        QMenu::item:selected {
            background-color: #007acc;
            color: #ffffff;
        }
        QScrollBar:vertical {
            border: none;
            background: #1e1e1e;
            width: 10px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #424242;
            min-height: 20px;
            border-radius: 5px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            border: none;
            background: #1e1e1e;
            height: 10px;
            margin: 0px;
        }
        QScrollBar::handle:horizontal {
            background: #424242;
            min-width: 20px;
            border-radius: 5px;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        QLineEdit {
            background-color: #3c3c3c;
            border: 1px solid #3c3c3c;
            color: #dcdcdc;
            padding: 2px;
            border-radius: 2px;
        }
        QPushButton {
            background-color: #3c3c3c;
            border: 1px solid #555555;
            color: #dcdcdc;
            padding: 5px;
            border-radius: 2px;
        }
        QPushButton:hover {
            background-color: #505050;
        }
        QPushButton:pressed {
            background-color: #007acc;
            color: #ffffff;
        }
        QTreeView, QListView, QTableView {
            background-color: #252525;
            alternate-background-color: #2d2d2d;
            border: none;
            color: #dcdcdc;
        }
        QHeaderView::section {
            background-color: #333333;
            color: #dcdcdc;
            padding: 4px;
            border: none;
        }
    """)
