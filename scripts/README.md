# scripts/

Purpose
- Small, repeatable CLI utilities and developer-facing scripts intended to be run directly (locally or in CI).
- Examples: test helpers, small setup tasks, environment bootstrapping (e.g., `install_dejavu_fonts.py`, `run_tests_offscreen.py`).

Guidelines
- Keep scripts small and focused. Prefer idempotent behavior so CI can run them safely.
- Provide usage/help (argparse or PowerShell param block) and a short top-of-file comment explaining purpose and whether it should be promoted to `tools/` or `tests/` later.
- Prefer `if __name__ == "__main__"` entrypoints for Python scripts; add a shebang (`#!/usr/bin/env python3`) if the script is intended to be executable on Unix.
- Avoid heavy third-party dependencies unless necessary; document any required extras in a comment or dev-doc.

Running
- Python scripts: `python scripts/<script>.py` or `uv run python scripts/<script>.py` (when using uv-managed env).
- PowerShell scripts: `pwsh scripts/<script>.ps1` (scripts intended for PowerShell should explicitly document supported shells).

Packaging & CI
- If a script downloads or bundles third-party data (fonts, binaries), include license text and make downloads idempotent (no system-wide installs without explicit user consent).
- Scripts used by CI (build/test) should exit non-zero on failures and be documented in CI configs or dev-docs.

When to move
- If a script becomes a stable developer tool used by the team, consider promoting it to `dev-tools/` or keep in `scripts/` with maintained docs.
- If it becomes an automated test, convert to pytest and move to `tests/`.

Maintenance
- Add a single-line header comment describing purpose and expected runtimes.
- Ensure scripts pass lints where applicable and include small usage examples.

If you'd like, I can also scan `scripts/` for scripts missing headers or usage help and add short top-of-file comments for consistency.