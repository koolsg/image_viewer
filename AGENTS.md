# Explanation aboiut this project

## Project overview

Desktop image viewer built with PySide6, using multi-process image decoding via pyvips and NumPy. The viewer supports two decoding modes (fast thumbnail vs full-resolution), a status overlay instead of a status bar, an explorer mode (folder tree + thumbnail grid), batch trimming, and WebP batch conversion. Backend logic and decoders live under the `image_viewer/image_engine/` package.

Code is organized into the `image_viewer/` package for application logic and UI, and `tests/` for unit/integration tests.

## Development environment & dependencies

- Python: 3.11+
- Package/dependency management: `uv` with `pyproject.toml` and `uv.lock`.
- Core runtime deps (from `pyproject.toml`): `pyside6`, `pyvips[binary]`, `numpy`, `send2trash`.
- Dev tools: `pytest`, `ruff`, `pyright`, `pyside6-stubs`.
- Windows-specific note: if pyvips DLLs are not discoverable on `PATH`, follow the README guidance (e.g. install `pyvips[binary]` or configure `LIBVIPS_BIN` via a `.env` file next to the app).

## Common commands

All commands assume the repo root (`image_viewer`) as the working directory.

### Environment setup

- Sync dependencies (recommended):
  - `uv sync`

### Running the application

-- Run the viewer (uv-managed environment):
- `uv run python -m image_viewer`
- Run with a specific Python (venv or system):
  - `python -m image_viewer`
- Optional CLI arguments (parsed before Qt):
  - `--log-level <debug|info|warning|error|critical>`
  - `--log-cats <comma-separated logger suffixes>`

You can also provide an optional positional `start_path` to `image_viewer.main.run` (file or folder) to control startup behavior:
  - `image_viewer <image file>` → open its folder, show that image, enter fullscreen View mode (use `python -m image_viewer <image>` or the `run()` function).
- `image_viewer <folder>` → open in Explorer mode, maximized.
- No path → Explorer mode, maximized.

> Packaging/installation as a console script is not wired in `pyproject.toml`; current flow is to run the module directly as above.

### Tests

- Run the full test suite (pytest over `tests/`):
  - `uv run pytest`
- Example: run a single test module:
  - `uv run pytest tests/test_trim.py`

Some tests require optional imaging libraries (`numpy`, `pyvips`) and will be skipped if those are unavailable.

### Linting, formatting, and type checking

Configured in `pyproject.toml`:

- Ruff lint (E/F/I/UP/B/SIM/PL/RUF; `tests` are excluded by config):
  - `uv run ruff check image_viewer`
- Ruff format (code formatting):
  - `uv run ruff format image_viewer`
- Pyright type checking (targets `image_viewer`, with relaxed rules for stub-heavy libs like PySide6/pyvips):
  - `uv run pyright`

## High-level architecture

**Responsibility boundary:** UI components (widgets, dialogs) act only as command-issuers and result-displayers. All filesystem mutations (file operations) and thumbnail DB writes/reads are performed by `image_viewer/image_engine` and its `ImageFileSystemModel`/`ThumbnailCache`/`ThumbDB` helpers. This ensures the UI remains light, testable, and that file/DB logic is centralized in the engine.

### Entry points and application shell

- `image_viewer/__main__.py`
  - Defines `main()` which calls `image_viewer.main.run()`. This is the console entrypoint when the package is executed as a module.
- `image_viewer/main.py`
  - Applies CLI logging options (`--log-level`, `--log-cats`) before Qt sees `sys.argv`, by setting `IMAGE_VIEWER_LOG_LEVEL` / `IMAGE_VIEWER_LOG_CATS`.
  - Defines `ImageViewer(QMainWindow)`, the main window coordinating all subsystems:
    - Maintains `ViewState`, `TrimState`, and `ExplorerState` (mode and explorer widgets).
    - Holds `image_files` and `current_index` and owns the central `ImageCanvas` widget for display.
    - Uses a single `ImageEngine` instance for decoding, thumbnail loading, and pixmap caching (the engine owns loaders and cache).
    - Wires up menus, status overlay builder, and explorer/view-mode bindings.
  - `run(argv=None)`: full application bootstrap.
    - Creates `QApplication`, installs theme, constructs `ImageViewer`.
    - Interprets optional `start_path` (file vs folder vs none) to choose between fullscreen View mode or Explorer mode.

