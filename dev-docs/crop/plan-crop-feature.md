# Crop Feature Implementation Plan

## Overview
Implement interactive crop feature that allows users to select a region from the currently displayed image and save the cropped result. Uses existing QPixmap from cache (no re-decoding needed for preview).

## User Flow
1. User views image in View mode (already decoded and cached as QPixmap)
2. Clicks "Crop" in hover menu
3. Modal dialog opens (maximized, not fullscreen) showing the image
4. User drags to create selection rectangle with 8 handles and 4x4 grid overlay
5. Can apply aspect ratio presets from left panel
6. Can toggle between Fit/1:1 zoom modes
7. Clicks "Preview" or Enter → shows cropped region only
8. Clicks "Cancel" or ESC → returns to full image with selection
9. Clicks "Save" → QFileDialog opens with original filename, user chooses final name
10. pyvips crops and saves to disk

## Architecture (3-Layer Separation)

### Layer 1: Backend (crop.py)
Pure functions, no Qt dependencies:
- `apply_crop_to_file(source_path, crop_rect, output_path)` → uses pyvips to crop and save
- `validate_crop_bounds(img_width, img_height, crop)` → bool validation

### Layer 2: Operations (crop_operations.py)
Bridges UI and backend:
- `start_crop_workflow(viewer)` → gets current pixmap from engine cache, opens dialog
- `save_cropped_file(src_path, crop, dest_path)` → calls backend, shows success message

### Layer 3: UI (ui_crop.py)
Dialog and widgets:
- `CropDialog(QDialog)` → main crop interface
- `SelectionRectItem(QGraphicsRectItem)` → interactive selection with handles
- `PresetDialog(QDialog)` → add custom aspect ratio presets

## Key Features

### CropDialog Layout
- **Center:** QGraphicsView with original pixmap
  - No scrollbars (setHorizontalScrollBarPolicy/setVerticalScrollBarPolicy = ScrollBarAlwaysOff)
  - Click-and-drag to pan (setDragMode(ScrollHandDrag))
  - SelectionRectItem overlay with 8 resize handles + 4x4 grid lines

- **Left Panel (QVBoxLayout):**
  - Zoom toggle buttons: "Fit to Window" / "1:1" (controls QGraphicsView transform)
  - QScrollArea with preset buttons (from SettingsManager)
  - "Configure Preset" button → opens PresetDialog

- **Right/Bottom Panel:**
  - "Preview" button (always visible) → shows cropped region only
  - "Cancel" button (hidden initially, shows in preview mode) → restores original
  - "Save" button → opens QFileDialog with original filename as default

### Selection Rectangle
- 8 corner/edge handles for resize
- Paint override for 4x4 grid lines inside selection
- Aspect ratio locking when preset applied
- Coordinate mapping: view → scene → item (for original image coordinates)

### Zoom Modes
- **Fit:** `fitInView(pixmapRect, Qt.KeepAspectRatio)` - default on open
- **1:1:** `resetTransform()` then `scale(1.0, 1.0)` - actual pixels

### Preview Flow
- Get selection coordinates via `SelectionRectItem.get_crop_rect()` → (left, top, width, height)
- Crop QPixmap: `cropped_pix = original_pixmap.copy(QRect(*crop_rect))`
- Replace scene pixmap with cropped version
- Set `_preview_mode = True`, show "Cancel" button
- ESC or Cancel → restore original pixmap, hide "Cancel"

### Save Flow
- QFileDialog with original filename: `QFileDialog.getSaveFileName(self, "Save Cropped Image", original_path, "Images (*.png *.jpg *.jpeg *.webp)")`
- User can keep filename (Windows will prompt if exists) or rename
- Call `crop_operations.save_cropped_file(original_path, crop_rect, chosen_path)`
- Backend uses pyvips: `Image.new_from_file(src).crop(l,t,w,h).write_to_file(dest)`

### Presets Storage
In SettingsManager DEFAULTS:
```python
"crop_presets": [
    {"name": "16:9", "ratio": [16, 9]},
    {"name": "4:3", "ratio": [4, 3]},
    {"name": "1:1", "ratio": [1, 1]},
]
```

## Files to Create

1. **image_viewer/crop.py** (~50 lines)
   - Backend functions using pyvips

2. **image_viewer/crop_operations.py** (~80 lines)
   - Workflow orchestration
   - Bridge between UI and backend

3. **image_viewer/ui_crop.py** (~400 lines)
   - CropDialog with QGraphicsView canvas
   - SelectionRectItem with handles and grid
   - PresetDialog for adding custom ratios
   - Zoom mode toggling
   - Preview/Cancel/Save handlers

## Files to Modify

1. **image_viewer/settings_manager.py**
   - Add `"crop_presets"` to DEFAULTS

2. **image_viewer/main.py**
   - Replace `_on_crop_action()` placeholder with `start_crop_workflow(self)` call

## Technical Details

### Coordinate Mapping
```python
# Selection is in scene coordinates
selection_rect = self._selection_item.rect()

# Map to pixmap item coordinates
item_rect = self._pix_item.mapRectFromScene(selection_rect)

# Extract crop coordinates
left = int(item_rect.x())
top = int(item_rect.y())
width = int(item_rect.width())
height = int(item_rect.height())
```

### QPixmap Crop (for preview)
```python
# Cheap operation, no decoding
cropped = original_pixmap.copy(left, top, width, height)
# or
cropped = original_pixmap.copy(QRect(left, top, width, height))
```

### pyvips Crop (for save)
```python
img = pyvips.Image.new_from_file(source_path, access="sequential")
cropped = img.crop(left, top, width, height)
cropped.write_to_file(output_path)
```

## ESC Key Behavior
- Preview mode: restore original image, stay in dialog
- Original mode: close dialog

## No Re-decoding Needed
- Uses existing QPixmap from `ImageEngine.get_cached_pixmap(current_path)`
- Preview = `QPixmap.copy()` (cheap memory operation)
- Only decode from disk when saving via pyvips

## Testing Strategy
- Manual testing: open crop dialog, select region, preview, save
- Verify coordinate mapping accuracy
- Verify preset application
- Verify zoom mode transitions
- Verify save with original filename shows Windows overwrite prompt

## Implementation Order
1. crop.py (backend)
2. settings_manager.py (add defaults)
3. ui_crop.py (dialog, selection, presets)
4. crop_operations.py (workflow)
5. main.py (wire up menu action)
6. Manual testing
7. ruff + pyright validation
