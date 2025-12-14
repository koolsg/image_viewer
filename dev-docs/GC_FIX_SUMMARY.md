# Canvas Garbage Collection Issue - Fix Summary

## Problem Statement
When switching between View Mode and Explorer Mode, the `ImageCanvas` object was being garbage collected by PySide6, resulting in:
```
ERROR: Internal C++ object (ImageCanvas) already deleted.
ERROR: Internal C++ object (PySide6.QtWidgets.QGraphicsPixmapItem) already deleted.
```

## Root Cause Analysis
1. **Widget Lifecycle Issue**: When calling `setCentralWidget(splitter)` to display explorer UI, PySide6 automatically garbage collects the previous central widget (canvas).

2. **Parent-Child Relationship Problem**: Simply storing `self.canvas` in a Python variable doesn't prevent PySide6's C++ memory manager from deleting the widget when it's no longer the central widget.

3. **Direct Widget Swapping Approach Fails**: Attempts to preserve canvas via:
   - `takeCentralWidget()` + `setParent()` → Still garbage collected
   - `setParent(self)` before/after setCentralWidget() → Race condition, canvas deleted before parent can be set
   - Explicit parent management → Canvas becomes invalid C++ object

## Solution Implemented: QStackedWidget Architecture

### Key Insight
Instead of swapping widgets in/out of the central widget position, use a **QStackedWidget as a persistent central container** that holds both the canvas and explorer UI.

```
QMainWindow
  └─ QStackedWidget (permanent central widget)
      ├─ Page 0: ImageCanvas (View Mode)
      └─ Page 1: QSplitter with FolderTreeWidget + ThumbnailGridWidget (Explorer Mode)
```

### Implementation Details

#### `_setup_explorer_mode()` (Lines 1132-1208)
```python
# First time: Create stacked widget container
if not isinstance(current_widget, QStackedWidget):
    stacked_widget = QStackedWidget()
    stacked_widget.addWidget(self.canvas)  # Page 0 (View Mode)
    self.setCentralWidget(stacked_widget)   # Permanent central widget

# Add/replace explorer splitter as Page 1
stacked_widget.addWidget(splitter)  # Page 1 (Explorer Mode)
stacked_widget.setCurrentIndex(1)   # Show explorer UI
```

**Benefits:**
- Canvas remains in the stacked widget tree permanently → Never garbage collected
- Page switching via `setCurrentIndex()` is just visibility change, not widget reparenting
- Simple and clean separation between View and Explorer modes

#### `_setup_view_mode()` (Lines 1068-1113)
```python
# If using stacked widget, just switch pages
if isinstance(current_widget, QStackedWidget):
    current_widget.setCurrentIndex(0)  # Show canvas page
else:
    # Fallback for edge cases
    # Set canvas as central widget with error recovery
```

**Benefits:**
- No widget reparenting or garbage collection risk
- Page switch is O(1) visibility operation
- Graceful fallback if stacked widget not initialized

## How It Works

### Initial State (First Launch)
```
QMainWindow
  └─ ImageCanvas (central widget)
```

### First Mode Switch (View → Explorer)
```
QMainWindow
  └─ QStackedWidget (becomes permanent central widget)
      ├─ Page 0: ImageCanvas (hidden)
      └─ Page 1: QSplitter (visible)
             ├─ FolderTreeWidget
             └─ ThumbnailGridWidget
```

### Subsequent Mode Switches
```
Only visibility changed via setCurrentIndex(0) or setCurrentIndex(1)
No widgets are reparented or deleted
Canvas C++ object remains valid throughout application lifetime
```

## Testing Recommendations

1. **Basic Mode Toggle**: Repeatedly press F5 to toggle modes (10+ times)
2. **Image Selection**: Select images in explorer thumbnails, verify canvas displays them
3. **Rapid Switching**: Toggle modes while thumbnails are loading
4. **Folder Navigation**: Navigate folders in tree widget, select images
5. **State Validation**: 
   - Check canvas reference remains valid after each mode switch
   - Verify no "already deleted" errors in logs
   - Confirm canvas displays images correctly in both modes

## Files Modified
- `image_viewer/main.py`:
  - `_setup_view_mode()` (lines 1068-1113)
  - `_setup_explorer_mode()` (lines 1132-1208)

## Key Learnings

### What NOT to Do
- ❌ Don't try to manage canvas lifecycle with multiple `setParent()` calls
- ❌ Don't swap widgets as central widget repeatedly
- ❌ Don't rely on variable references to prevent garbage collection

### What Works
- ✅ Use a persistent container widget (QStackedWidget) as central widget
- ✅ Keep all "mode" widgets in the container from initialization
- ✅ Switch between modes via visibility/index changes, not reparenting
- ✅ This aligns with Qt's memory management design patterns

### Architecture Pattern
This solution implements the **Widget Container Pattern** where a stable container holds multiple alternative UI layouts and switches between them without destroying/recreating widgets.

## Future Improvements
- Consider using `QStackedWidget` from the start in new PySide6 projects requiring mode switching
- Document this pattern in project guidelines for avoiding similar GC issues
- Can extend to more than 2 modes (View, Explorer, Thumbnail, etc.) by adding more pages

## References
- Qt Documentation: QStackedWidget
- PySide6 Memory Management: Widget ownership and garbage collection
- Design Pattern: Container Pattern for UI mode switching
