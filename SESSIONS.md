## 2025-12-22

### Logging refactor: Move cursor/coordinate debug output to overlay
**Files:** image_viewer/crop/ui_crop_selection.py
**What:** Replaced console-based debug logging (`_logger.debug()`, `_logger.info()`) with on-screen overlay display for cursor shapes and coordinates. Changes:
- Removed `_logger.info("hoverMove: ...")` from `_log_hit_transition()`
- Removed `_logger.debug()` calls in `hoverEnterEvent()`, `hoverMoveEvent()`, `hoverLeaveEvent()`
- Removed `_logger.debug()` calls in `Handle._HandleItem.mousePressEvent()`
- Removed console logging in `Handle._HandleItem.mouseMoveEvent()`; kept overlay display
- Removed `_logger.debug()` calls in `Selection.mousePressEvent()` (two instances removed)
- Removed `_logger.debug()` from fallback drag, mouseReleaseEvent, resize_handle_to, _compute_drag_target_view_rect, _apply_view_rect_to_parent
- Maintained internal `_transition_log_history` and `_handle_move_log_history` lists for test compatibility
- All debug info now shown via `DebugOverlay.show_message()` in bottom-left corner
**Result:** Clean console output; interactive cursor/coordinate debug info displayed on-screen overlay when `_debug_overlay` is attached
**Checks:** Ruff: pass; Py compile: pass; Verification: console info/debug removed ✅, overlay calls present ✅

### Crop module cleanup: remove heavy root shim + fix pytest collection
**Files:** image_viewer/ui_crop.py, pyproject.toml, tests/conftest.py
**What:**
- Replaced the legacy root-level `image_viewer/ui_crop.py` monkey-patching shim with a tiny, side-effect-free re-export module.
- Restricted pytest discovery to `tests/` (`testpaths = ["tests"]`) so helper scripts like `tools/test_db_creation.py` are not imported during collection.
- Added a session-wide `QApplication` bootstrap/teardown in `tests/conftest.py` to keep Qt initialization consistent across runs.
**Checks:** Ruff: pass; Pyright: pass; Tests: 36 passed

## 2025-12-19

### Crop feature implementation (interactive region selection + preview)
**Files:** image_viewer/crop.py, image_viewer/crop_operations.py, image_viewer/ui_crop.py, image_viewer/settings_manager.py, image_viewer/main.py, dev-docs/plan-crop-feature.md
**What:** Implemented complete crop feature using existing QPixmap from cache (no re-decoding for preview). Modal dialog with maximized window showing: interactive selection rectangle with 8 resize handles + 4x4 grid overlay, Fit/1:1 zoom toggle, customizable aspect ratio presets (stored in settings), instant preview via QPixmap.copy(), save with QFileDialog (user chooses filename, Windows handles overwrite prompt), backend uses pyvips.crop() for final save. Click-drag to pan, no scrollbars. ESC cancels preview or closes dialog.
**Checks:** Ruff: pass; Pyright: pass

### Fix: `CropDialog` modal maximize behavior
**Files:** image_viewer/ui_crop.py
**What:** Resolved issue where the modal `CropDialog` opened too small on some platforms. Changes:
- Kept dialog modal (workflow requirement) and added maximize/close window hints.
- In `showEvent`, attempt a real OS maximize via `setWindowState(... | Qt.WindowMaximized)` shortly after show; if the window manager ignores this (common for modal/transient cases), fall back to sizing the dialog to the screen's `availableGeometry()` with a small margin so it appears maximized-like.
- Re-apply `fitInView` after layout stabilizes using `QTimer.singleShot`.
- Added `QSizePolicy` adjustments and `setMinimumSize(640, 480)` for more robust initial layout.
- Replaced `try/except: pass` with `contextlib.suppress(Exception)` and cleaned imports.
**Checks:** Ruff: pass; Pyright: pass; Tests: crop-related UI tests passed (12/12), fullscreen checks passed.
**Notes:** Ran ruff fixes and `pyright` after changes; added a short maximize fallback delay to let the window manager honor maximize when possible.

