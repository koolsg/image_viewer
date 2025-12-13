from pathlib import Path
import pytest

from image_viewer.image_engine.db.thumbnail_db import ThumbDBBytesAdapter
from image_viewer.image_engine import db_operator as dbop


def test_thumbnail_cache_fails_when_db_operator_init_raises(tmp_path: Path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Monkeypatch DbOperator.__init__ to raise to simulate failure
    def _fail_init(self, db_path, busy_timeout_ms=5000):
        raise RuntimeError("simulated operator failure")

    monkeypatch.setattr(dbop.DbOperator, "__init__", _fail_init, raising=True)

    with pytest.raises(RuntimeError) as exc:
        ThumbDBBytesAdapter(cache_dir / "thumbs.db")

    assert "ThumbnailCache requires a DbOperator" in str(exc.value) or "simulated operator failure" in str(exc.value)
