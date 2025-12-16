# File Explorer Feature Addition Plan

## Goals
- View Mode (current): Display full image on central canvas.
- Explorer Mode (new): Left folder tree + right thumbnail grid.
- Mode switching: Shortcut (e.g., F5) and/or menu.


## Architecture Overview

```
ImageViewer (QMainWindow)
  ↳ Mode flag: view_mode (bool, True=View, False=Explorer)
  ↳ Central Widget (mode-specific switching)
     ↳ View Mode: ImageCanvas (current)
     ↳ Explorer Mode: QSplitter
        ↳ Left:  FolderTreeWidget (folder tree)
        ↳ Right: ThumbnailGridWidget (thumbnail grid)
  ↳ Menu: "View" > "Toggle Explorer Mode" (checkable)
```


## Step 1: Basic Mode Flag and Switching

### Changes in `main.py`

```python
# In __init__
self.view_mode: bool = True  # True = View, False = Explorer

def toggle_view_mode(self) -> None:
    """Toggle between View Mode and Explorer Mode."""
    self.view_mode = not self.view_mode
    self._update_ui_for_mode()
    logger.debug("view_mode toggled: %s", self.view_mode)

def _update_ui_for_mode(self) -> None:
    """Set up the UI based on the current mode flag."""
    if self.view_mode:
        self._setup_view_mode()
    else:
        self._setup_explorer_mode()
```


## Step 2: Preserve Existing View Mode Behavior

### Requirements
- Keep `self.canvas` as-is for View Mode.
- Existing shortcuts and menu actions must continue to work.
- When `self.view_mode = True`, the UI should look exactly like the current viewer.


## Step 3: New UI Components (Explorer Mode)

### 3-1. `FolderTreeWidget` (Folder Tree)

Location: `image_viewer/ui_explorer_tree.py`

```python
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt, Signal
from pathlib import Path


class FolderTreeWidget(QTreeWidget):
    """Folder tree that displays directories and emits signals on selection."""

    folder_selected = Signal(str)  # Emits folder path when user selects a node

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Folder"])
        self.setColumnCount(1)
        self.itemClicked.connect(self._on_item_clicked)
        self.setMinimumWidth(250)

    def set_root_path(self, root_path: str) -> None:
        """Set the root path and rebuild the tree."""
        self.clear()
        root_item = self._build_tree(root_path)
        self.addTopLevelItem(root_item)

    def _build_tree(self, path: str, parent_item: QTreeWidgetItem | None = None) -> QTreeWidgetItem:
        """Recursively build a tree of subfolders."""
        name = Path(path).name or path
        item = QTreeWidgetItem([name])
        item.setData(0, Qt.UserRole, path)  # Store full path

        try:
            for sub_path in sorted(Path(path).iterdir()):
                if sub_path.is_dir() and not sub_path.name.startswith("."):
                    sub_item = self._build_tree(str(sub_path), item)
                    item.addChild(sub_item)
        except PermissionError:
            # Ignore folders we cannot access
            pass

        return item

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Emit folder_selected when a tree item is clicked."""
        path = item.data(0, Qt.UserRole)
        if path:
            self.folder_selected.emit(path)
```

Key points:
- Shows only folders, hides dot-prefixed ones.
- Emits `folder_selected` signal with the selected folder path.
- Lazy loading could be added later if needed.


### 3-2. `ThumbnailGridWidget` (Thumbnail Grid)

Location: `image_viewer/ui_explorer_grid.py`

```python
from PySide6.QtWidgets import QWidget, QGridLayout, QScrollArea, QPushButton
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, Signal
from pathlib import Path
from collections import OrderedDict


class ThumbnailGridWidget(QScrollArea):
    """Scrollable grid of thumbnail buttons."""

    image_selected = Signal(str)  # Emits image path when a thumbnail is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)

        self._container = QWidget()
        self._layout = QGridLayout(self._container)
        self._layout.setSpacing(10)
        self.setWidget(self._container)

        self._buttons: list[QPushButton] = []
        self._thumb_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._columns = 4

    def set_images(self, paths: list[str]) -> None:
        """Populate grid with images from the given list of paths."""
        self._clear_grid()

        row = col = 0
        for path in paths:
            button = QPushButton()
            button.setFixedSize(140, 140)
            button.setIconSize(button.size())
            button.setProperty("image_path", path)
            button.clicked.connect(self._on_button_clicked)

            pixmap = self._thumb_cache.get(path)
            if pixmap is not None:
                button.setIcon(QIcon(pixmap))

            self._layout.addWidget(button, row, col)
            self._buttons.append(button)

            col += 1
            if col >= self._columns:
                col = 0
                row += 1

    def _on_button_clicked(self) -> None:
        button = self.sender()
        if isinstance(button, QPushButton):
            path = button.property("image_path")
            if path:
                self.image_selected.emit(path)

    def _clear_grid(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._buttons.clear()
```

Future work:
- Integrate with `Loader` for asynchronous thumbnail decoding.
- Implement LRU cache management for `_thumb_cache`.


## Step 4: Wiring Explorer Mode in `main.py`

### New helper methods

- `_setup_view_mode()`  
  - Ensure central widget shows the existing `ImageCanvas` layout.
  - Reset or hide explorer widgets if they exist.

- `_setup_explorer_mode()`  
  - Construct a `QSplitter` with `FolderTreeWidget` and `ThumbnailGridWidget`.  
  - Connect signals:
    - `folder_tree.folder_selected` → `open_folder_at(path)` (new helper).  
    - `grid.image_selected` → `on_explorer_image_selected(path)` (new helper).
  - Either:
    - Use `QStackedWidget` as a permanent container, or  
    - Temporarily replace the central widget with the splitter (less robust).

Recommended pattern: **QStackedWidget** as the permanent central widget, with:
- Page 0: `ImageCanvas` (View Mode)
- Page 1: `QSplitter` (Explorer Mode)


## Step 5: Menu and Shortcut Integration

Location: `image_viewer/ui_menus.py`

- Add a checkable menu action:
  - Menu: `View` → `Explorer Mode`
  - Shortcut: `F5`
  - Behavior:
    - Toggling this action calls `toggle_view_mode()` on the viewer.
    - When `view_mode` is `False`, the action is checked.

- Update any UI refresh helpers:
  - Ensure menu state (`setChecked`) matches `viewer.view_mode`.
  - Avoid conflicts with existing fullscreen shortcuts and global `QShortcut` bindings.


## Testing Checklist

1. **Basic Explorer Mode Toggle**
   - Press F5 repeatedly to toggle between View and Explorer modes.
   - Confirm no crashes or “already deleted” widget errors.

2. **Folder Navigation**
   - Tree:
     - Expand several folders; confirm only directories appear.
     - Click a folder node; verify thumbnails update.
   - Thumbnails:
     - Click multiple thumbnails; verify the main canvas shows the selected image.

3. **Integration with Existing Navigation**
   - While in Explorer Mode, check that arrow keys / Home / End behave predictably.
   - Ensure pressing F5 while thumbnails are loading does not crash the app.

4. **Performance**
   - Navigate folders with many images and confirm UI remains responsive.
   - Scroll in thumbnail grid; check that thumbnails appear progressively (once Loader integration is in place).


## Future Enhancements

- LRU thumbnail cache and on-disk cache:
  - `.cache/image_viewer_thumbs/` directory with eviction policy.
- Lazy loading in `FolderTreeWidget`:
  - Load subfolders on demand instead of all at once.
- Additional explorer features:
  - Sort/filter by name, date, or size.
  - Context menu actions (open in viewer, delete to trash, reveal in Explorer).
