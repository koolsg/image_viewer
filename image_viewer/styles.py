from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# -----------------------------------------------------------------------------
# Fluent Design Color Palette (WinUI 3 Inspired)
# -----------------------------------------------------------------------------


class FluentColors:
    # Dark Theme
    DARK_WINDOW = "#202020"  # Neutral background
    DARK_SURFACE = "#2D2D2D"  # Card/Layer background
    DARK_SURFACE_ALT = "#323232"  # Alternate list rows
    DARK_BORDER = "#454545"  # Divider/Border
    DARK_TEXT = "#E0E0E0"  # Primary text
    DARK_TEXT_SEC = "#A0A0A0"  # Secondary text
    DARK_ACCENT = "#4CC2FF"  # Light Blue (WinUI default for dark)
    DARK_ACCENT_HOVER = "#4CC2FF"  # (Simplify for now)
    DARK_ACCENT_TEXT = "#000000"  # Text on accent

    # Light Theme
    LIGHT_WINDOW = "#F3F3F3"  # Mica-like background
    LIGHT_SURFACE = "#FFFFFF"  # Card/Layer background
    LIGHT_SURFACE_ALT = "#FAFAFA"  # Alternate list rows
    LIGHT_BORDER = "#E5E5E5"  # Divider
    LIGHT_TEXT = "#1F1F1F"  # Primary text
    LIGHT_TEXT_SEC = "#5D5D5D"  # Secondary text
    LIGHT_ACCENT = "#0067C0"  # Standard Windows Blue
    LIGHT_ACCENT_HOVER = "#187BCD"
    LIGHT_ACCENT_TEXT = "#FFFFFF"


# -----------------------------------------------------------------------------
# Common QSS Templates
# -----------------------------------------------------------------------------

