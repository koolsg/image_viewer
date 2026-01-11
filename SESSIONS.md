## 2026-01-11

### QML: Crop mode (normalized rect + overlay preview + pan)
**Files:** image_viewer/app/backend.py, image_viewer/app/state/crop_state.py, image_viewer/ops/crop_controller.py, image_viewer/ui/qml/CropPage.qml, image_viewer/ui/qml/ViewWindow.qml, image_viewer/ui/qml/ViewerShortcuts.qml, tests/test_crop_controller.py
**What:** Added an initial QML-first crop mode driven by a new `backend.crop` state object. The crop rectangle is stored as normalized (0..1) coordinates, rendered with an overlay mask, and supports resize handles, moving the selection, wheel zoom, and Space-held pan. Preview is non-destructive (mask/overlay + live preview panel sampling the current image). Saving uses `pyvips` crop via `image_viewer.crop.crop.apply_crop_to_file` and reports results through `backend.taskEvent` (`name: "cropSave"`).
**Checks:** Ruff: pass; Pyright: pass; Tests: 7 passed

### QML: View mode Del key delete confirmation
**Files:** image_viewer/ui/qml/ViewerShortcuts.qml, image_viewer/ui/qml/ViewWindow.qml, image_viewer/ui/qml/ViewerPage.qml
**What:** Implemented View-mode delete on the `Delete` key using the existing `DeleteConfirmationDialog` owned by `ViewWindow`. The shortcut now lives in `ViewerShortcuts.qml` (so all view-only shortcuts are centralized) and triggers `showViewDeleteDialog(currentPath)`; on confirmation it dispatches `deleteFiles` (Recycle Bin) via the existing backend command.
**Checks:** pyside6-qmllint: pass; Ruff: pass; Pyright: pass; Tests: 3 passed

### QML: Fix Explorer thumbnail left-click selection
**Files:** image_viewer/ui/qml/ExplorerSelectionOverlay.qml
**What:** Fixed Explorer thumbnail left-click selection by parenting the selection overlay to the GridView viewport (not the Flickable contentItem). This makes click coordinates consistent with the existing `contentX/contentY` offset logic and restores reliable thumbnail clicks.
**Checks:** pyside6-qmllint: pass; Tests: 3 passed

### Perf: Thumbnail ImageProvider QPixmap LRU cache + diagnostics
**Files:** image_viewer/app/backend.py, .vscode/tasks.json
**What / 문제:** Explorer grid에서 썸네일이 `image://thumb/...`로 다시 요청될 때마다 `QPixmap.loadFromData(png_bytes)` 디코딩이 반복되어 CPU를 태우고 스크롤/리사이즈 시 끊김이 발생.
**Fix / 해결:** `ThumbImageProvider` 내부에 QPixmap LRU 캐시(키: thumb id)를 추가해 동일 썸네일 요청 시 디코딩을 생략. 또한 `thumb_cache` 로거로 `thumb_lru HIT/MISS/EVICT` 및 주기적 stats 로그를 추가해 히트율/효과를 검증 가능하게 함. VS Code task("Run Image Viewer (Thumb LRU Cache Logs Only)")를 추가해 콘솔과 `debug.log`에 동일한 필터링 로그만 기록하도록 구성.
**Checks:** (not rerun in this entry); Manual runtime: HIT 로그로 캐시 동작 확인

### QML: Fix Explorer wrong item picked after scrolling
**Files:** image_viewer/ui/qml/ExplorerSelectionOverlay.qml
**What / 문제:** 스크롤을 많이 내린 뒤 클릭하면, 클릭 좌표→index 계산을 `cellWidth/cellHeight`로 직접 나누는 방식(수동 col/row 계산) 때문에 GridView의 실제 레이아웃/라운딩/여백과 미세하게 어긋나 잘못된 index가 선택됨.
**Fix / 해결:** 클릭 hit-test를 수동 수학에서 `GridView.indexAt(contentX+mouse.x, contentY+mouse.y)` 기반으로 변경하여, GridView가 실제로 배치한 item geometry로부터 index를 얻도록 수정.
**Checks:** pyside6-qmllint: pass

