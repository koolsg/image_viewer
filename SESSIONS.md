## 2026-01-06

### Fix: Avoid previous image flash when switching from Explorer → View (T-UI-03)
**Files:** image_viewer/explorer_mode_operations.py
**What:** When selecting an image in Explorer and switching to View mode, the QML view could briefly display the previously shown image before the newly-selected image finished loading. I added an early call to `viewer.app_controller.setCurrentPathSlot(normalized_path)` before switching the UI so the QML controller clears any previous image and starts loading the new one immediately, preventing the transient flash. The change is defensive (wrapped in try/except) to remain compatible with setups that do not use QML.
**Checks:** Ruff: pass; Pyright: pass; Tests: 65 passed
### Cleanup: remove leftover commented sizing lines
**Files:** image_viewer/main.py, image_viewer/file_operations.py
**What:** Removed obsolete commented-out UI sizing lines (`# self.resize(1024, 768)`, `# self.setMinimumWidth(500)`) that were left behind from earlier debugging. These were purely cosmetic/commented traces; no behavior change.
**Checks:** Ruff: pass; Pyright: pass; Tests: 76 passed
## 2026-01-05

### QML Explorer plan update + QML grid model cleanup
**Files:** dev-docs/QML/plan-qml-migration.md, image_viewer/qml_models.py
**What:** Updated the QML migration plan to reflect the decided full QML shell direction and the Explorer priorities (thumbnail grid, metadata, context menu, shortcuts). Also refactored `QmlImageGridModel.data()` to remove a Ruff `PLR0912` “too many branches” violation by switching to a role->getter mapping.
**Checks:** Ruff: pass; Pyright: pass; Tests: 76 passed

### QML ImageProvider & engine integration (T-QLM-02)
**Files:** image_viewer/qml_bridge.py, image_viewer/main.py, tests/test_qml_image_provider.py, tests/test_qml_bridge_integration.py
**What:** Implemented a custom `QQuickImageProvider` to serve images from the engine cache directly to QML, replacing the inefficient base64 data URL approach.
- Added `EngineImageProvider` in `qml_bridge.py` supporting `image://engine/{generation}/{path}` URL scheme.
- Registered the provider in `ImageViewer` (main.py).
- Updated `AppController` to emit `image://` URLs and improved path splitting logic with numeric generation validation.
- Added path decoding (percent-encoding) in `EngineImageProvider` to handle special characters and spaces correctly.
- Added unit tests for the image provider, including percent-encoded path resolution.
**Checks:** Ruff: pass; Pyright: pass; Tests: 65 passed

### QML Viewer POC skeleton (T-QLM-01)
**Files:** image_viewer/qml_bridge.py, image_viewer/main.py, image_viewer/explorer_mode_operations.py, image_viewer/qml/ViewerPage.qml
**What:** Implemented the initial QML Viewer POC.
- Enhanced `AppController` in `qml_bridge.py` with properties (currentPath, zoom, fitMode) and generation tracking.
- Embedded `QQuickView` into `ImageViewer` using `createWindowContainer`.
- Connected `ImageEngine` signals to `AppController` for direct image push to QML via data URLs.
- Updated `explorer_mode_operations.py` to be aware of the QML container during mode switching.
- Created a functional `ViewerPage.qml` that displays images and handles stale results via generation IDs.
**Checks:** Ruff: pass; Pyright: (manual check of imports); POC ready for manual verification.

### Pyvips-first thumbnail encoding (no QImage fallback)

**Files:** image_viewer/image_engine/engine_core.py, tests/test_enginecore_vips_thumb_encode.py
**What:** Replaced thumbnail PNG encoding to use **pyvips** directly from decoded RGB numpy arrays (`_numpy_to_png_bytes_vips`), removing the QImage encoding fallback for thumbnails as requested. Added a unit test validating odd-width RGB encodes.
**Checks:** Ruff: pass; Pyright: 0 errors; Tests: 58 passed

