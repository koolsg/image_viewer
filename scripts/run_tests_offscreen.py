#!/usr/bin/env python3
"""Run pytest in Qt offscreen mode with safe defaults.

Usage:
  python scripts/run_tests_offscreen.py [--timeout SECONDS] [--] [pytest args...]

Examples:
  python scripts/run_tests_offscreen.py tests/test_crop_pixmap_update.py::\
      test_set_dialog_pixmap_resets_selection_and_centers
  python scripts/run_tests_offscreen.py -- -k crop -q
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys


def main() -> int:
    p = argparse.ArgumentParser(description="Run pytest with Qt offscreen mode and safe defaults")
    p.add_argument("--timeout", type=int, default=300, help="Maximum seconds to allow the whole pytest run")
    p.add_argument("--verbose", action="store_true", help="Don't use -q (quiet)")
    p.add_argument(
        "pytest_args", nargs=argparse.REMAINDER, help="Additional pytest args (e.g. tests/test_file.py::test_name)"
    )
    args = p.parse_args()

    env = os.environ.copy()
    # Default to offscreen to avoid OS window manager "Not Responding" states in CI and local test runs
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # If the repo includes a fonts directory, set QT_QPA_FONTDIR so Qt can find fonts (avoids QFontDatabase warnings)
    for candidate in ("./third_party/fonts", "./fonts", "./dev-resources/fonts"):
        if os.path.isdir(candidate):
            env.setdefault("QT_QPA_FONTDIR", os.path.abspath(candidate))
            break

    base_cmd = ["uv", "run", "python", "-m", "pytest"]
    flags = []
    if not args.verbose:
        flags += ["-q", "-x", "--maxfail=1"]
    # Default per-test timeout via pytest-timeout plugin; allow override via explicit pytest args
    timeout_flag = [f"--timeout={min(300, args.timeout)}"]
    # Append user args if any (strip leading '--' if argparse kept it)
    user_args = [a for a in args.pytest_args if a != "--"]
    cmd = base_cmd + flags + timeout_flag + user_args

    print("Running:", " ".join(shlex.quote(c) for c in cmd))
    try:
        completed = subprocess.run(cmd, env=env, check=False, timeout=args.timeout)
        return completed.returncode if completed.returncode is not None else 0
    except subprocess.TimeoutExpired:
        print(f"pytest run timed out after {args.timeout} seconds", file=sys.stderr)
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