### Infra: Migrate legacy crop widget usage -> deprecate UI, add helpers & tests
**Files:** image_viewer/crop/ui_crop.py, image_viewer/crop/ui_crop_selection.py, image_viewer/crop/dev_helpers.py, scripts/debug_call_impl.py, scripts/debug_crop_setup.py, tests/test_crop_backend.py, dev-docs/crop/legacy_vs_qml_migration.md
**What:** Began migration to reduce reliance on the legacy QWidget-based crop UI:
- Added deprecation header to `ui_crop.py` and `ui_crop_selection.py` to mark them as legacy and recommend `image_viewer/ui/qml/CropPage.qml` and `image_viewer.crop.apply_crop_to_file`.
- Added `image_viewer/crop/dev_helpers.py` with utilities (`make_test_pixmap`, `apply_crop_to_tempfile`) intended for scripts/tests to call the backend crop implementation without instantiating UI dialogs.
- Updated developer scripts (`scripts/debug_call_impl.py`, `scripts/debug_crop_setup.py`) to use the dev helpers instead of instantiating `CropDialog`.
- Added `tests/test_crop_backend.py` with a pyvips shim to ensure `apply_crop_to_file` behavior is covered by unit tests.
**Checks:** Unit tests added: `tests/test_crop_backend.py` — passed locally; pyside6-qmllint: n/a

### QML: DeleteConfirmationDialog keyboard shortcuts + focus UX
**Files:** image_viewer/ui/qml/DeleteConfirmationDialog.qml
**What / Goal:** Make delete confirmation fast in keyboard flow (Del → Enter) by defaulting focus to **Yes**, while still keeping a safe/clear UX via visible focus indication and predictable key bindings.

**Implemented:**
- Buttons changed to **Yes / No** (Yes first) and wired to existing signals:
  - Yes → `acceptedWithPayload(payload)`
  - No → `rejectedWithPayload(payload)`
- Default focus: `Yes` gets initial focus (`focus: true`) so `Del → Enter` confirms.
- Enter/Return: activates the **currently focused** button (not "always delete").
- Y/N shortcuts: `Y` confirms, `N` cancels.
- Arrow keys: Left/Right move **focus only** between Yes/No (do not activate).
- Esc: closes immediately **without emitting** accept/reject signals.
- Focus visuals: both buttons now show a clearer focused state (border + subtle color shift) using `activeFocus`.

**What was broken / Why:**
- In Qt Quick Controls, when a `Dialog` (Popup) is modal and a `Button` has focus, key events like Enter/Return can be consumed by the focused control and **not reliably delivered** to `Keys.on*Pressed` handlers on the Dialog.
- Similarly, arrow keys may not reach Dialog-level handlers depending on focus and control behavior.

**Fix / How:**
- Centralized accept/reject into `dlg._acceptNow()` / `dlg._rejectNow()` and a focus-aware dispatcher `dlg._activateFocusedButton()`.
- Added explicit `Shortcut { sequence: "Return" }` and `Shortcut { sequence: "Enter" }` with `context: Qt.WindowShortcut` so Enter/Return reliably triggers `dlg._activateFocusedButton()` even when a control has focus.
- Set `Keys.priority: Keys.BeforeItem` and added `KeyNavigation.left/right` between the Yes/No buttons for predictable focus navigation.

**Checks:** pyside6-qmllint: pass; Tests: 3 passed

### QML: Explorer PageUp/PageDown grid navigation
**Files:** image_viewer/ui/qml/App.qml
**What:** Added `PageUp` / `PageDown` navigation in the Explorer grid keyboard handler. The jump size is computed dynamically from the current viewport and thumbnail sizing by estimating how many full rows fit (`Math.floor(grid.height / grid.cellHeight)`) and multiplying by the current column count (`computedCols`). This keeps paging behavior consistent across window resizes and different thumbnail sizes.
**Checks:** pyside6-qmllint: pass; Ruff: pass; Pyright: pass; Tests: 3 passed

