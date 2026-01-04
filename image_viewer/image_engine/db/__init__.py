"""DB-related modules for the image engine.

This package centralizes the thumbnail DB operator and adapter.
Legacy/compatibility layers were intentionally removed.
"""

from .db_operator import DbOperator
from .thumbdb_bytes_adapter import ThumbDBBytesAdapter

__all__ = [
    "DbOperator",
    "ThumbDBBytesAdapter",
]