### Decoding pipeline and async loading

  - `image_viewer/image_engine/decoder.py`
  - Pure decoding layer based on `pyvips` and `numpy`.
  - `decode_image(path, target_width=None, target_height=None, size="both")`:
    - Uses `pyvips.Image.thumbnail` / `new_from_file` to decode from disk.
    - Normalizes to 3-channel `uint8` RGB arrays, performing color space conversion and alpha flattening when needed.
    - Intended to be process-safe / pickleable for use from `ProcessPoolExecutor`.

- `image_viewer/image_engine/loader.py`
  - Orchestrates file I/O and multi-process decoding. `ImageEngine` owns one general `Loader` instance and one thumbnail-only `Loader` instance; UI components interact with `ImageEngine` rather than talking to loaders directly.
  - Holds a `ProcessPoolExecutor` for CPU-heavy decoding and a small `ThreadPoolExecutor` as an I/O scheduler.
  - Public API:
    - `request_load(path, target_width=None, target_height=None, size="both")` queues a decode, assigning monotonically increasing request IDs per path.
    - Emits `image_decoded(path, numpy_array_or_None, error_or_None)` when a decode completes.
    - `ignore_path` / `unignore_path` let callers drop late results (e.g., deleted files).
  - Internally tracks `_pending` and `_latest_id` to discard stale or ignored results before emitting.

- `image_viewer/image_engine/strategy.py`
  - Defines decoding strategies used by the viewer:
    - `FastViewStrategy`: decodes near viewport/screen resolution for speed, does **not** support HQ downscale.
    - `FullStrategy`: always decodes at original resolution and **does** support HQ downscale.
  - `DecodingStrategy` exposes `get_target_size`, `get_name`, and `supports_hq_downscale` to consumers.

### Image Engine (backend)

- `image_viewer/image_engine/engine.py`
  - `ImageEngine` is the single entry point for file system, decoding, prefetch, and caching responsibilities.
  - Signals: `image_ready(path, QPixmap, error)`, `folder_changed(path, file_list)`, `thumbnail_ready(path, QIcon)`, `file_list_updated(list)`.
  - Public API:
    - `open_folder(path)`: sets root path and triggers directory scan.
    - `get_image_files()`: returns current sorted image file list.
    - `request_decode(path, target_size)`: enqueue a decode request; emits `image_ready` on completion.
    - `get_cached_pixmap(path)`: return a cached `QPixmap` or None.
    - `prefetch(paths, target_size)`: enqueue prefetch requests for neighboring images.
    - `cancel_pending(path=None)`: cancel pending decode requests or ignore a specific path via loader.
    - `set_decoding_strategy(strategy)` / `get_decoding_strategy()`: manage the active decoding strategy.
  - `ImageEngine` owns loader instances and the LRU pixmap cache; UI components should call into the engine rather than creating their own loaders or caches.

-- `ImageViewer` + `ImageEngine` (UI/backend responsibilities)
  - The display responsibilities are implemented across `ImageViewer` (UI) and `ImageEngine` (backend):
  - `ImageViewer` exposes UI methods such as `open_folder()`, `display_image()`, and `maintain_decode_window()`, while `ImageEngine` owns decoding machinery and caches.
  - `open_folder()` (UI/Viewer):
    - Uses `QFileDialog` to select a directory (the `ImageViewer.open_folder()` path). In View mode: resets decode state, queries `ImageEngine` for files, updates `image_files`/`current_index`, and invokes `display_image()` and `maintain_decode_window()`. In Explorer mode: updates the folder tree and thumbnail grid via `Explorer`/FS model APIs.
  - `display_image()` (UI/Viewer):
    - First checks the `ImageEngine` pixmap cache via `engine.get_cached_pixmap()`.
    - On cache miss: determines target decode size from the active `DecodingStrategy` and calls `engine.request_decode(path, target_size)`.
  - `on_image_ready(path, image_data, error)`:
    - Converts the returned RGB array to `QImage`/`QPixmap` on the GUI thread, updates engine cache, records decoded size for status overlay, and calls `viewer.update_pixmap` if the path is still current.
    - Skips updates while a trim preview is active.
  - `maintain_decode_window(back=3, ahead=5)`:
    - Prefetches neighboring images around `current_index`, respecting fast-view and screen size for thumbnails.