COMMON_QSS = """
    * {
        font-family: "Segoe UI", "Malgun Gothic", sans-serif;
        font-size: 10pt;
    }
    
    /* -------------------------------------------------------------------------
       Window & Global
       ------------------------------------------------------------------------- */
    QToolTip {
        color: {{text}};
        background-color: {{surface}};
        border: 1px solid {{border}};
        padding: 6px;
        border-radius: 4px;
        font-size: 9pt;
    }
    
    QStatusBar {
        background-color: {{window}};
        color: {{text_sec}};
        border-top: 1px solid {{border}};
    }

    /* -------------------------------------------------------------------------
       Menus & Bars
       ------------------------------------------------------------------------- */
    QMenuBar {
        background-color: {{window}};
        color: {{text}};
        border-bottom: 1px solid {{border}};
        padding: 2px;
    }
    QMenuBar::item {
        background-color: transparent;
        padding: 8px 12px;
        border-radius: 4px;
        margin: 2px;
    }
    QMenuBar::item:selected {
        background-color: {{surface_alt}}; /* Subtle hover effect */
    }

    QMenu {
        background-color: {{surface}}; # card-like
        color: {{text}};
        border: 1px solid {{border}};
        border-radius: 6px;
        padding: 6px;
        /* Padding for the shadow feeling (can't do real shadow in pure QSS easily) */
    }
    QMenu::item {
        padding: 8px 24px 8px 12px; /* Top Right Bottom Left */
        border-radius: 4px;
        margin: 2px 0px;
    }
    QMenu::item:selected {
        background-color: {{accent}};
        color: {{accent_text}};
    }
    QMenu::separator {
        height: 1px;
        background-color: {{border}};
        margin: 4px 0px;
    }

    /* -------------------------------------------------------------------------
       Scrollbars (Modern Thin)
       ------------------------------------------------------------------------- */
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 10px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: {{text_sec}}; /* Use secondary text color for scrollbar */
        min-height: 30px;
        border-radius: 5px;
        margin: 1px;
        /* Make it semi-transparent if possible, or just lighter */
        background-color: rgba(128, 128, 128, 0.4); 
    }
    QScrollBar::handle:vertical:hover {
        background-color: rgba(128, 128, 128, 0.7);
    }
    QScrollBar::handle:vertical:pressed {
        background-color: {{accent}};
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }

    QScrollBar:horizontal {
        border: none;
        background: transparent;
        height: 10px;
        margin: 0px;
    }
    QScrollBar::handle:horizontal {
        background-color: rgba(128, 128, 128, 0.4);
        min-width: 30px;
        border-radius: 5px;
        margin: 1px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: rgba(128, 128, 128, 0.7);
    }
    QScrollBar::handle:horizontal:pressed {
        background-color: {{accent}};
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: none;
    }

    /* -------------------------------------------------------------------------
       Input & Buttons
       ------------------------------------------------------------------------- */
    /* Button: Unobtrusive default */
    QPushButton {
        background-color: {{surface}};
        border: 1px solid {{border}};
        color: {{text}};
        padding: 6px 16px;
        border-radius: 4px;
        font-weight: 500;
    }
    QPushButton:hover {
        background-color: {{surface_alt}};
        border-color: {{border}}; 
    }
    QPushButton:pressed {
        background-color: {{border}}; /* Darker interaction */
        color: {{text}};
    }
    /* Primary Action (if tagged, implementation dependent, here we style all checkables as toggle-like) */

    QLineEdit {
        background-color: {{surface}};
        border: 1px solid {{border}}; 
        border-bottom: 2px solid {{border}}; /* Fluent-like underline hint */
        color: {{text}};
        padding: 5px 8px;
        border-radius: 4px;
        selection-background-color: {{accent}};
        selection-color: {{accent_text}};
    }
    QLineEdit:hover {
        background-color: {{surface_alt}};
    }
    QLineEdit:focus {
        border-bottom: 2px solid {{accent}};
        background-color: {{window}};
    }

    QComboBox {
        background-color: {{surface}};
        border: 1px solid {{border}};
        color: {{text}};
        padding: 5px 8px;
        border-radius: 4px;
    }
    QComboBox:hover {
        background-color: {{surface_alt}};
    }
    QComboBox::drop-down {
        border: none;
        width: 24px;
    }
    QComboBox QAbstractItemView {
        background-color: {{surface}};
        border: 1px solid {{border}};
        selection-background-color: {{accent}};
        selection-color: {{accent_text}};
        color: {{text}};
        outline: 0px;
        padding: 4px;
    }

    /* -------------------------------------------------------------------------
       Lists, Trees & Tables
       ------------------------------------------------------------------------- */
    QTreeView, QListView, QTableView {
        background-color: {{surface}}; 
        /* Alternate background handled by QPalette, but here we can enforce */
        alternate-background-color: {{surface_alt}};
        border: 1px solid {{border}};
        color: {{text}};
        gridline-color: {{border}};
        outline: 0;
    }
    
    QHeaderView::section {
        background-color: {{window}}; /* Subtle header */
        color: {{text_sec}};
        padding: 6px 10px;
        border: none;
        border-bottom: 1px solid {{border}};
        border-right: 1px solid {{border}};
        font-weight: 600;
    }
    QHeaderView::section:last {
        border-right: none;
    }

    /* Selection Logic */
    QTreeView::item, QListView::item, QTableView::item {
        padding: 4px;
        border: none;
    }
    QTreeView::item:selected, QListView::item:selected {
        background-color: {{accent}};
        color: {{accent_text}};
        border-radius: 3px;
    }
    QTreeView::item:hover:!selected, QListView::item:hover:!selected {
        background-color: {{surface_alt}};
        border-radius: 3px;
    }

    /* -------------------------------------------------------------------------
       Specific: Explorer Widgets
       ------------------------------------------------------------------------- */
    /* Thumbnail List (Icon View) */
    #explorerThumbnailList {
        background-color: {{window}}; /* Distinct from sidebar */
        border: none;
        padding: 10px;
    }
    #explorerThumbnailList::item {
        border-radius: 6px;
        padding: 4px;
        margin: 4px; /* Spacious */
    }
    #explorerThumbnailList::item:selected {
        background-color: rgba(76, 194, 255, 0.2); /* Light accent fill */
        border: 1px solid {{accent}};
        color: {{text}};
    }
    #explorerThumbnailList::item:selected:active {
        background-color: rgba(76, 194, 255, 0.3);
    }
    #explorerThumbnailList::item:hover:!selected {
        background-color: {{surface_alt}};
    }

    /* Folder Tree (Sidebar) */
    #explorerFolderTree {
        background-color: {{surface}}; /* Sidebar look */
        border: none;
        border-right: 1px solid {{border}};
        font-size: 10pt;
    }
    #explorerFolderTree::item {
        padding: 6px 4px;
        margin: 2px 4px;
        border-radius: 4px;
    }
    #explorerFolderTree::item:selected {
        background-color: {{surface_alt}}; /* Neutral selection for sidebar usually better? Or accent. */
        /* Let's go with a subtler accent marker style if we could, but for now solid */
        background-color: {{accent}};
        color: {{accent_text}};
    }
    
    /* Detail Tree (Properties) */
    #explorerDetailTree {
        background-color: {{surface}};
        border-top: 1px solid {{border}};
    }
    
    /* Splitter */
    QSplitter::handle {
        background-color: {{border}};
    }
    QSplitter::handle:hover {
        background-color: {{accent}};
    }
"""


