# Logging Manual (image_viewer)

Purpose
- Enable logging easily with options when running main.py, and output only the required categories.
- All logs are output to standard error (stderr).

Basic Usage (Windows PowerShell)
- All debug logs
  - `uv run python -m image_viewer --log-level debug`

- Specific categories only (comma-separated)
  - `uv run python -m image_viewer --log-level debug --log-cats main,loader`

Options
- `--log-level <level>`
  - Supported: `debug`, `info`, `warning`, `error`, `critical`
  - Example: `--log-level debug`

- `--log-cats <cats>`
  - Comma-separated list. Combine category names below.
  - Supported categories (main):
    - Core / CLI: `main`, `engine`, `engine_core`, `db_operator`
    - Decoding / IO: `loader`, `decoder`, `convert_webp`, `strategy`
    - Explorer / UI: `ui_canvas`, `ui_explorer_grid`, `ui_explorer_tree`, `explorer_model`, `ui_menus`, `ui_settings`
    - Thumbnail / DB: `fs_db_worker`, `thumb_db`, `thumbnail_db`, `thumbnail_cache`
    - Misc / ops: `trim`, `trim_operations`, `hover_menu`, `webp_converter`, `file_operations`, `settings`, `status_overlay`
  - Thumbnail / DB-focused categories you may find useful:
    - `--log-cats engine_core,fs_db_worker,thumbnail_db,explorer_model`

Example Scenarios (thumbnail debugging)
- Narrow focus to thumbnail pipeline and DB preload:
  - `uv run python -m image_viewer --log-level debug --log-cats engine_core,fs_db_worker,thumbnail_db,explorer_model,ui_explorer_grid`
- Focus only on loader queue/decoding flow
  - `uv run python -m image_viewer --log-level debug --log-cats loader`

- View along with UI events and view updates
  - `uv run python -m image_viewer --log-level debug --log-cats main,ui_canvas`

Output Redirection (Optional)
- Logs are written to standard error (stderr) only by default.
  - A previous iteration wrote a session log file, but the current `image_viewer/logger.py` intentionally avoids creating a session log on disk.
  - If you want a file capture, redirect stderr (or use the VS Code task below).

- You can still redirect stderr if you want an additional capture:
  - Save to file: `uv run python -m image_viewer --log-level debug 2> debug.log`

- PowerShell: show logs in normal console color and save to `debug.log` (recommended on Windows if you want non-red console output):
  - Overwrite (truncate) file and show normal-colored console output:
    - `Remove-Item debug.log -ErrorAction SilentlyContinue; & { uv run python -m image_viewer --log-level debug 2>&1 } | ForEach-Object { Write-Host $_; Add-Content -Path debug.log -Value $_ }`
  - Append to existing file and show normal-colored console output:
    - `& { uv run python -m image_viewer --log-level debug 2>&1 } | ForEach-Object { Write-Host $_; Add-Content -Path debug.log -Value $_ }`
  - Explanation: `2>&1` merges stderr into stdout; `ForEach-Object { Write-Host $_; Add-Content ... }` prints each line to the console using normal colours and writes it to `debug.log`. Using `Remove-Item` is optional — `Out-File -Force` or `Clear-Content` can be used to truncate without deleting.
  - Note: These commands are PowerShell-specific. On Bash/CMD use `2>&1 | tee debug.log` (or `&> debug.log` on Bash) instead.

Also configurable via environment variables
- PowerShell
  - `$env:IMAGE_VIEWER_LOG_LEVEL='debug'`
  - `$env:IMAGE_VIEWER_LOG_CATS='main,loader'`
  - `uv run .\image_viewer\main.py`

Internal Operation
- When main.py starts, it pre-parses `--log-level`, `--log-cats` to reflect in environment variables and removes them from argv so they are not passed to Qt.
- The logger reads `IMAGE_VIEWER_LOG_LEVEL` and `IMAGE_VIEWER_LOG_CATS` to apply level/category filters.

QML → Python logging integration (recommended)
- Use the `Main.qmlDebug(message: string)` QML-callable slot to route QML-originated diagnostics into the Python logging system and also print them to stderr for guaranteed visibility.

  Why this is recommended:
  - `qmlDebug()` is part of the application's `Main(QObject)` backend that is injected into QML as `root.main`.
  - Messages sent via `root.main.qmlDebug("...")` are logged at DEBUG to the project's Python logger and also printed to `stderr` regardless of logger filters, so you get both structured logging and reliably visible early diagnostics.

  Example (QML):

  ```qml
  // inside a QML component where root is the ApplicationWindow
  if (root && root.main) {
      root.main.qmlDebug("[THUMB] DOUBLE-CLICK idx=" + idx)
  }
  ```

  Example (Python): the `qmlDebug` slot is implemented as:

  ```python
  @Slot(str)
  def qmlDebug(self, message: str) -> None:
      _logger.debug("[QML] %s", message)
      print(f"[QML] {message}", file=sys.stderr, flush=True)
  ```

Alternative: expose a `QmlLogger` bridge
- If you prefer separate category methods (`debug/info/warning/error`) callable directly from QML, you can expose a small QObject with `@Slot(str)` methods via the QML context:

  ```python
  qml_logger = QmlLogger()
  qml_engine.rootContext().setContextProperty("qmlLogger", qml_logger)
  ```

  Then in QML:

  ```qml
  qmlLogger.debug("Component=Grid, event=click idx=" + idx)
  ```

  Note: the project currently uses `root.main.qmlDebug()` as the canonical path; prefer it unless you need a separate logger object for structural reasons.

Capturing and filtering QML-originated logs
- Because `qmlDebug()` also prints to stderr, messages are visible even when log-level filters would otherwise hide DEBUG records.
- If you want to funnel QML logs through the same category filtering UI, use `--log-level debug` and `--log-cats main,engine` (or add a dedicated `qml` category in `get_logger` if you want fine-grained control).

Troubleshooting
- Logs not visible
  - If `--log-level` is `info` or higher, debug messages are not visible. Try `debug`.
  - Check if categories are missing in `--log-cats` (e.g., `main,loader`).
- File saving not working
  - Output to standard error. Use `2>` redirection.

Suppress noisy Qt/pybind warnings
- The app suppresses recurring Qt/pybind-derived lines that contain `FIXME qt_isinstance` by default to avoid console spam.
  - This suppression is enabled by default; suppressed lines are appended to `debug.log.filtered` in the current working directory for later inspection.
  - To opt out and see the original lines on stderr, set `IMAGE_VIEWER_FILTER_QT_FIXME=0` (or `false`) before launching the app.
  - The feature is controlled via the `IMAGE_VIEWER_FILTER_QT_FIXME` environment variable (unset = enabled, `0`/`false` = disabled).

VS Code task note
- The workspace task "Run Image Viewer with Debug Logging" truncates `debug.log` at each start and writes logs to `debug.log` using a relative path.
  (In VS Code this is typically the workspace root, but it depends on the task working directory.)
