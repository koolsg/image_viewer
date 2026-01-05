#!/usr/bin/env python3
"""Download and extract DejaVu TTF fonts into third_party/fonts.

This script is idempotent and safe to run in CI or locally. It only downloads
and extracts the TTF files and does not install fonts system-wide.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEST = REPO_ROOT / "third_party" / "fonts"
CANDIDATE_URLS = [
    # Try the latest download redirect first
    "https://github.com/dejavu-fonts/dejavu-fonts/releases/latest/download/dejavu-fonts-ttf-2.37.zip",
    # Known versioned asset (may change over time)
    "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version-2.37/dejavu-fonts-ttf-2.37.zip",
    # Alternate common naming
    "https://github.com/dejavu-fonts/dejavu-fonts/releases/latest/download/dejavu-fonts-ttf.zip",
    "https://github.com/dejavu-fonts/dejavu-fonts/archive/refs/heads/master.zip",
]


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    # Quick check: if at least one .ttf exists, assume done
    existing = list(DEST.glob("**/*.ttf"))
    if existing:
        print("Fonts already present in:", DEST)
        return 0

    print("Downloading DejaVu fonts...")
    with tempfile.TemporaryDirectory() as td:
        zip_path = Path(td) / "dejavu.zip"
        last_err = None
        for url in CANDIDATE_URLS:
            try:
                print("Trying:", url)
                urllib.request.urlretrieve(url, zip_path)
                last_err = None
                break
            except Exception as ex:
                print("Download failed for:", url, "->", ex)
                last_err = ex
        if last_err is not None:
            print("Failed to download fonts from candidates:", CANDIDATE_URLS, file=sys.stderr)
            return 1

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                members = [m for m in zf.namelist() if m.lower().endswith(".ttf")]
                if not members:
                    print("No TTF files found in archive", file=sys.stderr)
                    return 2
                for m in members:
                    target = DEST / Path(m).name
                    with zf.open(m) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
            print(f"Extracted {len(members)} fonts to: {DEST}")
        except zipfile.BadZipFile as ex:
            print("Bad zip file:", ex, file=sys.stderr)
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