### QML: Extract Rename dialog into its own file
**Files:** image_viewer/ui/qml/RenameFileDialog.qml, image_viewer/ui/qml/AppDialogs.qml
**What:** Refactored the Explorer F2 rename UI so the rename dialog lives in its own reusable component (`RenameFileDialog.qml`), similar to `DeleteConfirmationDialog.qml`. `AppDialogs.openRenameDialog()` now configures and opens the component, and dispatches `renameFile` via `acceptedWithPayload({path,newName})`.
**Checks:** pyside6-qmllint: pass; Ruff: pass; Pyright: pass; Tests: 3 passed

## 2026-01-10

### Remove unused legacy helpers in main/styles/engine
**Files:** image_viewer/main.py, image_viewer/ui/styles.py, image_viewer/image_engine/engine.py
**What:** Deleted duplicate/unused QML image providers and payload coercion helpers from `main.py` (providers now live in `BackendFacade`), removed legacy theme alias functions from `ui/styles.py`, and dropped an unused legacy `_on_image_decoded` hook from `ImageEngine`. This reduces noise and eliminates dead code without affecting the QML-first app path.
**Checks:** Ruff: pass; Pyright: pass; Tests: 3 passed

### QML: Centralize Controls palette in Theme
**Files:** image_viewer/ui/qml/Theme.qml, image_viewer/ui/qml/App.qml
**What:** Moved the app-wide Qt Quick Controls palette values into `Theme.qml` as `theme.palette` and bound `ApplicationWindow.palette` to it, so palette policy lives in one place and stays consistent across the UI.
**Checks:** pyside6-qmllint: pass; Tests: 3 passed

### QML: Fix DeleteConfirmationDialog modal behavior and layout overflow
**Files:** image_viewer/ui/qml/DeleteConfirmationDialog.qml, image_viewer/ui/qml/AppDialogs.qml
**What:** Fixed a bug where the Delete confirmation dialog allowed background clicks and could be closed by clicking the parent window. Root causes were incorrect parenting and layout overflow: dialog was not using the window overlay for modality and its content layout used `anchors.fill` causing implicit sizing issues that let the buttons render outside the dialog. Fixes:
- Parent dialogs to the window overlay (fallback to `contentItem`) so Qt Quick Controls' modal dimming and input blocking work.
- Set `closePolicy: Popup.NoAutoClose` and `dim: true` on the dialog so outside clicks don't close it and the background is dimmed.
- Replace `anchors.fill` usage with dialog `padding` and rely on `implicitHeight` for content; wrap long text in a `ScrollView` and give buttons stable `implicitHeight`/`implicitWidth` so buttons cannot overflow the dialog bounds.
- Add a small draggable header area so dialogs can be moved by the user.
**Checks:** pyside6-qmllint: pass; Manual verification: modal scrim blocks background clicks, clicking the parent no longer closes the dialog, buttons fully visible and dialog draggable; Tests: 3 passed

### Dev: document Qt Quick backend overrides and log when applied
**Files:** image_viewer/main.py, dev-docs/qt_quick_backend_overrides.md
**What:** Added debug logging to `main.py` so when `IMAGE_VIEWER_QSG_RHI_BACKEND` or `IMAGE_VIEWER_QT_QUICK_BACKEND` is used we record the applied override (`IMAGE_VIEWER_QSG_RHI_BACKEND -> QSG_RHI_BACKEND=...`). Also added `dev-docs/qt_quick_backend_overrides.md` with one-line usage examples and notes.
**Checks:** pyside6-qmllint: n/a; Tests: 3 passed

