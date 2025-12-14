# ThumbDB Migration Guide

## Overview

This guide explains the thumbnail DB migration behavior and tools used by the Image Viewer.

- Migration framework: `image_viewer/image_engine/migrations.py`
- Utility CLI: `scripts/migrate_thumb_db.py`
- DB wrapper: `image_viewer/image_engine/thumb_db.py` calls migration helpers on connect

## How it works

- On `ThumbDB.connect()`, the code ensures schema columns and runs `apply_migrations(conn)`.
- `migrations.py` contains organized migration steps for each target schema version.
- The current migrations support upgrading legacy (v0) thumbnails DB to v1 with columns:
  - `thumb_width`, `thumb_height`, `created_at`

## CLI Usage

```bash
python scripts/migrate_thumb_db.py /path/to/SwiftView_thumbs.db
```

- The script prints current and new user_version after migration.
- The script requires Python to have packages from `pyproject.toml` (especially `sqlite3` available in stdlib).

## Rollbacks and Downgrades

- A downgrade is only performed by a matching downgrade migration.
- The current migrations include a migration to downgrade from v1 to v0 (recreate table to drop columns).
- Use rollback cautiously; always back up the DB first.

## Tests

- `tests/test_thumb_db_migration.py` validates an upgrade path from a generated v0 DB to v1 and column existence. It helps ensure future regressions are detected by CI.

## Recommendations

- Run `python scripts/migrate_thumb_db.py` during maintenance windows if you expect older DB files.
- Add monitoring for `user_version` drift if running in large fleets to detect un-migrated DB files.

*** End of Guide
