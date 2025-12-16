# UI Lock Removal: Structural Improvement Proposals (Image Viewer)

This document outlines structural improvements to eliminate or significantly reduce UI freezing (UI Lock) when opening folders with many images in the `image_viewer` project. The previous patch (removing blocking I/O) was a temporary fix; a more fundamental architectural change is required.

---

### 1. Analysis of Structural Issues

The primary bottleneck for UI locks stems from the reliance on `QFileSystemModel`. While `QFileSystemModel` is a powerful tool for generic file exploration, its design leads to significant overhead and blocking behavior on the main UI thread when dealing with folders containing thousands of files.

| Category | Current State (`QFileSystemModel` based) | Problem Statement |
| :------- | :--------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Data Source** | `QFileSystemModel` internally scans and manages the file system. | When `setRootPath` is called, an initial scan occurs on the main UI thread. Furthermore, its internal file watcher continuously operates, making its behavior difficult to control and causing UI freezes due to frequent data changes. |
| **Duplicate Scans** | `DirectoryWorker` (in `ImageEngine`) and `QFileSystemModel` (in `ImageFileSystemModel`) both scan files independently. | This leads to redundant resource usage and potential data inconsistencies between the independently managed file lists. |
| **UI Updates** | The model performs internal logic upon each file addition (`rowsInserted` signal). | During the loading of a large number of files, this event storm can overwhelm the UI event loop, causing the application to become unresponsive. |

---

### 2. Proposed Improvement: Virtual List Model Architecture

**Core Strategy:**
Replace the heavy `QFileSystemModel` with a lightweight, custom model inheriting from `QAbstractListModel`. The `ImageEngine` will become the sole "Source of Truth" for file data, and the custom model will act as a thin, performant view of this data.

#### Data Flow Transformation
*   **AS-IS:** `UI` -> `Model.setRootPath` (blocking) -> `Model` scans internally.
*   **TO-BE:** `UI` -> `Engine.open_folder` -> `DirectoryWorker` (background scan) -> `Engine` updates its data -> `Model` is notified of a "complete reset" (`layoutChanged` signal).

---

### 3. Detailed Improvement Plan by File

#### A. `image_viewer/image_engine/engine.py` (Strengthening Controller Role)

The `ImageEngine` should fully own and manage the list of image files.

1.  **Centralize Data Ownership:**
    *   The `_file_list_cache` should become the definitive source of truth for the file list within the application.
2.  **Worker Integration for Model Update:**
    *   Once `DirectoryWorker` completes its scan, `ImageEngine` updates its internal file list and then explicitly instructs the `ImageFileSystemModel` to refresh, signaling that its underlying data has been replaced.

```python
# [Proposed Changes in Engine.py]

def open_folder(self, path: str) -> bool:
    # ... existing initialization ...
    
    # 1. Remove call to QFileSystemModel's setRootPath
    # self._fs_model.setRootPath(path)  <-- DELETE THIS LINE
    
    # 2. Initiate background file scan
    self._dir_worker.run(path) 
    return True

def _on_directory_files_ready(self, path: str, files: list[str]):
    # ... validation and duplicate emission checks ...
    self._file_list_cache = files # Update Engine's internal source of truth
    
    # 3. Notify the model of a complete data replacement (single signal)
    self._fs_model.set_file_list(files, path) 
    
    # 4. Initiate asynchronous thumbnail/metadata loading (now via Model's new API)
    self._fs_model.start_async_loading() # New method on the custom model
```

#### B. `image_viewer/image_engine/fs_model.py` (Transition to Lightweight View)

This is the most critical change: removing the `QFileSystemModel` inheritance and replacing it with `QAbstractListModel`.

1.  **Change Base Class:** `QFileSystemModel` -> `QAbstractListModel`.
2.  **Data Access:** The model will no longer scan the file system. Instead, it will reference the `list[str]` provided by the `ImageEngine`.
3.  **Eliminate UI Lock:** Blocking methods like `setRootPath` will be removed. Even with 10,000 items, updating a Python list is instantaneous, and a single `layoutChanged` signal will refresh the UI without freezing.
4.  **Simplify Watcher Logic:** Remove complex `_on_rows_inserted`, `_on_rows_removed`, `_on_model_data_changed` methods as the model will no longer be observing the file system directly; `ImageEngine` will handle file system changes and push updates to the model.

