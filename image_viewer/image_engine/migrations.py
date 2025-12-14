"""Compatibility shim re-exporting migrations implementation from
`image_viewer.image_engine.db.migrations`."""

from image_viewer.image_engine.db.migrations import apply_migrations, get_latest_version

__all__ = ["apply_migrations", "get_latest_version"]
