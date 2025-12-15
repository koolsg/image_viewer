"""Path normalization utilities.

This module centralizes the project's path normalization rules:

- Use absolute paths when interacting with the filesystem/UI.
- Use a stable, normalized key for DB storage (forward slashes + drive letter
  normalization on Windows).

Keep this module free of Qt dependencies.
"""

from __future__ import annotations

from pathlib import Path

_DRIVE_PREFIX_LEN = 2


def _normalize_drive_letter(path_str: str) -> str:
    # Normalize drive letter casing on Windows ("c:\\" -> "C:\\").
    if len(path_str) >= _DRIVE_PREFIX_LEN and path_str[1] == ":":
        return path_str[0].upper() + path_str[1:]
    return path_str


def abs_path(path: str | Path) -> Path:
    """Return an absolute path without requiring that it exists."""
    p = Path(path).expanduser()
    try:
        # strict=False avoids exceptions for non-existent paths.
        return p.resolve(strict=False)
    except Exception:
        return p.absolute()


def abs_path_str(path: str | Path) -> str:
    """Absolute, OS-native path string (Windows uses backslashes)."""
    return _normalize_drive_letter(str(abs_path(path)))


def abs_dir(path: str | Path) -> Path:
    """Absolute directory path.

    If the path exists and is not a directory, returns its parent.
    """
    p = abs_path(path)
    try:
        if p.exists() and not p.is_dir():
            return p.parent
    except Exception:
        # If filesystem checks fail, keep the absolute path.
        pass
    return p


def abs_dir_str(path: str | Path) -> str:
    return _normalize_drive_letter(str(abs_dir(path)))


def db_key(path: str | Path) -> str:
    """Stable DB key for a filesystem path."""
    return _normalize_drive_letter(abs_path_str(path)).replace("\\", "/")
