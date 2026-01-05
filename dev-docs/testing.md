Testing guide

Run tests safely (recommended for local development and CI):

- Use the helper script which forces Qt offscreen mode and applies sensible defaults (quiet, fail-fast, per-test timeout):

  python scripts/run_tests_offscreen.py [--timeout SECONDS] [pytest args...]

  Examples:
    python scripts/run_tests_offscreen.py tests/test_crop_pixmap_update.py::\
        test_set_dialog_pixmap_resets_selection_and_centers
    python scripts/run_tests_offscreen.py -- -k crop -q

Notes:
- The script sets `QT_QPA_PLATFORM=offscreen` to avoid OS "Not Responding" UI freezes when tests create windows.
- If your environment logs a `QFontDatabase: Cannot find font directory` warning, either install a system font package (e.g., `fonts-dejavu-core` on Ubuntu) or add a fonts folder to the repo (e.g., `third_party/fonts`). The runner will automatically set `QT_QPA_FONTDIR` to a bunded fonts folder if present.
- A per-test timeout is enforced via the `pytest-timeout` plugin (configured in `pyproject.toml` as `timeout = 60`).
- Use `-x` / `--maxfail=1` for the quickest feedback loop; add `-k <expr>` to run only a subset of tests.
- If you see native crashes (access violations), try isolating with `-k` and file-by-file runs to find the culprit. Native crashes may indicate issues in C extensions or threading (investigation recommended).
