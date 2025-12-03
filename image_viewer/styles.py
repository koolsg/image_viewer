from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication, theme: str = "dark") -> None:
    """Apply a theme to the application.

    Args:
        app: QApplication instance
        theme: Theme name ("dark" or "light")
    """
    if theme == "light":
        apply_light_theme(app)
    else:
        apply_dark_theme(app)


def apply_dark_theme(app: QApplication) -> None:
    """Apply a modern dark theme to the application."""
    app.setStyle("Fusion")

    palette = QPalette()

    # Modern Dark Colors (inspired by VS Code Dark / Material)
    background = QColor(26, 26, 26)
    surface = QColor(45, 45, 45)
    primary = QColor(74, 144, 226)  # Blue accent
    text = QColor(220, 220, 220)
    disabled_text = QColor(128, 128, 128)

    palette.setColor(QPalette.Window, background)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, QColor(30, 30, 30))
    palette.setColor(QPalette.AlternateBase, surface)
    palette.setColor(QPalette.ToolTipBase, QColor(42, 42, 42))
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, surface)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Link, QColor(100, 180, 255))
    palette.setColor(QPalette.Highlight, primary)
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.Disabled, QPalette.Text, disabled_text)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_text)

    app.setPalette(palette)

    app.setStyleSheet("""
        QToolTip {
            color: #dcdcdc;
            background-color: #2a2a2a;
            border: 1px solid #454545;
            padding: 4px;
            border-radius: 4px;
        }
        QMenuBar {
            background-color: #1a1a1a;
            color: #dcdcdc;
            border-bottom: 1px solid #333333;
        }
        QMenuBar::item {
            background-color: transparent;
            padding: 6px 12px;
        }
        QMenuBar::item:selected {
            background-color: #3d3d3d;
            border-radius: 4px;
        }
        QMenu {
            background-color: #2a2a2a;
            color: #dcdcdc;
            border: 1px solid #454545;
            border-radius: 6px;
            padding: 4px;
        }
        QMenu::item {
            padding: 6px 24px;
            border-radius: 4px;
        }
        QMenu::item:selected {
            background-color: #4A90E2;
            color: #ffffff;
        }
        QScrollBar:vertical {
            border: none;
            background: #1a1a1a;
            width: 12px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #505050;
            min-height: 24px;
            border-radius: 6px;
            margin: 2px;
        }
        QScrollBar::handle:vertical:hover {
            background: #606060;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            border: none;
            background: #1a1a1a;
            height: 12px;
            margin: 0px;
        }
        QScrollBar::handle:horizontal {
            background: #505050;
            min-width: 24px;
            border-radius: 6px;
            margin: 2px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #606060;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        QLineEdit {
            background-color: #3c3c3c;
            border: 1px solid #555555;
            color: #dcdcdc;
            padding: 6px;
            border-radius: 4px;
        }
        QLineEdit:focus {
            border: 1px solid #4A90E2;
        }
        QPushButton {
            background-color: #3c3c3c;
            border: 1px solid #555555;
            color: #dcdcdc;
            padding: 6px 16px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #505050;
            border: 1px solid #666666;
        }
        QPushButton:pressed {
            background-color: #4A90E2;
            color: #ffffff;
            border: 1px solid #4A90E2;
        }
        QTreeView, QListView, QTableView {
            background-color: #1a1a1a;
            alternate-background-color: #252525;
            border: none;
            color: #dcdcdc;
        }
        QHeaderView::section {
            background-color: #2a2a2a;
            color: #b0b0b0;
            padding: 8px;
            border: none;
            border-bottom: 1px solid #333333;
        }
        QComboBox {
            background-color: #3c3c3c;
            border: 1px solid #555555;
            color: #dcdcdc;
            padding: 6px;
            border-radius: 4px;
        }
        QComboBox:hover {
            border: 1px solid #666666;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        QComboBox QAbstractItemView {
            background-color: #2a2a2a;
            border: 1px solid #454545;
            selection-background-color: #4A90E2;
            color: #dcdcdc;
        }
        /* Explorer widgets */
        #explorerThumbnailList {
            outline: 0;
            background-color: #1a1a1a;
            border: none;
            padding: 8px;
        }
        #explorerThumbnailList::item {
            border: none;
            border-radius: 8px;
            padding: 4px;
            margin: 2px;
        }
        #explorerThumbnailList::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(74, 144, 226, 60),
                stop:1 rgba(74, 144, 226, 40));
            border: 2px solid #4A90E2;
            border-radius: 8px;
        }
        #explorerThumbnailList::item:selected:active {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(74, 144, 226, 80),
                stop:1 rgba(74, 144, 226, 50));
            border: 2px solid #5BA0F2;
            border-radius: 8px;
        }
        #explorerThumbnailList::item:selected:!active {
            background: rgba(74, 144, 226, 30);
            border: 2px solid rgba(74, 144, 226, 60);
            border-radius: 8px;
        }
        #explorerThumbnailList::item:hover:!selected {
            background: rgba(255, 255, 255, 8);
            border: 1px solid rgba(255, 255, 255, 20);
            border-radius: 8px;
        }
        #explorerDetailTree {
            background-color: #1a1a1a;
            border: none;
            outline: 0;
        }
        #explorerDetailTree::item {
            padding: 6px 4px;
            border: none;
        }
        #explorerDetailTree::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(74, 144, 226, 60),
                stop:1 rgba(74, 144, 226, 40));
            color: #ffffff;
            border: none;
            outline: 0;
        }
        #explorerDetailTree::item:selected:active {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(74, 144, 226, 80),
                stop:1 rgba(74, 144, 226, 50));
            color: #ffffff;
            border: none;
            outline: 0;
        }
        #explorerDetailTree::item:hover:!selected {
            background: rgba(255, 255, 255, 8);
        }
        #explorerFolderTree {
            background-color: #1e1e1e;
            border: none;
            border-right: 1px solid #333333;
            outline: 0;
            font-size: 13px;
        }
        #explorerFolderTree::item {
            padding: 6px 4px;
            border: none;
            border-radius: 4px;
            margin: 1px 4px;
        }
        #explorerFolderTree::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(74, 144, 226, 70),
                stop:1 rgba(74, 144, 226, 50));
            color: #ffffff;
        }
        #explorerFolderTree::item:selected:active {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(74, 144, 226, 90),
                stop:1 rgba(74, 144, 226, 60));
            color: #ffffff;
        }
        #explorerFolderTree::item:hover:!selected {
            background: rgba(255, 255, 255, 8);
        }
        #explorerSplitter {
            background-color: #1a1a1a;
        }
        #explorerSplitter::handle {
            background-color: #333333;
            width: 1px;
        }
        #explorerSplitter::handle:hover {
            background-color: #4A90E2;
        }
    """)


