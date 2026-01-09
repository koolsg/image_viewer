# Font packaging for distribution 📦

**Summary**
- This document explains why the repo contains third-party fonts (DejaVu), what to check before packaging, and concrete steps to bundle fonts correctly into a packaged executable (PyInstaller example included). It also lists files to inspect and a testing checklist. ✅

---

## Why bundle fonts?
- Qt may not find system fonts in CI, containers, or minimal user systems → results in `QFontDatabase` warnings, layout shifts, or test flakiness.
- Bundling ensures consistent rendering (metrics, bold/italic variants, monospace) across platforms and during tests.

---

## Files to look at in this repo 🔎
- Fonts & license
  - `third_party/fonts/` — bundled TTFs (DejaVu .ttf files) and `DEJAVU_LICENSE.txt`
- Scripts
  - `scripts/install_dejavu_fonts.py` — downloads/extracts DejaVu TTF files into `third_party/fonts`
  - `scripts/run_tests_offscreen.py` — sets `QT_QPA_FONTDIR` to a repo fonts folder for tests
- UI font references (where fonts are used)
  - QML: `image_viewer/qml/App.qml`, `image_viewer/qml/ViewerPage.qml`, `image_viewer/qml/ConvertWebPDialog.qml`, etc. (look for `font.family`, `font.pixelSize`, `font.bold`)
  - Python: `image_viewer/styles.py` (app default `QFont("Segoe UI")` and qss `font-family`), `image_viewer/trim/ui_trim.py` (uses `QFont` directly)

---

## What to include in the package (recommended minimum)
- Include only the fonts you actually need. Heuristics:
  - Include any font family explicitly referenced (`QFont("Consolas")`, `font.family` in QML, `font-family` in styles).
  - Provide a default sans + monospace pair for CI and non-Windows systems: **DejaVuSans.ttf** and **DejaVuSansMono.ttf**.
  - If the UI uses bold/italic variants, include the corresponding TTFs (e.g., `DejaVuSans-Bold.ttf`).
  - Include the font license file(s) alongside the binaries (`DEJAVU_LICENSE.txt`).

Suggested minimal bundle from this repo:
- `third_party/fonts/DejaVuSans.ttf`
- `third_party/fonts/DejaVuSansMono.ttf`
- `third_party/fonts/DejaVuSans-Bold.ttf` (if bold is used)
- `third_party/fonts/DEJAVU_LICENSE.txt`

If you need Korean/GSI coverage for non-Windows, pick an appropriate Noto/Nanum font and verify its license before bundling.

---

## Packaging steps (PyInstaller example) 🔧
1. Add font files and license to package data
   - Example CLI:
     pyinstaller --add-data "third_party/fonts/DejaVuSans.ttf;fonts" \
                 --add-data "third_party/fonts/DejaVuSansMono.ttf;fonts" \
                 --add-data "third_party/fonts/DEJAVU_LICENSE.txt;fonts" \
                 your_app.spec
2. At app startup, register fonts or set font dir
   - Option A: Register with QFontDatabase (recommended for deterministic control):
     ```python
     import os, sys
     from PySide6.QtGui import QFontDatabase

     def register_bundled_fonts():
         base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))  # PyInstaller support
         fonts_dir = os.path.join(base, "fonts")
         for fname in ("DejaVuSans.ttf", "DejaVuSansMono.ttf"):
             path = os.path.join(fonts_dir, fname)
             if os.path.exists(path):
                 QFontDatabase.addApplicationFont(path)
     ```
   - Option B: Set `QT_QPA_FONTDIR` before QApplication is created:
     ```python
     import os, sys
     base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
     os.environ["QT_QPA_FONTDIR"] = os.path.join(base, "fonts")
     ```
3. Include license files in the distributable and display a link in About / Credits if appropriate.

---

## Testing checklist ✅
- Build the package for each target platform (Windows, Linux, macOS) and run it on a clean VM/image.
- Verify there are **no** `QFontDatabase` warnings in console logs.
- Check UI typography: font family, bold/italic availability, monospace sections (e.g., console views), and layout/line breaks.
- Confirm that `DEJAVU_LICENSE.txt` (or other font license) is present in the packaged output.
- CI: Modify/extend `scripts/run_tests_offscreen.py` to set `QT_QPA_FONTDIR` to the packaged fonts location and run headless tests against the packaged binary if feasible.

---

## License considerations ⚖️
- Always include the font license text and any attribution required by the font's license.
- DejaVu fonts have permissive terms (see `DEJAVU_LICENSE.txt`) but verify if you later bundle other fonts (e.g., Noto, Nanum) as their licenses may differ.

---

## Platform notes
- Windows: `Segoe UI` is typically available → no need to bundle unless deterministic behavior is required.
- Linux: minimal distros often lack good fallback fonts → bundling is useful.
- macOS: ship fonts only if cross-platform deterministic rendering is required; test metrics carefully.

---

## How to pick fonts to include (quick recipe)
1. Search the repo for explicit font references:
   - `grep -R "font.family\|QFont(\"\)|font-family"`
2. List the TTFs in `third_party/fonts/` and map families → TTF filenames.
3. Choose the minimal set (regular + monospace + bold/italic if used).

---

## Example: add to PyInstaller spec (snippet)
- In `.spec` add `datas=[('third_party/fonts/DejaVuSans.ttf','fonts'), ('third_party/fonts/DejaVuSansMono.ttf','fonts'), ('third_party/fonts/DEJAVU_LICENSE.txt','fonts')]`.

---

## Notes & follow-ups
- If you want, I can generate a small helper (`dev-tools/package_fonts.py`) to pick fonts referenced in code and emit an include-list for packagers. Would you like that?

---

**Created for reference when preparing final distribution builds.**
