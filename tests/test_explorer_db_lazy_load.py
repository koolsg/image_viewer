from PySide6.QtWidgets import QApplication

from image_viewer.image_engine.explorer_model import ExplorerTableModel, ExplorerEntry
from image_viewer.path_utils import db_key
from pathlib import Path
from PySide6.QtCore import Qt


def test_do_not_request_thumbnail_if_meta_present(qtbot):
    app = QApplication.instance() or QApplication([])
    class DummyEngine:
        pass

    engine = DummyEngine()
    engine.requested = False
    def request_thumbnail(p):
        engine.requested = True
    engine.request_thumbnail = request_thumbnail

    # Pretend DB meta exists for this path
    path = str(Path("/tmp/test.jpg"))
    key = db_key(path)
    engine._meta_cache = {key: (None, None, 123, 456)}

    model = ExplorerTableModel(engine)

    entry = ExplorerEntry(path=path, name="test.jpg", suffix="jpg", size=123, mtime_ms=456, is_image=True)
    model._entries = [entry]
    model._row_for_key[key] = 0

    idx = model.index(0, model.COL_NAME)
    # DecorationRole should not trigger request_thumbnail when meta exists
    _ = model.data(idx, Qt.ItemDataRole.DecorationRole)
    assert engine.requested is False
