"""Compatibility shim re-exporting implementation from image_engine.db package.

This module keeps old imports working while the real implementation lives under
`image_viewer.image_engine.db`.
"""

from image_viewer.image_engine.db.db_operator import DbOperator

__all__ = ["DbOperator"]