### Canvas, view modes, and overlay

- `image_viewer/ui_canvas.py`
  - `ImageCanvas(QGraphicsView)` is the central image viewer widget:
    - Maintains zoom state (`_preset_mode` = "fit" or "actual", `_zoom` factor) and optional HQ downscale cache.
    - Implements mouse and keyboard interactions:
      - Ctrl+wheel zoom, plain wheel for previous/next image.
      - Left-click press-to-zoom (temporary zoom around cursor using configurable multiplier, then restore on release).
      - Middle-click snap-to-global-view, right-click drag panning, extra mouse buttons for zoom in/out.
    - Overrides `apply_current_view` to:
      - Reset transforms and set rotation around the pixmap center.
      - For "fit" mode: either `fitInView` or a high-quality downscale path using `pyvips` plus `numpy`.
      - For "actual" mode: apply a scale transform based on `_zoom`.
    - Re-runs the viewer’s status overlay update after applying view changes.
  - `drawForeground` renders the top-left overlay box:
    - Reads `_overlay_title` and `_overlay_info` from the window (the `ImageViewer`).
    - Chooses text color based on background luminance.
    - Optionally shows `pixmap_cache` debug info in debug logging mode.

- `image_viewer/status_overlay.py`
  - `StatusOverlayBuilder` builds the string components for the overlay:
    - Decorates current strategy name (`[fast view]` or `[original]`).
    - Reports file resolution and decoded output resolution when available.
    - Computes and displays scale factor (`@ {scale:.2f}x`) using the helper methods on `ImageViewer` (`_get_file_dimensions`, `_get_decoded_dimensions`, `_calculate_scale`).

### Explorer mode and thumbnail caching

- `image_viewer/explorer_mode_operations.py`
  - Implements the View vs Explorer mode switch and associated UI wiring.
  - Core functions:
    - `toggle_view_mode(viewer)` flips `ExplorerState.view_mode` and calls `_update_ui_for_mode`.
    - `_setup_view_mode(viewer)` ensures that the central widget is the `ImageCanvas` (reusing or recreating it as needed), and stores/restores window geometry for transitions.
    - `_setup_explorer_mode(viewer)` wraps the canvas into a `QStackedWidget` and adds a second page containing a `QSplitter` with folder tree and thumbnail grid.
      - Reuses existing explorer widgets when possible for performance.
      - Connects tree and grid signals and applies persisted thumbnail layout settings from `SettingsManager`.
    - `_on_explorer_folder_selected` / `_on_explorer_image_selected` delegate to grid and viewer operations.

- `image_viewer/ui_explorer_tree.py`
  - `FolderTreeWidget(QTreeWidget)` displays the folder hierarchy:
    - Builds a tree rooted at a given path, skipping hidden/permission-denied directories.
    - Emits `folder_selected(path: str)` when a node is clicked; explorer operations connect this to grid loading.

- `image_viewer/ui_explorer_grid.py`
  - Contains the explorer model and views for thumbnail and detail display.
  - `ImageFileSystemModel(QFileSystemModel)`:
    - Extends the standard FS model with:
      - A "Resolution" column derived from `QImageReader` and cached file metadata.
      - Thumbnail icons cached in memory (`_thumb_cache`) and optionally persisted via `ThumbnailCache`.
      - Custom formatting for size and type columns, and metadata-rich tooltips.
    - Integrates with `Loader` via `set_loader`, listening to `image_decoded` to populate thumbnails.
  - The associated thumbnail grid widget (see remaining parts of `ui_explorer_grid.py`) manages view mode (thumbnail vs detail), context menus, keyboard shortcuts, and uses `ThumbnailCache` for on-disk caching.

  - `image_viewer/image_engine/thumbnail_cache.py`
  - `ThumbnailCache` stores thumbnails in a SQLite DB under a dedicated cache directory:
    - Schema tracks path, mtime, file size, original dimensions, thumbnail size, and PNG-encoded thumbnail bytes. The on-disk DB by default is named `SwiftView_thumbs.db` inside the target folder.
    - `get(...)` validates mtime/size and requested thumbnail dimensions before returning a `QPixmap` and optional original size.
    - `set(...)` encodes a `QPixmap` to PNG and upserts into the DB.
    - `cleanup_old(days)` and `vacuum()` support periodic maintenance.
    - On Windows, marks the DB file as hidden via Win32 APIs.

