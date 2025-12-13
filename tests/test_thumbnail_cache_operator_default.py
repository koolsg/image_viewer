from pathlib import Path
from image_viewer.image_engine.thumbnail_cache import ThumbnailCache


def test_thumbnail_cache_operator_default(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache = ThumbnailCache(cache_dir, db_name="thumbs.db")
    # Operator should be created by default and direct connection should be closed
    assert getattr(cache, "_db_operator", None) is not None
    assert getattr(cache, "_conn", None) is None
    cache.close()
