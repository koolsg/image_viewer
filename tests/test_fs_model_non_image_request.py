import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from image_viewer.image_engine.engine import ImageEngine
from image_viewer.image_engine.fs_model import ImageFileSystemModel


class FakeLoader:
    def __init__(self):
        self.requests = []

    def request_load(self, path, **kwargs):
        self.requests.append(path)


def test_non_image_file_not_queued():
    app = QApplication.instance() or QApplication([])
    tmp_dir = Path(tempfile.gettempdir()) / "iv_test_fs_model_non_image"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    non_img = tmp_dir / "README.txt"
    non_img.write_text("hello")

    engine = ImageEngine()
    model: ImageFileSystemModel = engine.fs_model
    fake = FakeLoader()
    model.set_loader(fake)
    # ensure model is configured to list files
    model.setFilter(model.filter())
    # request thumbnail for non-image
    model._request_thumbnail(str(non_img))
    assert str(non_img) not in model._thumb_pending
    assert len(fake.requests) == 0