> NOTE (2026-01-10): QML 단일 경로는 `image_viewer/ui/qml/` 입니다. 과거 기록에 남아있는 `image_viewer/qml/*` 경로는 레거시이며 현재는 제거되었습니다.
**Files:** image_viewer/ui/qml/App.qml
**What:** Fixed Windows frameless-drag artifacts where the custom titlebar appeared to lag/"trail" behind the window during drag by disabling layer caching on the titlebar and restricting the drag handler to a dedicated drag region (excluding the window buttons). Also anchored the minimize/maximize/close glyphs so they remain properly centered and consistent across DPI/font metrics. Finally, fixed MenuBar items rendering as blank by wiring the custom MenuBar delegate to the underlying `Menu` objects (`modelData.title` + `menu: modelData`).
**Checks:** pyside6-qmllint: pass; Manual run: launched (UI verification recommended)

### QML: Restore MenuBar labels after delegate changes
**Files:** image_viewer/ui/qml/App.qml
**What:** Fixed a regression where the top MenuBar appeared to be "missing" because the custom `MenuBarItem` delegate was not bound to the underlying `Menu` model objects. Restored `text: modelData.title` and `menu: modelData` so the menubar shows "File/View/..." and opens correctly.
**Checks:** pyside6-qmllint: pass; Manual run: launched; Tests: 3 passed

## 2026-01-09

### QML boundary cleanup: remove `main` shims; stub legacy Main(QObject)
**Files:** image_viewer/qml/App.qml, image_viewer/qml/ViewerPage.qml, image_viewer/qml/ConvertWebPDialog.qml, image_viewer/main.py
**What:** Finished the remaining QML compatibility cleanup by removing the `main`-based facade injection shims and standardizing on a direct `backend` property for components. Replaced the unused legacy `Main(QObject)` QML bridge with a fail-fast stub so accidental imports are caught immediately.
**Checks:** Ruff: pass (2 fixed); Pyright: pass; Tests: 3 passed