### Settings, themes, and user preferences

- `image_viewer/settings_manager.py`
  - `SettingsManager` wraps a JSON file (`settings.json` in the app base directory) with defaults for:
    - Background color, fast-view toggle, press-zoom multiplier.
    - Explorer thumbnail width/height, spacing, and cache name.
  - Provides `get/has/set`, automatic persistence on `set`, and convenience accessors such as `fast_view_enabled`, `last_parent_dir`, and `determine_startup_background()`.

- `image_viewer/styles.py`
  - Theme system for the entire Qt application:
    - `apply_theme(app, theme="dark")` dispatches to `apply_dark_theme` or `apply_light_theme` (dark theme is implemented here).
    - Dark theme uses Fusion style plus a modern palette and stylesheet rules, with special IDs for explorer widgets (e.g. `#explorerThumbnailList`, `#explorerDetailTree`, `#explorerFolderTree`, `#explorerSplitter`).

- `image_viewer/ui_settings.py`
  - `SettingsDialog` provides a preferences UI, backed by `SettingsManager` and current explorer grid state:
    - Appearance page: theme selector (`dark` / `light`), calling `viewer.apply_theme(theme)`.
    - Thumbnail page: thumbnail width/height and horizontal spacing; calls `viewer.apply_thumbnail_settings(...)`.
    - View page: press-zoom multiplier; calls `viewer.set_press_zoom_multiplier(...)`.
  - Tracks dirty state and only enables "Apply & Save" when there are changes.

### File operations and batch tools

- `image_viewer/file_operations.py`
  - `delete_current_file(viewer)` implements the "Delete to Recycle Bin" behavior:
    - Confirms with the user, moves focus to a different image first (to avoid deleting the file currently displayed by Qt), then uses `send2trash` with retry logic.
    - Updates `pixmap_cache`, `image_files`, and `current_index`, and clears the view/state when the last image is removed.
    - Integrates with `Loader.ignore_path` to drop in-flight decode results for the deleted file.

  - `image_viewer/trim.py` and `image_viewer/trim_operations.py`
  - `trim.py` contains pure functions for content-aware trimming using pyvips + numpy:
    - `detect_trim_box_stats(path, profile)` computes a bounding box for non-background content, with a simple threshold and optional "aggressive" profile.
    - `make_trim_preview(path, crop)` returns a cropped preview as an RGB array.
    - `apply_trim_to_file(path, crop, overwrite, alg=None)` writes the cropped image back (overwriting or creating `<name>.trim<ext>`).
  - `trim_operations.py` orchestrates the interactive workflow from the viewer:
    - Prompts for sensitivity profile and save mode (overwrite vs save-copy).
    - For save-copy: runs a batch job over `image_files` with `TrimBatchWorker` and `TrimProgressDialog`.
    - For overwrite: loops through images, shows a preview in the main canvas, and asks for per-image confirmation (with Y/N/A shortcuts); invalidates cache and redisplays as needed.
    - Uses `viewer.trim_state` flags to prevent re-entry and coordinate with display updates.

- `image_viewer/webp_converter.py` and `image_viewer/ui_convert_webp.py`
  - `webp_converter.py` implements a worker and controller for batch WebP conversion using pyvips:
    - Scans folders for supported image extensions, optionally resizes so the shorter side matches a target, writes WebP with configurable quality, and optionally deletes originals.
  - `ui_convert_webp.py` defines `WebPConvertDialog`:
    - UI for choosing folder, resize/quality/delete options, and monitoring conversion progress/log output.
    - Used from the "Tools → Convert to WebP..." menu item in the main window.

