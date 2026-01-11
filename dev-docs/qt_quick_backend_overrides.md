# Qt Quick backend overrides

This project supports two optional environment variables to help debug or work around Qt Quick rendering issues (useful on Windows with problematic GPU drivers).

- `IMAGE_VIEWER_QSG_RHI_BACKEND`
  - When set, `main.py` sets `QSG_RHI_BACKEND` to this value before Qt starts.
  - Example values: `opengl`, `vulkan` (platform-dependent).
  - Example usage: `IMAGE_VIEWER_QSG_RHI_BACKEND=opengl uv run python -m image_viewer`

- `IMAGE_VIEWER_QT_QUICK_BACKEND`
  - When set, `main.py` sets `QT_QUICK_BACKEND` to this value before Qt starts (e.g. `software`).
  - Example usage: `IMAGE_VIEWER_QT_QUICK_BACKEND=software uv run python -m image_viewer`

Notes
- These variables are optional and do nothing if not set; they are applied early in `main.run()` before `QApplication` is created.
- When an override is applied, `main.py` logs a debug message such as:
  `Applied Qt backend override: IMAGE_VIEWER_QSG_RHI_BACKEND -> QSG_RHI_BACKEND=opengl`
  so enable debug logging to see that message (e.g. `--log-level debug`).
- Use these only when troubleshooting rendering or input artifacts; prefer leaving defaults in normal operation.