def _apply_style(app: QApplication, pal_def: dict) -> None:
    """Apply palette and QSS based on definition dict."""
    app.setStyle("Fusion")

    # 1. Setup QPalette
    # Note: We use QColor(hex_string) which PySide6 supports
    palette = QPalette()

    c_window = QColor(pal_def["window"])
    c_surface = QColor(pal_def["surface"])
    c_text = QColor(pal_def["text"])
    c_accent = QColor(pal_def["accent"])
    c_accent_text = QColor(pal_def["accent_text"])
    c_disabled = QColor(pal_def["text_sec"])

    palette.setColor(QPalette.Window, c_window)
    palette.setColor(QPalette.WindowText, c_text)
    palette.setColor(QPalette.Base, c_surface)
    palette.setColor(QPalette.AlternateBase, QColor(pal_def["surface_alt"]))
    palette.setColor(QPalette.ToolTipBase, c_surface)
    palette.setColor(QPalette.ToolTipText, c_text)
    palette.setColor(QPalette.Text, c_text)
    palette.setColor(QPalette.Button, c_surface)
    palette.setColor(QPalette.ButtonText, c_text)
    palette.setColor(QPalette.Link, c_accent)
    palette.setColor(QPalette.Highlight, c_accent)
    palette.setColor(QPalette.HighlightedText, c_accent_text)

    # Disabled states
    palette.setColor(QPalette.Disabled, QPalette.Text, c_disabled)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, c_disabled)
    palette.setColor(QPalette.Disabled, QPalette.WindowText, c_disabled)

    app.setPalette(palette)

    # 2. Set Font
    # Prefer Segoe UI (Windows standard), then Malgun Gothic (Korean standard), then Generic
    font = QFont("Segoe UI")
    font.setStyleHint(QFont.SansSerif)
    font.setPointSize(10)  # 10pt is readable

    # Check if Segoe UI exists, otherwise fallback?
    # Qt usually handles "Segoe UI" gracefully on Windows.
    app.setFont(font)

    # 3. Process and Set Stylesheet
    # Simple template replacement
    qss = COMMON_QSS
    for key, val in pal_def.items():
        qss = qss.replace(f"{{{{{key}}}}}", val)

    app.setStyleSheet(qss)


def apply_theme(app: QApplication, theme: str = "dark") -> None:
    """Apply a theme to the application.

    Args:
        app: QApplication instance
        theme: Theme name ("dark" or "light")
    """
    if theme == "light":
        pal_def = {
            "window": FluentColors.LIGHT_WINDOW,
            "surface": FluentColors.LIGHT_SURFACE,
            "surface_alt": FluentColors.LIGHT_SURFACE_ALT,
            "border": FluentColors.LIGHT_BORDER,
            "text": FluentColors.LIGHT_TEXT,
            "text_sec": FluentColors.LIGHT_TEXT_SEC,
            "accent": FluentColors.LIGHT_ACCENT,
            "accent_text": FluentColors.LIGHT_ACCENT_TEXT,
        }
    else:
        pal_def = {
            "window": FluentColors.DARK_WINDOW,
            "surface": FluentColors.DARK_SURFACE,
            "surface_alt": FluentColors.DARK_SURFACE_ALT,
            "border": FluentColors.DARK_BORDER,
            "text": FluentColors.DARK_TEXT,
            "text_sec": FluentColors.DARK_TEXT_SEC,
            "accent": FluentColors.DARK_ACCENT,
            "accent_text": FluentColors.DARK_ACCENT_TEXT,
        }

    _apply_style(app, pal_def)


# Legacy aliases if needed, though apply_theme handles both
def apply_dark_theme(app: QApplication) -> None:
    apply_theme(app, "dark")


def apply_light_theme(app: QApplication) -> None:
    apply_theme(app, "light")
