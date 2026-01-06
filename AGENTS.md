# Central Agent Rules

This file (.agents.md) is the single source of truth
for all AI agents and tools, including GitHub Copilot, Gemini, and others.

Any agent-specific instruction file must defer to this document.

# Explanation aboiut this project

## Project overview

Desktop image viewer built with PySide6, using multi-process image decoding via pyvips and NumPy. The viewer supports two decoding modes (fast thumbnail vs full-resolution), a status overlay instead of a status bar, an explorer mode (folder tree + thumbnail grid), batch trimming, and WebP batch conversion. Backend logic and decoders live under the `image_viewer/image_engine/` package.

Code is organized into the `image_viewer/` package for application logic and UI

## Development environment & dependencies

- Python: 3.11+
- Package/dependency management: `uv` with `pyproject.toml` and `uv.lock`.
- Core runtime deps (from `pyproject.toml`): `pyside6`, `pyvips[binary]`, `numpy`, `send2trash`.
- Dev tools: `ruff`, `pyright`, `pytest`, `pytest-qt`, `pyside6-stubs`. `pyside6-qmllint`
- Windows-specific note: if pyvips DLLs are not discoverable on `PATH`, follow the README guidance (e.g. install `pyvips[binary]` or configure `LIBVIPS_BIN` via a `.env` file next to the app).

## Common commands

All commands assume the repo root (`image_viewer`) as the working directory.

### Tests

- Run tests (pytest as module):
  - `uv run python -m pytest`

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



### Linting, formatting, and type checking

Configured in `pyproject.toml`:

- Ruff lint (E/F/I/UP/B/SIM/PL/RUF;
  - `uv run python -m ruff check --fix .`
- Ruff format (code formatting):
  - `uv run python -m ruff format .`
- Pyright type checking (targets `image_viewer`, with relaxed rules for stub-heavy libs like PySide6/pyvips):
  - `uv run python -m pyright`

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
  - `ImageFileSystemModel` (lightweight `QAbstractTableModel`):
    - The model no longer directly wraps `QFileSystemModel` or perform inline SQLite scans.
    - Folder scanning and DB reads are performed by the engine-core thread (`EngineCore`) using `FSDBLoadWorker`, which queries the thumbnail DB via `ThumbDB` or `ThumbDBOperatorAdapter` and emits `chunk_loaded` payloads that populate the model.
    - The model exposes columns such as `Resolution` and other cached file metadata and keeps an in-memory thumbnail cache (`_thumb_cache`) for fast display. It requests thumbnails from the engine loader when missing, and otherwise reads bytes via `ThumbDBBytesAdapter` when available.
    - Design goal: keep UI fast and thread-safe by avoiding direct DB connections and heavy IO on the GUI thread.
  - The associated thumbnail grid widget (see remaining parts of `ui_explorer_grid.py`) manages view mode (thumbnail vs detail), context menus, keyboard shortcuts, and uses `ThumbnailCache`/`ThumbDBBytesAdapter` for on-disk caching when appropriate.

  - `image_viewer/image_engine/thumbnail_cache.py` / `image_viewer/image_engine/db/thumbdb_bytes_adapter.py`
  - Thumbnails and metadata are stored in a SQLite DB (`SwiftView_thumbs.db`) and are accessible via the `ThumbDB`/`ThumbDBOperatorAdapter` and `ThumbDBBytesAdapter` compatibility helpers.
    - `ThumbnailCache` provides a UI-friendly wrapper for `QPixmap` → PNG bytes conversions and prefers operator-backed adapters when available.
    - The DB schema tracks path, mtime, size, original and thumbnail dimensions, and PNG-encoded bytes; `get`/`set`/`upsert_meta` helpers provide safe read/write semantics.
    - On Windows, the DB file is marked hidden where possible (operator-backed initialization ensures cross-process safety).

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


# Development policies
- **Pre-release project:** This project is in a pre-release state and prior to first public distribution; we do **not** maintain backward compatibility guarantees. Refactors that improve code quality and reduce maintenance burden may remove compatibility shims when appropriate.
- **Fail fast, avoid excessive try/except (default rule):** For new and modified code, do not blanket logic with broad `try/except` blocks or generic `except Exception` / `contextlib.suppress(Exception)` usage. Prefer targeted exception handling and allow errors to surface so they can be immediately noticed and debugged; catch only expected exceptions and provide informative logs. When you believe broad exception handling is required, treat that as an exception to this rule and follow the fallback policy below.
- **Fallbacks & exception use policy (narrow, documented exceptions):** Only introduce fallbacks (e.g., window-level input fallbacks or secondary handlers) or broad `try/except` / `contextlib.suppress(Exception)` clauses when there is a documented, unavoidable reason (platform/IME quirks, cross-process safety, or unrecoverable external failures), and preferably at well-defined boundaries (e.g., process boundaries, top-level UI event loops, or startup/shutdown glue such as `main.py`). Existing broad handlers and `contextlib.suppress(Exception)` usages in legacy code (including `main.py`) are grandfathered but should not be expanded without review; when touching those areas, prefer tightening the handled exception types. In all cases where a fallback or broad handler is used, document the rationale inline in code, add a short QA note or test that exercises the fallback path, and include a plan (or ticket) to remove or narrow the fallback once the root cause is understood or fixed.
- **Normalize paths using `path_utils.py`:** When working with filesystem paths, always use the utilities in `image_viewer.path_utils` (e.g., `abs_path`, `abs_dir`, `db_key`, `abs_path_str`) to normalize and canonicalize paths across the codebase.

# AGENTS — Operations SOP (Automation & Resume Rules)

Purpose
- Short, practical operating procedures for agents: how to pick tasks, implement work, run checks, and report results.

Single source of truth (SoT)
- TASKS.md: multi-step plans and in-progress tracking (authoritative task plans)
- SESSIONS.md: short, dated session logs (records of completed work)

Quick start
1. Open TASKS.md and SESSIONS.md. Pick a High Priority task if none provided.
2. Single-prompt task: implement, run checks, and add a SESSIONS.md entry.
3. Multi-step task: add a TASKS.md plan before starting and update it as you progress.

Session checklist
- Read TASKS.md (High Priority section) and recent SESSIONS.md entries for context.
- Confirm environment/dependencies in pyproject.toml.

Work rules (must follow)
- Always run checks before reporting completion:
  - uv run python -m ruff check . --fix
  - uv run python -m pyright
  - uv run python -m pytest (recommended)
- Fail fast / avoid excessive try/except: Do not blanket-catch Exception. Prefer targeted exception handling and let unexpected errors surface quickly so they can be diagnosed and fixed; catch only expected exceptions and provide informative logs.
- Record the results of checks in SESSIONS.md.
- Only one task should be in_progress at a time.
- Do not commit or push changes unless the user explicitly asks. When asked to commit, follow the commit checklist:
  - Review git status/diff/log and stage only relevant files
  - Draft a concise English commit message focused on the "why"
  - If pre-commit hooks modify files, include/amend those changes in the commit

Reporting & completion
1. Run checks and tests.
2. Update TASKS.md (mark completed if used).
3. Add a SESSIONS.md entry (minimal template below).
4. Notify the user with a short summary and next steps.

SIMPLE SESSIONS.md TEMPLATE

```
## YYYY-MM-DD

### Short title
**Files:** path/to/file.py
**What:** One-line description
**Checks:** Ruff: pass; Pyright: pass; Tests: N passed
```

When to ask the user
- If scope, acceptance criteria, design decisions, or permissions (commit/PR) are unclear.

Final note
- Keep entries concise and actionable so another agent can resume work quickly. Use `uv run python -m ...` for commands.


