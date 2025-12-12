#!/usr/bin/env python3
"""Run repository checks: ruff, pyright, and optional tests.

This script allows automated running of linting, typing, and tests.
It exits non-zero when checks fail so CI and local tooling can observe status.
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def run(cmd: list[str]) -> int:
    print("=>", " ".join(cmd))
    res = subprocess.run(cmd, check=False)
    return res.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-tests", action="store_true", help="Skip running pytest")
    args = parser.parse_args()

    # Run ruff with auto-fix
    rc = run([sys.executable, "-m", "ruff", "check", "--fix", "."])
    if rc != 0:
        print("ruff failed")
        return rc

    # Run pyright
    rc = (
        run([sys.executable, "-m", "pyright"]) if sys.platform != "win32" else run(["pyright"])
    )  # pyright may be on PATH
    if rc != 0:
        print("pyright failed")
        return rc

    # Optionally run tests
    if not args.no_tests:
        rc = run([sys.executable, "-m", "pytest", "-q"])
        if rc != 0:
            print("pytest failed")
            return rc

    print("All checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