### Logging and utilities

  - `image_viewer/logger.py`
  - Centralized logging setup.
  - `setup_logger` respects environment variables for log level and category filters, ensures a single `StreamHandler` on the base logger, and configures a consistent formatter.
  - `get_logger(name)` returns child loggers (e.g. `image_viewer.main`, `image_viewer.loader`).

- `image_viewer/busy_cursor.py`
  - `busy_cursor()` is a small context manager that switches the global cursor to `WaitCursor` during long operations and restores it afterwards; used around decode, delete, and other potentially slow actions.

## Tests overview

- Tests live under `tests/` and primarily exercise non-UI logic:
  - `tests/test_trim.py` covers `detect_trim_box_stats` and related trim behavior with synthetic images.
  - Other scripts in `tests/` (e.g. geometry/fullscreen experiments) are more exploratory or integration-style.
- Use `pytest` as the primary test runner (see commands above); some tests use `unittest` but are still discoverable by pytest.

# AGENTS — Operations SOP (Automation & Resume Rules)

This document defines the operating procedures for agents working on this repository.

## Document Structure

```
AGENTS.md          → Operational SOP (this file)
TASKS.md           → Multi-step task plans and in-progress tracking
SESSIONS.md        → Short records of completed work
```

**Single Source of Truth (SoT):** TASKS.md (task plans) and SESSIONS.md (session logs) are the canonical operational documents. `control.yaml` and `CONTROL_PANEL.md` are legacy files kept only for historical records under `dev-docs` and should not be used for tracking current work.

## Purpose

Short, focused guidance so an agent can start a session and know how to plan, implement, and report work without reading other files.

### Quick Start

1. Ensure environment health: `uv run ruff check . --fix` then `uv run pyright`.
2. Open `TASKS.md` and `SESSIONS.md`. If there is no user-specified task, pick a High Priority item from `TASKS.md`.
3. If the task is short (one prompt), implement and log in `SESSIONS.md`. If it is multi-step, add a plan to `TASKS.md` first.

## Session Checklist

1. Read `TASKS.md` (High Priority section).
2. Scan recent `SESSIONS.md` entries for context.
3. Confirm any environment or dependency notes in `pyproject.toml`.

## Work Rules (must follow)

- Single-prompt tasks: Record only in `SESSIONS.md` (short entry: date, summary, files, checks).  (사용자 기준 1-prompt 작업은 `SESSIONS.md`만 기록)
- Multi-step tasks: Add a `TASKS.md` entry with steps, files, and decision points before starting and update it as you progress.
- Always run `uv run ruff check . --fix` and `uv run pyright` before marking work complete. Include the results in `SESSIONS.md`.
- **Commit Messages**: All automated or agent-generated commit messages must be in English.

## Reporting & Completion

1. Run checks: `uv run ruff check . --fix`, `uv run pyright`, and tests if applicable (`uv run pytest`).
2. Update `TASKS.md` status to `completed` (if used).
3. Add a `SESSIONS.md` entry with files changed, short description, and checks:

```
## YYYY-MM-DD

### Short title
**Files:** path/to/file.py
**What:** One-line description
**Checks:** Ruff: pass; Pyright: pass; Tests: pass
```

4. Report to the user with a short summary and next steps.

## Templates (minimal)

- `SESSIONS.md` entry: see above.
- `TASKS.md` entry example:

```
- [ ] T-###: Short title — plan: 1) step 2) step 3) verify
  - files: path/to/file
  - notes: blockers/decisions
```

## Code Quality

- Use `uv run ruff check . --fix` and `uv run pyright` frequently. They must pass (0 errors) before reporting completion.

## When to ask the user

- If scope, acceptance criteria, or design decisions are unclear.
- If linters or tests show errors you cannot resolve locally.

## Final Note

Keep entries concise and actionable so another agent can resume work from `TASKS.md` and `SESSIONS.md` alone.

