#!/usr/bin/env python3
"""Watch source files and run checks automatically on changes.

This script watches the `image_viewer` package and runs `python scripts/run_checks.py --no-tests`
on file change events. It's meant for developer convenience (runs lighter checks by default).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from time import sleep

try:
    from watchfiles import watch
except Exception:
    print("watchfiles not installed. Please install via `pip install watchfiles`.")
    raise


def run_check() -> int:
    cmd = [sys.executable, str(Path(__file__).parent / "run_checks.py"), "--no-tests"]
    print("Running checks:", " ".join(cmd))
    return subprocess.run(cmd, check=False).returncode


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    src = project_root / "image_viewer"
    print("Watching:", src)
    rc = 0
    for _changes in watch(src, stop_event=None):
        # Debounce: brief sleep to group related changes
        sleep(0.1)
        print("Detected changes, running checks")
        rc = run_check()
        print("Checks complete, rc=", rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
