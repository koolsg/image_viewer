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

- Optional Qt Quick backend overrides (use only for troubleshooting rendering/input issues on specific platforms):
  - `IMAGE_VIEWER_QSG_RHI_BACKEND` → sets `QSG_RHI_BACKEND` (e.g. `opengl`)
  - `IMAGE_VIEWER_QT_QUICK_BACKEND` → sets `QT_QUICK_BACKEND` (e.g. `software`)
  - Example: `IMAGE_VIEWER_QSG_RHI_BACKEND=opengl uv run python -m image_viewer`
  - These are applied early at startup and are logged at DEBUG level when used. See `dev-docs/qt_quick_backend_overrides.md` for details.

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

- QML linting with `pyside6-qmllint` (recommended when editing QML):
  - Purpose: checks QML syntax, property bindings and common QML-specific issues before running the app or opening a PR.
  - Run it against a single file:
    - `uv run pyside6-qmllint image_viewer/ui/qml/App.qml`
  - Run it against many files (shells differ):
    - POSIX shells with glob support: `uv run pyside6-qmllint "image_viewer/ui/qml/**/*.qml"`
    - Windows PowerShell (explicit recursion): `Get-ChildItem -Recurse -Filter *.qml | ForEach-Object { uv run pyside6-qmllint $_.FullName }`
  - CI guidance: include a step that runs `uv run pyside6-qmllint` for changed QML files or performs a full pass; the tool exits non-zero and prints diagnostics when it finds issues.
  - Note: `pyside6-qmllint` may print nothing on success; if it prints errors, fix them and re-run.

## High-level architecture

**Current architecture (QML-first + strict boundary):**

- UI is implemented in **Qt Quick/QML** (`image_viewer/ui/qml/App.qml`) with `pragma ComponentBehavior: Bound`.
- Python exposes a single backend object, `BackendFacade` (`image_viewer/app/backend.py`), to QML.
- QML issues commands only via `backend.dispatch(cmd, payload)` and binds to state objects under `backend.*`.
- Python emits only structured events back to QML (no direct method calls into QML).

### Entry points and application shell

- `image_viewer/__main__.py`
  - Calls `image_viewer.main.run()`.
- `image_viewer/main.py`
  - Parses CLI logging flags (`--log-level`, `--log-cats`) before Qt reads argv.
  - Sets a non-native Qt Quick Controls style (`Fusion`) so QML `background:`/`contentItem:` customization works.
  - Creates `QApplication`, `SettingsManager`, `ImageEngine`, and `BackendFacade`.
  - Registers QML image providers:
    - `image://engine/<gen>/<path>` for full images (pixmaps served from the engine cache)
    - `image://thumb/<gen>/<key>` for thumbnails (pixmaps decoded from cached PNG bytes)
  - Injects `backend` as a context property *and* sets `root.backend` after loading to satisfy `ComponentBehavior: Bound`.
  - Hooks shutdown (`app.aboutToQuit`) to `engine.shutdown` so worker threads stop cleanly.

### QML ↔ Python boundary (the important contract)

- **Inbound (QML → Python):** `backend.dispatch(cmd: str, payload: QVariant)`
  - `payload` is commonly a JS object; Python must accept it as a Qt variant and coerce to native dict/list as needed.
- **Outbound (Python → QML):**
  - `backend.event({...})` — general UI events/notifications
  - `backend.taskEvent({...})` — long-running task progress/events (e.g. WebP conversion)
- **Bindable state objects (QML reads):**
  - `backend.viewer`, `backend.explorer`, `backend.settings`, `backend.tasks`
  - These are `QObject` property holders under `image_viewer/app/state/`.

Design rule: QML should remain a "dumb view" — it binds to state and sends commands; it does not own file/DB/engine logic.

### Image engine threads and data flow

- `image_viewer/image_engine/engine.py` (`ImageEngine`)
  - Owns two main pipelines:
    1) **Full-image decode (view mode):** a `Loader` does multi-process decode to numpy; a `ConvertWorker` in a QThread converts numpy→`QImage`; UI thread finalizes into `QPixmap` and caches it.
    2) **Explorer scan + thumbnail DB + thumbnail bytes (explorer mode):** an `EngineCore` runs in its own QThread and emits folder snapshots + thumbnail chunks.
  - Emits UI-facing signals used by `BackendFacade` to update QML models/state:
    - `file_list_updated`, `explorer_entries_changed`, `explorer_thumb_rows`, `explorer_thumb_generated`, plus `image_ready`.
  - Caches pixmaps with an LRU policy, so QML can fetch quickly through the `image://engine` provider.

