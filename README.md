Overview
- Desktop image viewer built with PySide6.
- Multi-process image decoding (pyvips). File I/O is scheduled with a small thread pool.
- Two decoding modes: Thumbnail mode (fast viewing) and Full (original resolution).
- High-quality fit downscale option and a top-left overlay for status (no QStatusBar).

What's Included
- image_viewer/main.py: UI, keyboard/mouse, overlay, fullscreen, cache/prefetch, settings, delete-to-trash flow.
- image_viewer/decoder.py: pyvips-based decoding into RGB NumPy arrays (with optional LIBVIPS on Windows via .env).
- image_viewer/settings.json: User settings cache (written at runtime).
- pyproject.toml, uv.lock: uv project metadata/lock.

Requirements
- Python 3.11+
- PySide6, pyvips[binary], numpy, send2trash
- Windows: if pyvips DLLs are not on PATH, set `LIBVIPS_BIN` in a `.env` next to the app (decoder.py reads it) or install `pyvips[binary]`.

Install (uv)
- Sync env: `uv sync`
- Run app: `uv run python image_viewer/main.py`
- Optional (pip style): `uv pip install -r requirements.txt` (not required if using pyproject + uv.lock)

Run (plain Python)
- Create venv, install deps from pyproject or requirements, then: `python image_viewer/main.py`

Key Features
- Decoding strategies
  - Thumbnail mode (fast viewing): decodes to (near) screen size for speed and lower memory.
  - Full (original): decodes the full source resolution for best quality.
  - Toggle in menu: View → "Thumbnail Mode (fast viewing)" (checked = thumbnail; unchecked = full).
- Overlay status (no status bar)
  - Top-left overlay shows two lines: line 1 = filename; line 2 = (index/total) [mode] resolution and zoom.
  - Text color auto-contrasts with current background color.
- Background color
  - View → Black / White / Other... (custom color picker). Default: Black.
- Fit/Actual modes
  - Fit to window or Actual size (1:1). Press Space to snap to the current global mode.
  - Optional HQ fit downscale for smoother results. This option is disabled automatically while in thumbnail mode.
- Navigation & zoom
  - Left/Right (prev/next), Home/End (first/last), Ctrl+Wheel (zoom).
  - Mouse wheel (no Ctrl): prev/next.
  - Press-zoom: hold left mouse to temporarily zoom by a multiplier (default 2.0) centered on cursor; release to restore.
  - Multiplier prompt: View → "Set Zoom Multiplier..." to set 0.1~10.0.
- Fullscreen
  - Menu bar is hidden in fullscreen; overlay remains.
  - Press F11 to toggle fullscreen; Esc exits fullscreen.
- Explorer toggle
  - Press F5 to switch between Explorer Mode and View Mode.
- Delete to Recycle Bin
  - Press Delete to move current file to Recycle Bin (send2trash). The confirmation dialog defaults focus to "Yes". The viewer switches to another image before deletion to avoid UI stalls.
- Caching & prefetch
  - LRU pixmap cache (20). Decode window maintained around the current image (back 3 / ahead 5). Late results for removed files are dropped.

Settings
- Stored at runtime in `image_viewer/settings.json` (auto-created/updated):
  - `thumbnail_mode` (bool): true = thumbnail mode; false = full decoding.
  - `background_color` (hex #RRGGBB): overlay contrast color auto-selected.
  - `press_zoom_multiplier` (float): default 2.0.
  - `last_parent_dir` (string): last file dialog parent dir.
- The app starts fine with no settings file; missing keys take safe defaults and are written on change.

Notes
- On Windows, to avoid white borders in fullscreen, the app removes QGraphicsView/QMainWindow borders/margins for edge-to-edge rendering.
- Decoder uses pyvips thumbnailing for the thumbnail mode; full decoding requests the original size.

Troubleshooting
- "pyvips not found" or DLL errors on Windows: install `pyvips[binary]` or set `LIBVIPS_BIN` via `.env` adjacent to the app (decoder.py reads it) and restart.