def apply_light_theme(app: QApplication) -> None:
    """Apply a modern light theme to the application."""
    app.setStyle("Fusion")

    palette = QPalette()

    # Modern Light Colors (inspired by VS Code Light / Material)
    background = QColor(255, 255, 255)
    surface = QColor(245, 245, 245)
    primary = QColor(0, 120, 212)  # Blue accent
    text = QColor(30, 30, 30)
    disabled_text = QColor(160, 160, 160)

    palette.setColor(QPalette.Window, background)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.AlternateBase, surface)
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 225))
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, surface)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Link, QColor(0, 100, 200))
    palette.setColor(QPalette.Highlight, primary)
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.Disabled, QPalette.Text, disabled_text)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_text)

    app.setPalette(palette)

    app.setStyleSheet("""
        QToolTip {
            color: #1e1e1e;
            background-color: #ffffdd;
            border: 1px solid #cccccc;
            padding: 4px;
            border-radius: 4px;
        }
        QMenuBar {
            background-color: #f5f5f5;
            color: #1e1e1e;
            border-bottom: 1px solid #e0e0e0;
        }
        QMenuBar::item {
            background-color: transparent;
            padding: 6px 12px;
        }
        QMenuBar::item:selected {
            background-color: #e0e0e0;
            border-radius: 4px;
        }
        QMenu {
            background-color: #ffffff;
            color: #1e1e1e;
            border: 1px solid #d0d0d0;
            border-radius: 6px;
            padding: 4px;
        }
        QMenu::item {
            padding: 6px 24px;
            border-radius: 4px;
        }
        QMenu::item:selected {
            background-color: #0078D4;
            color: #ffffff;
        }
        QScrollBar:vertical {
            border: none;
            background: #f5f5f5;
            width: 12px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #c0c0c0;
            min-height: 24px;
            border-radius: 6px;
            margin: 2px;
        }
        QScrollBar::handle:vertical:hover {
            background: #a0a0a0;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            border: none;
            background: #f5f5f5;
            height: 12px;
            margin: 0px;
        }
        QScrollBar::handle:horizontal {
            background: #c0c0c0;
            min-width: 24px;
            border-radius: 6px;
            margin: 2px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #a0a0a0;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        QLineEdit {
            background-color: #ffffff;
            border: 1px solid #d0d0d0;
            color: #1e1e1e;
            padding: 6px;
            border-radius: 4px;
        }
        QLineEdit:focus {
            border: 1px solid #0078D4;
        }
        QPushButton {
            background-color: #f5f5f5;
            border: 1px solid #d0d0d0;
            color: #1e1e1e;
            padding: 6px 16px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #e8e8e8;
            border: 1px solid #b0b0b0;
        }
        QPushButton:pressed {
            background-color: #0078D4;
            color: #ffffff;
            border: 1px solid #0078D4;
        }
        QTreeView, QListView, QTableView {
            background-color: #ffffff;
            alternate-background-color: #f9f9f9;
            border: none;
            color: #1e1e1e;
        }
        QHeaderView::section {
            background-color: #f5f5f5;
            color: #606060;
            padding: 8px;
            border: none;
            border-bottom: 1px solid #e0e0e0;
        }
        QComboBox {
            background-color: #ffffff;
            border: 1px solid #d0d0d0;
            color: #1e1e1e;
            padding: 6px;
            border-radius: 4px;
        }
        QComboBox:hover {
            border: 1px solid #b0b0b0;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        QComboBox QAbstractItemView {
            background-color: #ffffff;
            border: 1px solid #d0d0d0;
            selection-background-color: #0078D4;
            color: #1e1e1e;
        }
        /* Explorer widgets */
        #explorerThumbnailList {
            outline: 0;
            background-color: #ffffff;
            border: none;
            padding: 8px;
        }
        #explorerThumbnailList::item {
            border: none;
            border-radius: 8px;
            padding: 4px;
            margin: 2px;
        }
        #explorerThumbnailList::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(0, 120, 212, 40),
                stop:1 rgba(0, 120, 212, 30));
            border: 2px solid #0078D4;
            border-radius: 8px;
        }
        #explorerThumbnailList::item:selected:active {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(0, 120, 212, 60),
                stop:1 rgba(0, 120, 212, 40));
            border: 2px solid #0078D4;
            border-radius: 8px;
        }
        #explorerThumbnailList::item:selected:!active {
            background: rgba(0, 120, 212, 20);
            border: 2px solid rgba(0, 120, 212, 50);
            border-radius: 8px;
        }
        #explorerThumbnailList::item:hover:!selected {
            background: rgba(0, 0, 0, 5);
            border: 1px solid rgba(0, 0, 0, 15);
            border-radius: 8px;
        }
        #explorerDetailTree {
            background-color: #ffffff;
            border: none;
            outline: 0;
        }
        #explorerDetailTree::item {
            padding: 6px 4px;
            border: none;
        }
        #explorerDetailTree::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(0, 120, 212, 40),
                stop:1 rgba(0, 120, 212, 30));
            color: #1e1e1e;
            border: none;
            outline: 0;
        }
        #explorerDetailTree::item:selected:active {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(0, 120, 212, 60),
                stop:1 rgba(0, 120, 212, 40));
            color: #1e1e1e;
            border: none;
            outline: 0;
        }
        #explorerDetailTree::item:hover:!selected {
            background: rgba(0, 0, 0, 5);
        }
        #explorerFolderTree {
            background-color: #f5f5f5;
            border: none;
            border-right: 1px solid #e0e0e0;
            outline: 0;
            font-size: 13px;
        }
        #explorerFolderTree::item {
            padding: 6px 4px;
            border: none;
            border-radius: 4px;
            margin: 1px 4px;
        }
        #explorerFolderTree::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(0, 120, 212, 50),
                stop:1 rgba(0, 120, 212, 35));
            color: #1e1e1e;
        }
        #explorerFolderTree::item:selected:active {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(0, 120, 212, 70),
                stop:1 rgba(0, 120, 212, 50));
            color: #1e1e1e;
        }
        #explorerFolderTree::item:hover:!selected {
            background: rgba(0, 0, 0, 5);
        }
        #explorerSplitter {
            background-color: #ffffff;
        }
        #explorerSplitter::handle {
            background-color: #e0e0e0;
            width: 1px;
        }
        #explorerSplitter::handle:hover {
            background-color: #0078D4;
        }
    """)