### 문서화: 디코딩 아키텍처 한글 기술
**Files:** dev-docs/architecture_description/deconding_architecture.md
**What:** 전체 이미지 디코딩 및 썸네일 디코딩의 함수/스레드/프로세스 관점 아키텍처, 데이터 흐름, 성능 위험과 개선 방안을 한국어로 정리해 문서화함. 또한 왜 현재 아키텍처를 선택했는지(장점, 대안 및 선택하지 않은 이유)를 명시.
**Checks:** 문서 추가 완료; 관련 코드 참조 확인

## 2026-01-04

### Strict thumbnail DB schema + remove legacy compatibility
**Files:** image_viewer/image_engine/db/thumbdb_bytes_adapter.py, image_viewer/image_engine/db/thumbdb_core.py, image_viewer/image_engine/thumbnail_cache.py, image_viewer/image_engine/db/__init__.py, image_viewer/image_engine/__init__.py, image_viewer/image_engine/fs_db_worker.py, image_viewer/crop/ui_crop.py
**What:**
- Centralized the thumbnail DB schema into a single spec and generated SQL via f-strings (including column types/constraints).
- Enforced strict schema validation; when the on-disk schema/version mismatches, the thumbnails table is dropped and recreated (no migrations/compat).
- Removed legacy `ThumbDB`/`ThumbDBOperatorAdapter` and legacy `ThumbnailCache` implementation code (modules now fail fast if imported).
- Unified crop preset UI so “Configure Preset” is the single entry point (removed the separate “add preset” path).
**Checks:** Ruff: pass; Pyright: 0 errors; Tests: 55 passed, 7 skipped

### Fix EngineCore ThumbDBBytesAdapter operator access
**Files:** image_viewer/image_engine/engine_core.py, tests/test_enginecore_db_operator_wiring.py
**What:** Fixed DB preload startup to use `ThumbDBBytesAdapter.operator` (public API) instead of referencing a non-existent private `_db_operator` attribute.
**Checks:** Ruff: pass; Pyright: 0 errors; Tests: 56 passed

### Harden EngineCore thumbnail PNG encoding
**Files:** image_viewer/image_engine/engine_core.py, tests/test_enginecore_png_encode.py
**What:** Made thumbnail PNG encoding more robust by converting to ARGB32 and encoding via `QImageWriter`; added a regression test for odd-width RGB888 thumbnails.
**Checks:** Ruff: pass; Pyright: 0 errors; Tests: 57 passed

### Explorer: avoid sparse thumbnail grid on empty DB
**Files:** image_viewer/image_engine/engine_core.py
**What:** Make DB preload `prefetch_limit` dynamic (min(image_count, 256)) so small folders queue thumbnail generation for all missing images instead of only the first 48.
**Checks:** Ruff: pass; Pyright: 0 errors; Tests: 57 passed

### Explorer: generate all missing thumbnails (throttled)
**Files:** image_viewer/image_engine/fs_db_worker.py, image_viewer/image_engine/engine_core.py
**What:** FSDB worker now emits *all* missing/outdated thumbnail paths in chunks; EngineCore queues them and requests thumbnail decodes in small batches via a timer so the grid eventually fills completely without a decode storm.
**Checks:** Ruff: pass; Pyright: 0 errors; Tests: 57 passed


## 2025-12-25

