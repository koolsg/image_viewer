from pathlib import Path
from PySide6.QtWidgets import QApplication
from image_viewer.image_engine.fs_model import ImageFileSystemModel
from image_viewer.image_engine.thumbnail_cache import ThumbnailCache


def test_fs_model_passes_operator_to_worker(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    # Setup folder and DB
    a = tmp_path / "a.jpg"
    a.write_bytes(b"aa")
    model = ImageFileSystemModel()
    model.setRootPath(str(tmp_path))

    # Ensure cache exists and has operator by instantiating it
    model._ensure_db_cache(str(a))
    assert model._db_cache is not None

    # Enable operator read strategy and start loader
    model.set_db_read_strategy(True)
    model.batch_load_thumbnails()

    # Worker should have been created and configured to use operator
    worker = model._thumb_db_worker
    assert worker is not None
    assert getattr(worker, "_use_operator_for_reads", False) is True
    assert getattr(worker, "_db_operator", None) is not None

    # Cleanup: stop the background loader
    try:
        model._stop_thumb_db_loader()
    except Exception:
        pass
