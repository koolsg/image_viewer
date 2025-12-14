# Agent User Guide (Human Operator Checklist)

This document is a checklist for humans working with the `image_viewer` project together with an agent (CLI). It explains what the human must do before and after agent work so that logs, control files, and the application stay in a consistent state.

## What the Human Must Always Do

- Project and scope
  - Confirm the current task and scope before asking the agent to change code.
  - Distinguish clearly between mandatory tasks (must finish) and optional tasks (nice to have).

- Run and verify
  - Be able to run: `uv sync && uv run python image_viewer/main.py`.
  - Prepare a sample folder of images (mixed sizes and formats) to manually test navigation, zoom, and trim features.

- Logging (when needed)
  - Enable detailed logs when investigating bugs:
    - PowerShell: `$env:IMAGE_VIEWER_LOG_LEVEL='debug'`
    - Optionally: `$env:IMAGE_VIEWER_LOG_CATS='main,loader,decoder'`
  - Reset or close the console if log output becomes too noisy.

- Control files
  - Treat `CONTROL_PANEL.md`, `SESSIONS.md`, and `control.yaml` as the project's operational truth:
    - `CONTROL_PANEL.md`: human-readable dashboard (status, TODO, decisions).
    - `SESSIONS.md`: chronological session log (latest section at the top).
    - `control.yaml`: machine-readable state; single source of truth (SoT).


## Operational Flow (Recommended)

1. Before starting a new session
   - Open `control.yaml` and check `next_actions` (priority: `must` items).
   - Skim the latest sections of `CONTROL_PANEL.md` and `SESSIONS.md` to understand recent changes and decisions.
   - Decide what you want the agent to do (e.g., "optimize thumbnail cache", "fix fullscreen bug") and phrase it clearly.
2. While the agent is working
   - Let the agent update code and documentation files.
   - Avoid editing the same files in parallel to prevent conflicts.
   - If the agent changes behavior (navigation, trim, loader, etc.), plan to do a short manual test run afterward.

3. After the agent finishes
   - Run: `uv run python -m compileall image_viewer` (or an equivalent syntax check) if needed.
   - Exercise key flows:
     - Open folder, browse images, zoom in/out, toggle fullscreen.
     - Switch View/Explorer modes (if implemented) and ensure no crashes.
   - Make sure `CONTROL_PANEL.md` and `SESSIONS.md` reflect what was actually done.
   - Commit to Git only after both code and control files are in sync.


## Environment and Configuration

- Run command
  - Primary: `uv sync && uv run python image_viewer/main.py`
  - Alternative (plain Python, if required): create a venv, install dependencies from `pyproject.toml` or `requirements.txt`, then run `python image_viewer/main.py`.

- Logging environment variables (PowerShell examples)
  - `setx IMAGE_VIEWER_LOG_LEVEL debug`
  - `setx IMAGE_VIEWER_LOG_CATS main,loader`
  - After setting, open a new PowerShell session before running the app.

- `.env` configuration for Windows (libvips)
  - Example:
    ```text
    LIBVIPS_BIN=C:\tools\libvips-8.14\bin
    ```
  - Ensure this matches the actual location of the libvips binaries used by `pyvips`.


## Responsibilities Split (Human vs Agent)

- Agent (CLI)
  - Perform code edits, refactors, and documentation updates.
  - Keep `CONTROL_PANEL.md` and `SESSIONS.md` in sync with `control.yaml`.
  - Record technical decisions, risks, and file/line pointers.

- Human operator
  - Decide priorities (which tasks to run, in which order).
  - Run the application, visually verify behavior, and judge UX quality.
  - Manage Git branches, commits, and pull requests.
  - Ensure that deployment or packaging steps (if any) are valid.


## Quick Reference

- Run app (uv): `uv sync && uv run python image_viewer/main.py`
- Enable debug logs (current session):
  ```pwsh
  $env:IMAGE_VIEWER_LOG_LEVEL = 'debug'
  $env:IMAGE_VIEWER_LOG_CATS = 'main,loader'
  uv run python image_viewer/main.py
  ```
- Key control files:
  - `control.yaml` — machine-readable state, next actions, decisions.
  - `CONTROL_PANEL.md` — human-readable dashboard.
  - `SESSIONS.md` — chronological session log (latest at top).
