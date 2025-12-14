"""DB-related modules for the image engine.

This package centralizes DB operators, adapters, migrations and related
helpers used by the engine. Modules are re-exported from top-level
`image_viewer.image_engine` for backward compatibility via small wrappers.
"""

from .db_operator import DbOperator
from .migrations import apply_migrations, get_latest_version
from .thumbdb_bytes_adapter import ThumbDBBytesAdapter
from .thumbdb_core import ThumbDB, ThumbDBOperatorAdapter

__all__ = [
    "DbOperator",
    "ThumbDB",
    "ThumbDBBytesAdapter",
    "ThumbDBOperatorAdapter",
    # UI-level ThumbnailCache lives under image_viewer.image_engine.thumbnail_cache
    "apply_migrations",
    "get_latest_version",
]
