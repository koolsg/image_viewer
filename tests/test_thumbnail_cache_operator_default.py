from pathlib import Path
from image_viewer.image_engine.db.thumbnail_db import ThumbDBBytesAdapter


def test_thumbnail_cache_operator_default(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache = ThumbDBBytesAdapter(cache_dir / "thumbs.db")
    # Operator should be created by default
    assert getattr(cache, "_operator", None) is not None
    cache.close()
