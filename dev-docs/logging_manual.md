# Logging Manual (image_viewer)

Purpose
- Enable logging easily with options when running main.py, and output only the required categories.
- All logs are output to standard error (stderr).

Basic Usage (Windows PowerShell)
- All debug logs
  - `uv run .\image_viewer\main.py --log-level debug`

- Specific categories only (comma-separated)
  - `uv run .\image_viewer\main.py --log-level debug --log-cats main,loader`

Options
- `--log-level <level>`
  - Supported: `debug`, `info`, `warning`, `error`, `critical`
  - Example: `--log-level debug`

- `--log-cats <cats>`
  - Comma-separated list. Combine category names below.
  - Supported categories (main):
    - `main`, `loader`, `decoder`, `strategy`, `trim`, `trim_operations`
    - `ui_canvas`, `ui_explorer_grid`, `ui_explorer_tree`, `ui_menus`, `ui_settings`, `ui_trim`
    - `hover_menu`, `webp_converter`, `convert_webp`, `view_mode`, `explorer_mode`
    - `file_operations`, `settings`, `fs_model`, `engine`, `thumbnail_cache`, `status_overlay`
  - Example: `--log-cats main,loader`

Example Scenarios
- Focus only on loader queue/decoding flow
  - `uv run .\image_viewer\main.py --log-level debug --log-cats loader`

- View along with UI events and view updates
  - `uv run .\image_viewer\main.py --log-level debug --log-cats main,ui_canvas`

Output Redirection (Optional)
- Save to file: `uv run .\image_viewer\main.py --log-level debug 2> debug.log`

Also configurable via environment variables
- PowerShell
  - `$env:IMAGE_VIEWER_LOG_LEVEL='debug'`
  - `$env:IMAGE_VIEWER_LOG_CATS='main,loader'`
  - `uv run .\image_viewer\main.py`

Internal Operation
- When main.py starts, it pre-parses `--log-level`, `--log-cats` to reflect in environment variables and removes them from argv so they are not passed to Qt.
- The logger reads `IMAGE_VIEWER_LOG_LEVEL` and `IMAGE_VIEWER_LOG_CATS` to apply level/category filters.

Troubleshooting
- Logs not visible
  - If `--log-level` is `info` or higher, debug messages are not visible. Try `debug`.
  - Check if categories are missing in `--log-cats` (e.g., `main,loader`).
- File saving not working
  - Output to standard error. Use `2>` redirection.