```python
# [Proposed Changes in fs_model.py]

from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex
from pathlib import Path
# ... other imports ...

class ImageFileSystemModel(QAbstractListModel): # Inherit from QAbstractListModel
    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = [] # The actual file paths (read-only reference from Engine)
        self._root_path: str = ""   # Current root path
        # ... existing _thumb_cache, _meta, _loader, etc. ...
        # (Remove all QFileSystemModel-specific connections like rowsInserted, fileRenamed)

    # New public method to receive data from ImageEngine
    def set_file_list(self, files: list[str], root_path: str):
        """Called by ImageEngine after a scan to update the model's data."""
        self.beginResetModel()  # Notify UI that model data is about to be entirely replaced
        self._files = files
        self._root_path = root_path
        # ... clear _thumb_cache, _meta related to old folder ...
        self.endResetModel()    # Notify UI that model data has been replaced

    # Standard QAbstractListModel overrides
    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0 # This is a flat list model
        return len(self._files)

    def data(self, index: QModelIndex, role: int):
        if not index.isValid() or index.row() >= len(self._files):
            return None
        
        path = self._files[index.row()]
        
        if role == Qt.DisplayRole:
            # Return filename for display
            return Path(path).name
        elif role == Qt.DecorationRole:
            # Reuse existing thumbnail caching/loading logic
            return self._thumb_cache.get(path, self._default_icon_placeholder)
        elif role == Qt.ToolTipRole:
            # Reuse existing _build_tooltip
            return self._build_tooltip(path)
        # Add cases for COL_SIZE, COL_TYPE, COL_MOD, COL_RES based on _meta
        elif role == Qt.TextAlignmentRole:
            # Adjust alignment based on column (will need to know current column)
            # This part needs careful redesign as columnCount changes
            pass # Simplified for example
        # ... handle other roles (e.g., meta, size, type, modified date, resolution from _meta) ...
        
        return None

    # Implement other QAbstractListModel required methods:
    def columnCount(self, parent=QModelIndex()):
        return 1 # Or more if we want multiple columns in the list view

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        # ... implement if needed ...
        pass

    # New method to initiate async loading (called by ImageEngine after set_file_list)
    def start_async_loading(self):
        """Starts background loading of cached thumbnails and metadata for the new list."""
        # This will call into FSDBLoadWorker as before, but for the _files list
        # self._db_worker.load_for_paths(self._files, self._root_path, self._thumb_size)
        pass # Placeholder for new DBWorker integration
```

---

### 4. Step-by-Step Implementation Plan

This is a significant refactoring that affects multiple core components.

1.  **Phase 1: Model Re-architecture (`fs_model.py`) - _Start Here_**
    *   Change `ImageFileSystemModel`'s base class from `QFileSystemModel` to `QAbstractListModel`.
    *   Implement `__init__`, `set_file_list`, `rowCount`, `data`, `columnCount`, `headerData`.
    *   Remove all `QFileSystemModel`-specific signal connections (`rowsInserted`, `fileRenamed`, etc.).
    *   Adapt existing `_thumb_cache`, `_meta`, `_request_thumbnail`, `_on_thumbnail_ready`, `_load_disk_icon`, `_save_disk_icon` to work with the new model's `_files` list.
    *   Implement `start_async_loading` to kick off `FSDBLoadWorker` using the internal `_files` list.

2.  **Phase 2: Engine Integration (`engine.py`)**
    *   Modify `open_folder` to use the new `fs_model.set_file_list` and `fs_model.start_async_loading`.
    *   Ensure `_on_directory_files_ready` updates `ImageEngine`'s `_file_list_cache` and then notifies the new model.

3.  **Phase 3: UI Adaptation (`ui_explorer_grid.py`)**
    *   Update `ThumbnailGridWidget` to interact with the new model's API.
    *   Remove calls like `self._model.setRootPath()` and replace them with `self._model.set_file_list()` (via the `ImageEngine`).
    *   Adjust column handling if `columnCount` is changed from 1.

### Summary

The current UI freezing is due to `QFileSystemModel` overloading the main thread. By transitioning to an **`Engine` (data owner) + `QAbstractListModel` (lightweight view)** architecture:
1.  **Eliminate UI Freezing:** File scanning and heavy metadata operations will be fully asynchronous.
2.  **Improve Performance:** Faster folder loading and more responsive UI.
3.  **Cleaner Architecture:** Clear separation of concerns between data management and UI representation.

This is the recommended path for a robust and high-performance solution.