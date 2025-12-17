from pathlib import Path
import sys
import os
import types

# Ensure package import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Create lightweight fakes for PySide6 imports used by the module so tests can run without Qt
import types
sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
sys.modules.setdefault("PySide6.QtCore", types.SimpleNamespace(QBuffer=object, QIODevice=object, Qt=object))
sys.modules.setdefault("PySide6.QtGui", types.SimpleNamespace(QPixmap=object))

from image_viewer.image_engine.db import thumbdb_bytes_adapter as tba


def test_init_thumbnail_cache_calls_hidden(tmp_path: Path, monkeypatch):
    called = {"ok": False, "path": None}

    def _fake_set_hidden(path):
        called["ok"] = True
        called["path"] = path

    # The immediate setter should be invoked inside the DB operator task
    monkeypatch.setattr(tba, "_set_hidden_attribute_immediate", _fake_set_hidden)

    cache_dir = tmp_path / "cache"
    db_path = cache_dir / "SwiftView_thumbs.db"
    adapter = tba.ThumbDBBytesAdapter(db_path)

    assert adapter is not None
    assert called["ok"] is True
    assert called["path"] == db_path
