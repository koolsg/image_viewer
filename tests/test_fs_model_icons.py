from pathlib import Path
import tempfile
import sys
import time

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QDir
from image_viewer.ui_explorer_grid import _ImageOnlyIconProvider
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

sys.path.insert(0, str(Path(__file__).parent.parent))
from image_viewer.image_engine.engine import ImageEngine


def create_files(tmp_dir: Path):
    tmp_dir.mkdir(parents=True, exist_ok=True)
    # create a non-image file
    (tmp_dir / "README.txt").write_text("hello")
    # create a small PNG
    from PySide6.QtGui import QImage

    img = QImage(64, 64, QImage.Format.Format_RGB32)
    img.fill(0xFF0000)
    img.save(str(tmp_dir / "img.png"), "PNG")
    return [str(tmp_dir / "README.txt"), str(tmp_dir / "img.png")]


def test_fs_model_returns_icons_for_files():
    app = QApplication.instance() or QApplication([])
    tmp_dir = Path(tempfile.gettempdir()) / "iv_test_fs_model_icons"
    create_files(tmp_dir)

    engine = ImageEngine()
    model = engine.fs_model
    model.set_loader(engine.thumb_loader)
    # Ensure we list files and disable extension filtering for the test
    model.setFilter(QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
    model.setNameFilters([])
    model.setNameFilterDisables(True)
    model.setIconProvider(_ImageOnlyIconProvider())
    model.setRootPath(str(tmp_dir))
    root_idx = model.index(str(tmp_dir))
    # Force a batch load to read DB and prefetch
    model.batch_load_thumbnails(root_idx)

    # Wait for the model to populate rows (QFileSystemModel may be asynchronous)
    import time

    timeout = time.time() + 3
    row_count = model.rowCount(root_idx)
    while time.time() < timeout and row_count == 0:
        app.processEvents()
        time.sleep(0.05)
        row_count = model.rowCount(root_idx)

    # Ensure model has rows
    assert row_count >= 2

    for row in range(row_count):
        idx = model.index(row, 0, root_idx)
        val = model.data(idx, Qt.DecorationRole)
        # data may be QIcon or QPixmap; ensure it's QIcon or has pixmap
        assert val is not None
        if isinstance(val, QIcon):
            assert not val.isNull()
        else:
            # May be QPixmap-like; treat as truthy
            assert hasattr(val, "isNull")

    # Cleanup: ensure background threads are stopped
    try:
        model._stop_thumb_db_loader()
    except Exception:
        pass
    try:
        engine.shutdown()
    except Exception:
        pass