### Remove Python shim modules; migrate imports to layered packages
**Files:** image_viewer/main.py, image_viewer/app/backend.py, image_viewer/image_engine/*, image_viewer/crop/*, image_viewer/trim/*, tests/*
**What:** Removed top-level compatibility shims (`image_viewer/logger.py`, `path_utils.py`, `settings_manager.py`, `file_operations.py`, `webp_converter.py`, `styles.py`, `qml_models.py`) and migrated all imports to canonical modules under `image_viewer/infra`, `image_viewer/ops`, and `image_viewer/ui`.
**Checks:** Ruff: pass (2 fixed); Pyright: pass; Tests: 3 passed

## 2026-01-07

### Fix: Rename dialog UX polish and fixes (T-UI-06)
**Files:** image_viewer/qml/App.qml, dev-docs/UI/shortcuts_and_input_map.md
**What / 문제:** The rename dialog (triggered by F2 in Explorer) sometimes opened with missing or invisible filename text, appeared in the top-left instead of centered, the selection/cursor wasn't visible on dark theme, and pressing Enter did not confirm the dialog. The label also could overlap the dialog title on some platforms.
**Fix / 해결방법:**
- Restricted the F2 handler to Explorer only and require exactly one selected item before opening the rename dialog.
- Populate `renameDialog.initialName` from the selected path and ensure the `TextField` is refreshed on `onOpened`.
- Force focus to the dialog and `TextField` on open and call `selectAll()` to select the full filename (extension included).
- Parent the dialog to `root.contentItem` and compute `x/y` from the parent size; add implicit size and a top spacer so the title does not overlap content.
- Improve `TextField` styling for dark theme (text color, selection colors, cursor delegate, padding, preferred height) so filename and cursor are visible.
- Add `Keys.onReturnPressed` to the `TextField` so Enter accepts the dialog and triggers rename.
**Checks:** Manual verification: F2 opens dialog centered; filename is visible and selected; typing and Enter confirm rename and filesystem rename occurs.

### Fix Rename Dialog Filename Population (T-UI-05)
**Files:** image_viewer/qml/App.qml
**What:** Fixed issue where rename dialog (F2) was not populating the filename correctly or was showing stale data.
- Updated regex to handle both backslashes and forward slashes when extracting filename from path.
- Updated `renameDialog.onOpened` to unconditionally refresh the text field from `initialName`, fixing stale/empty text issues caused by broken bindings on reused dialogs.
**Checks:** pyside6-qmllint: pass

### QML→Python logging + reliable thumbnail double-click (T-UX-04)
**Files:** image_viewer/qml/App.qml, image_viewer/main.py
**What:** Integrated QML debug logging into the Python logging pipeline by routing QML messages through the existing `Main.qmlDebug()` slot. `qmlDebug()` now logs at DEBUG via the Python logger and prints to stderr for early visibility. Removed an earlier `qmlLogger` context property to avoid ambiguous access patterns. Fixed unreliable thumbnail double-click behavior by moving detection to the overlay `selectionMouse` (350ms interval) which reliably receives left-clicks; on double-click it sets `Main.currentIndex` and flips `Main.viewMode` and emits an explicit `[QML] [THUMB] DOUBLE-CLICK idx=...` message via `qmlDebug()`. Simplified delegate `MouseArea` to handle right-click context menu only and consolidated event ownership in the overlay.
**Checks:** Ruff: pass; Pyright: pass; Manual runtime verification: pending (please trigger a double-click and paste the debug output)

### Improve QML logging reliability & visibility (T-LOG-01)
**Files:** image_viewer/qml/App.qml, image_viewer/main.py, image_viewer/logger.py
**What / 문제:**
- QML-origin debug messages were sometimes missing from runtime logs (no `[QML]` lines in `debug.log`), and in one case a `TypeError` occurred when QML passed a single JS string payload containing special characters to `Main.performDelete` (error converting argument 0 to PySide::PyObjectWrapper).
- QML-side early lifecycle messages fired before the `main` object was attached to the root, causing messages to be lost.

**해결방법 / Fix:**
- In `App.qml`: added `qmlDebugSafe(msg)` which queues messages until `root.main` is available and flushes them once bound; replaced direct `root.main.qmlDebug(...)` calls in startup and lifecycle handlers with `qmlDebugSafe(...)` to make reporting reliable.
- In `App.qml`: ensure `Delete` confirmation handlers pass an array when invoking `performDelete` (`root.main.performDelete(Array.isArray(p) ? p : [p])`) to avoid conversion errors for single strings with exotic characters.
- In `main.py`: added a `@Slot(str)` overload to `performDelete` and added debug logging that prints the incoming payload's Python class name and a repr for diagnosis.
- Added an immediate startup call (`main.qmlDebug("[STARTUP] main property set on QML root")`) after setting `root.main` to validate the binding and verify message flow.
- In `logger.py`: added a lightweight highlight formatter that detects the `[QML]` marker and highlights those lines (ANSI magenta) in terminal output for visibility.
- Replaced an emoji marker with plain `[QML]` prefix and made stderr prints use ANSI coloring for terminal visibility. Also added a toggle-ready design (can add env var option later if needed).

**Checks / 검증:**
- Ruff: pass; Pyright: pass
- Manual runtime verification:
  - Startup debug message appears: `[QML] [STARTUP] main property set on QML root` (also printed to stderr)
  - QML-origin messages are present in `debug.log` (prefixed by `[QML]`) and stand out in terminal due to magenta highlighting
  - `performDelete` logs payload type and repr; sample deletes (including filenames with special characters) succeeded and printed: `performDelete called with payload type=str payload='...path...'`

**Next steps:**
- Optionally add an environment toggle to disable ANSI coloring (for environments that do not support it), or route `[QML]` messages to a separate file `debug.qml.log` if the team prefers separation of concerns.

### Feature: Explorer Delete shortcut (T-EX-02)
**Files:** image_viewer/qml/App.qml, image_viewer/main.py, image_viewer/file_operations.py
**What / 기능:** Implemented Explorer-mode deletion triggered by the **Del** key. When one or more items are selected in the thumbnail grid and Del is pressed, the app shows the Delete confirmation dialog; accepting moves the selected files to the Recycle Bin and refreshes the folder listing.

**해결방법 / 구현 세부:**
- In `App.qml`: added a `Keys.onPressed` branch for `Qt.Key_Delete` that gathers `grid.selectedIndices`, maps them to paths, then calls `root.showDeleteDialog(title, "", info, paths)` where `paths` is always an array (even for single-item deletes).
- In `App.qml`: ensured QML delete dialog handlers call `root.main.performDelete(Array.isArray(p) ? p : [p])` so Python receives an array and avoids PySide conversion errors for exotic filenames.
- In `main.py`: added a `@Slot(str)` overload to `performDelete` and diagnostic logging (payload class + repr); `performDelete` coalesces the payload via `_coerce_paths` and calls `delete_files_to_recycle_bin(paths)`.
- Reused `file_operations.delete_files_to_recycle_bin()` which uses `send2trash` for cross-platform Recycle Bin support and logs success/failure per file.

**Checks / 검증:**
- Ruff: pass; Pyright: pass
- Manual runtime verification: pressing Del with single and multiple selections shows confirmation dialog; accepting deletes files (including paths with special characters) and `debug.log` shows `performDelete called with payload type=str ...` and `delete complete` entries; folder listing refreshes.



### Fix: Thumbnail DB worker emission & idle/awake bug (T-DB-01)
**Files:** image_viewer/image_engine/fs_db_worker.py, image_viewer/image_engine/engine_core.py, image_viewer/image_engine/db/thumbdb_core.py
**What / 원인:** FSDB worker occasionally suppressed or delayed emission of missing/outdated thumbnail paths due to an "idle/awake" optimization and coarse chunking logic; thumbnails were not queued reliably and Explorer's grid appeared sparsely populated.
**해결방법:** Removed the idle/awake suppression and changed the worker to emit missing/outdated thumbnail paths in deterministic, small chunks. `EngineCore` now queues thumbnail decode requests using a short throttle timer to avoid decode storms while ensuring eventual completion. Added defensive checks and unit tests to validate chunked emission and throttled decode behavior.
**Checks:** Ruff: pass; Pyright: pass; Tests: updated & manual verification recommended

## 2026-01-06

### Fix: Avoid previous image flash when switching from Explorer → View (T-UI-03)
**Files:** image_viewer/explorer_mode_operations.py
**What:** When selecting an image in Explorer and switching to View mode, the QML view could briefly display the previously shown image before the newly-selected image finished loading. I added an early call to `viewer.app_controller.setCurrentPathSlot(normalized_path)` before switching the UI so the QML controller clears any previous image and starts loading the new one immediately, preventing the transient flash. The change is defensive (wrapped in try/except) to remain compatible with setups that do not use QML.
**Checks:** Ruff: pass; Pyright: pass; Tests: 65 passed
### QML Viewer: Mouse interaction support (press-to-zoom, right-drag pan, middle-click fit) (T-QLM-03)
**Files:** image_viewer/qml/ViewerPage.qml, tests/test_qml_mouse_interactions.py
**What:** Added mouse-driven interactions to the QML Viewer:
- Left-click (press): temporary press-to-zoom; release restores zoom
- Right-click + drag: manual panning via Flickable contentX/contentY
- Middle-click: snap to fit (fit mode)
- Ctrl+Wheel: zoom; Wheel alone navigates prev/next image

Also added `tests/test_qml_mouse_interactions.py` to validate press-to-zoom and middle-click fit behavior.
**Checks:** Ruff: pass; Pyright: pass; Tests: 78 passed
## 2026-01-05

### QML Explorer plan update + QML grid model cleanup
**Files:** dev-docs/QML/plan-qml-migration.md, image_viewer/qml_models.py
**What:** Updated the QML migration plan to reflect the decided full QML shell direction and the Explorer priorities (thumbnail grid, metadata, context menu, shortcuts). Also refactored `QmlImageGridModel.data()` to remove a Ruff `PLR0912` "too many branches" violation by switching to a role->getter mapping.
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
- Unified crop preset UI so "Configure Preset" is the single entry point (removed the separate "add preset" path).
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
- Scale clamped to 0.1-10.0 range to prevent extreme zoom levels
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