### Add mouse wheel zoom to crop dialog with 25% multiplication ratio
**Files:** image_viewer/crop/ui_crop.py
**What:** Implemented wheelEvent() method in CropDialog to enable interactive zoom on the crop canvas:
- Scroll up: 1.25x zoom in
- Scroll down: 0.8x zoom out
- Zoom applied directly via `QGraphicsView.scale()` transform
- Scale clamped to 0.1–10.0 range to prevent extreme zoom levels
- Proper event handling: `event.accept()` on success, `event.ignore()` on error
- Robust exception handling with debug logging
- No conflicts with existing SelectionRectItem mouse handling (SelectionRectItem only accepts LeftButton, doesn't override wheelEvent)
**Analysis:** Confirmed SelectionRectItem handles only left-mouse events; wheelEvent bubbles up to CropDialog without interference
**Checks:** Ruff: pass; Pyright: 0 errors; Tests: 36 passed

### Center previewed image in crop dialog (fix left-aligned preview)
**Files:** image_viewer/crop/ui_crop.py
**What:** Fixed an issue where the cropped preview shown after pressing Preview was left-aligned in the view. The preview (and restored original) are now centered by resetting the pixmap offset and calling `QGraphicsView.centerOn()` after `fitInView`.
- Reset item offset via `self._pix_item.setOffset(0, 0)` (safe, suppressed exceptions)
- Call `self._view.centerOn(self._pix_item)` to center the pixmap in the viewport
- Added defensive `contextlib.suppress` blocks and debug logging around the fit/center steps
**Checks:** Ruff: pass; Pyright: 0 errors; Tests: 36 passed

### Route hover debug to overlay; suppress console debug output
**Files:** image_viewer/crop/ui_crop_selection.py
**What:** Prevent hover debug messages (e.g., "hoverMoveEvent called: pos=... last_hit=...") from being emitted to the console. Instead, when the crop dialog debug overlay is enabled, hover info is shown in the dialog's bottom-left overlay via `DebugOverlay.show_message()` and not through `logger.debug()`.
- Replaced the console `_logger.debug(...)` call in `SelectionRectItem.hoverMoveEvent` with an overlay-only message when available
- Ensured message forwarding is guarded and exceptions are suppressed to avoid noisy console output
**Checks:** Ruff: pass; Pyright: 0 errors; Tests: 36 passed

### Move debug overlay to left panel + show mouse position & cursor-exit
**Files:** image_viewer/crop/ui_crop.py, image_viewer/crop/ui_crop_debug_overlay.py, image_viewer/crop/ui_crop_selection.py
**What:** Moved the debug overlay from the canvas viewport to the **left panel bottom-left** and added messages showing mouse coordinates and cursor state. The `_CropCursorResetFilter` now forwards mouse coordinates and cursor names to the overlay on hover/move events and displays a `cursor=exit` message when the cursor leaves the selection area. Overlay repositioning now watches the left panel resize events.
**Checks:** Ruff: pass (lint warnings from older code unchanged); Pyright: 0 errors; Tests: 36 passed

### Debug overlay: table layout, fixed rows, left column always visible
**Files:** image_viewer/crop/ui_crop_debug_overlay.py, image_viewer/crop/ui_crop_selection.py, image_viewer/crop/ui_crop.py, tests/test_debug_overlay_table.py, tests/test_preview_centering.py, tests/test_cursor_behavior.py
**What:** Improved the debug overlay to use a fixed set of rows and a two-column layout:
- Fixed row keys (in order): `mouse`, `hit`, `cursor`, `handler`, `info` (left column) — these labels are always shown
- Right column displays the corresponding values; if a value is missing/empty the right cell is left blank
- If none of the rows contain any value, the overlay hides itself to avoid showing an empty box
- Callers now pass structured dicts (e.g., `{"mouse": "x,y", "hit": "MOVE", "cursor": "OpenHandCursor"}`)
**Checks:** Ruff: pass; Pyright: 0 errors; Tests: 38 passed

### Document dummy hover usage in cursor tests & guard super() call
**Files:** tests/test_cursor_behavior.py, image_viewer/crop/ui_crop_selection.py
**What:** Added a concise comment in `tests/test_cursor_behavior.py` explaining why a lightweight hover helper is used instead of `QGraphicsSceneHoverEvent` (forwarding full Qt events can trigger internal C++/Python type checks that raise TypeError in tests). Also added a guard in `SelectionRectItem.hoverMoveEvent` to only call `super().hoverMoveEvent(event)` when `event` is a real `QGraphicsSceneHoverEvent`, preventing TypeError when tests pass simple dummies.
**Checks:** Ruff: pass; Pyright: 0 errors; Tests: 36 passed

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

