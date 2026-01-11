# Crop: Legacy Widgets vs QML — Status and Migration Plan

Summary
- The project historically shipped a QWidget-based crop UI under `image_viewer/crop/` (notably `ui_crop.py`, `ui_crop_selection.py`, `ui_crop_debug_overlay.py`).
- A new QML-first Crop mode (`image_viewer/ui/qml/CropPage.qml` plus `backend.crop` state and controller logic) was added and is the recommended UI for the app shell.
- The backend crop logic (pyvips-based) remains in `image_viewer/crop/crop.py` and is still used by runtime code to perform the actual cropping/save operation.

Current usage classification

1) Runtime / Production (keep)
- `image_viewer/crop/crop.py` — `apply_crop_to_file(...)`: core backend crop implementation, used by `BackendFacade` and by some operations.
- `image_viewer/crop/crop_operations.py` — workflow helpers (save path handling, prefetch coordination).
- `image_viewer/app/backend.py` imports `apply_crop_to_file` and calls it when QML crop save event fires.

2) Legacy Widget UI (candidate for removal or archiving)
- `image_viewer/crop/ui_crop.py` — `CropDialog(QDialog)` classic dialog, used by some legacy scripts and tools.
- `image_viewer/crop/ui_crop_selection.py` — `SelectionRectItem` and `_HandleItem` interactive selection code.
- `image_viewer/crop/ui_crop_debug_overlay.py` — on-canvas debug overlay used by debug tools.

3) Tests and tooling that still rely on Widget UI (need transition)
- `tests/helpers/selection_test_ui.py` uses `SelectionRectItem` for unit tests of selection logic.
- `tools/run_selection_demo.py`, `scripts/debug_crop_zoom.py`, `scripts/debug_crop_setup.py`, `scripts/debug_call_impl.py` instantiate `CropDialog` for interactive demos and developer workflows.

Migration objectives (short)
- Preserve and keep authoritative backend crop functions (`crop.py`) and tests around crop correctness.
- Move tests and developer scripts off Widget UI and either target:
  - the backend crop functions directly (for non-UI behavior), or
  - the new QML crop UI via higher-level test helpers (for integration/UX tests).
- After tests/tools are migrated and CI is passing, archive or remove `ui_crop*.py` files.

Planned steps (next actions)
1. Document this status (this file) and add deprecation notes at the top of `ui_crop.py`.
2. Replace scripting/demo usage of `CropDialog` with direct `apply_crop_to_file` calls where appropriate (or a small CLI/test helper wrapper in `image_viewer/crop/` for reproducible behavior).
3. Update tests to exercise `SelectionRectItem` logic via a lightweight test harness (if needed) or port tests to pure non-UI helpers where possible.
4. Run full test suite & QML smoke tests. Once green, remove or archive Widget UI files in a separate cleanup change.

Acceptance criteria
- No production code paths rely on `ui_crop.py` for normal app usage.
- Developer tools and tests no longer import `CropDialog` directly; they either call `apply_crop_to_file` or use a documented test helper.
- CI/tests remain green.

If you want, I can now:
- (A) add a short deprecation header to `image_viewer/crop/ui_crop.py` and create a small test helper in `image_viewer/crop/` to call `apply_crop_to_file` (for scripts) — low-risk, quick win.
- (B) update a few demo scripts and tests to use the helper / backend API so we can validate before removing UI files.

Which should I start with? (I can do A then B in sequence.)