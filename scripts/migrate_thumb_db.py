#!/usr/bin/env python
"""Migration helper script for thumbnail DB.

Usage: python scripts/migrate_thumb_db.py /path/to/SwiftView_thumbs.db
"""

import sqlite3
import sys
from pathlib import Path

from image_viewer.image_engine.migrations import apply_migrations, get_latest_version

EXIT_USAGE = 2
MIN_ARGS = 2

if __name__ == "__main__":
    if len(sys.argv) < MIN_ARGS:
        print("Usage: migrate_thumb_db.py <db_path>")
        sys.exit(EXIT_USAGE)
    db_path = Path(sys.argv[1])
    if not db_path.exists():
        print("DB file does not exist:", db_path)
        sys.exit(1)
    conn = sqlite3.connect(str(db_path))
    current = conn.execute("PRAGMA user_version").fetchone()
    current = int(current[0]) if current else 0
    print(f"Current user_version: {current}")
    apply_migrations(conn)
    latest = get_latest_version()
    new_ver = conn.execute("PRAGMA user_version").fetchone()
    new_ver = int(new_ver[0]) if new_ver else 0
    print(f"Migrated to user_version: {new_ver} (latest {latest})")
    conn.close()
    sys.exit(0)
