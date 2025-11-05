Image Viewer (PySide6 + pyvips)

Overview
- Desktop image viewer built with PySide6.
- Multi-process image decoding (pyvips). File I/O is scheduled with a small thread pool.
- Two decoding modes: Thumbnail mode (fast viewing) and Full (original resolution).
- High‑quality fit scaling option and left‑top overlay for status (no traditional status bar).

What's Included
- image_viewer/main.py: UI, keyboard/mouse, overlay, fullscreen, cache/prefetch, settings.
- image_viewer/decoder.py: pyvips-based decoding into RGB NumPy arrays (with optional LIBVIPS on Windows).
- image_viewer/settings.json: User settings cache (written at runtime).
- pyproject.toml, uv.lock: uv project metadata/lock.

Requirements
- Python 3.11+
- PySide6, pyvips[binary], numpy
- Windows users: if pyvips DLLs are not on PATH, set LIBVIPS_BIN in a .env next to the app (decoder.py will read it) or install pyvips[binary].

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
  - Toggle in menu: View → “썸네일 모드(fast viewing)”. Checked = thumbnail mode, unchecked = full.
- Overlay status (no status bar)
  - Top‑left overlay shows two lines: line 1 = filename; line 2 = (index/total) [mode] resolution and zoom.
  - Text color auto‑contrasts with current background color.
- Background color
  - View → 배경색 → 검정 / 흰색 / 기타... (custom color picker). Default: black.
- Fit/Actual modes
  - Fit to window or Actual size (1:1). Press Space to snap to the current global mode.
  - Optional HQ fit downscale for smoother results (pyvips‑assisted).
- Navigation & zoom
  - Left/Right (prev/next), Home/End (first/last), Up/Down (zoom in/out), Ctrl+Wheel (zoom).
  - Mouse wheel (no Ctrl): prev/next. XButton1/2: zoom out/in.
  - Press‑zoom: hold left mouse to temporarily zoom by a multiplier (default 2.0) centered on cursor; release to restore.
  - Multiplier: View → “프레스 중 배율...” opens a prompt to set 0.1–10.0.
- Fullscreen
  - Enter/Return toggles fullscreen on/off; Esc exits fullscreen.
  - Menu/status bars are hidden in fullscreen; overlay remains.
- Caching & prefetch
  - LRU pixmap cache (20). Decode window maintained around the current image (back 3 / ahead 5).

Settings
- Stored at runtime in `image_viewer/settings.json` (auto‑created/updated):
  - `thumbnail_mode` (bool): true = thumbnail mode; false = full decoding.
  - `background_color` (hex #RRGGBB): overlay contrast color is auto‑selected.
  - `press_zoom_multiplier` (float): default 2.0.
  - `last_parent_dir` (string): last file dialog parent dir.
- The app starts fine with no settings file; missing keys take safe defaults and are written on change.

Notes
- On Windows, if you see a slim white border in fullscreen, this app removes QGraphicsView/QMainWindow borders/margins to maximize edge‑to‑edge rendering.
- Decoder uses pyvips thumbnailing for the thumbnail mode; full decoding requests the original size.

Troubleshooting
- “pyvips not found” or DLL errors on Windows: install `pyvips[binary]` or set `LIBVIPS_BIN` via `.env` adjacent to the app (decoder.py reads it) and restart.