- `image_viewer/image_engine/engine_core.py` (`EngineCore`)
  - Runs in a dedicated thread.
  - Owns timers/watchers/DB interactions needed for folder scanning and thumbnail generation.
  - Must be shut down from its owning thread (engine shutdown coordinates this).

### Explorer UI model (QML)

- `image_viewer/ui/qml_models.py` (`QmlImageGridModel`)
  - QML-facing model for the Explorer grid.
  - Filled by `BackendFacade` using the engine’s explorer snapshot signals.

### File operations and batch tools

- `image_viewer/app/backend.py` dispatch handlers call pure-ish helpers under `image_viewer/ops/file_operations.py` for:
  - delete-to-recycle-bin, rename, copy/cut/paste, reveal in explorer, clipboard integration.
- `image_viewer/ops/webp_converter.py`
  - WebP conversion controller emits progress/log/finished/canceled/error signals.
  - `BackendFacade` translates these into `taskEvent({ name: "webpConvert", ... })` and updates `backend.tasks` state.

### Legacy / non-QML UI modules

This repo still contains widget-based UI/crop utilities (e.g. under `image_viewer/crop/`, and older widget codepaths).
They are not the primary app shell anymore; the QML path is the default entrypoint.

### Logging and utilities

  - `image_viewer/infra/logger.py`
  - Centralized logging setup.
  - `setup_logger` respects environment variables for log level and category filters, ensures a single `StreamHandler` on the base logger, and configures a consistent formatter.
  - `get_logger(name)` returns child loggers (e.g. `image_viewer.main`, `image_viewer.loader`).
  - QML logging: prefer `backend.dispatch("log", { level: "debug", message: "..." })` (see `App.qml`'s `qmlDebugSafe`). Avoid ad-hoc `qmlLogger` context objects unless you need a separate logging bridge.


# Development policies
- **Pre-release project:** This project is in a pre-release state and prior to first public distribution; we do **not** maintain backward compatibility guarantees. Refactors that improve code quality and reduce maintenance burden may remove compatibility shims when appropriate.
- **Fail fast, avoid excessive try/except (default rule):** For new and modified code, do not blanket logic with broad `try/except` blocks or generic `except Exception` / `contextlib.suppress(Exception)` usage. Prefer targeted exception handling and allow errors to surface so they can be immediately noticed and debugged; catch only expected exceptions and provide informative logs. When you believe broad exception handling is required, treat that as an exception to this rule and follow the fallback policy below.
- **Fallbacks & exception use policy (narrow, documented exceptions):** Only introduce fallbacks (e.g., window-level input fallbacks or secondary handlers) or broad `try/except` / `contextlib.suppress(Exception)` clauses when there is a documented, unavoidable reason (platform/IME quirks, cross-process safety, or unrecoverable external failures), and preferably at well-defined boundaries (e.g., process boundaries, top-level UI event loops, or startup/shutdown glue such as `main.py`). Existing broad handlers and `contextlib.suppress(Exception)` usages in legacy code (including `main.py`) are grandfathered but should not be expanded without review; when touching those areas, prefer tightening the handled exception types. In all cases where a fallback or broad handler is used, document the rationale inline in code, add a short QA note or test that exercises the fallback path, and include a plan (or ticket) to remove or narrow the fallback once the root cause is understood or fixed.
- **Normalize paths using `infra.path_utils`:** When working with filesystem paths, always use the utilities in `image_viewer.infra.path_utils` (e.g., `abs_path`, `abs_dir`, `db_key`, `abs_path_str`) to normalize and canonicalize paths across the codebase.

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
- Git policy: **Read-only git queries are allowed** (e.g. `git status`, `git diff`, `git log`). **But any git operation that changes repo state is forbidden unless the user explicitly asks.** This includes (but is not limited to) `git add`, `git commit`, `git restore`, `git checkout/switch`, `git reset`, `git merge/rebase`, `git stash`, `git push`, and editing `.git*` metadata.
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


