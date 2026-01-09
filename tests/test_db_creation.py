from pathlib import Path
import time

from image_viewer.image_engine.engine_core import EngineCore
from image_viewer.image_engine.db.db_operator import DbOperator


def test_db_created_on_open(tmp_path: Path) -> None:
    base = tmp_path / "images"
    base.mkdir()
    img = base / "img1.jpg"
    img.write_text("dummy")

    print("TEST: creating EngineCore")
    core = EngineCore()
    print("TEST: calling open_folder")
    core.open_folder(str(base))

    print("TEST: open_folder returned; waiting up to 5s for DB file")
    db = base / "SwiftView_thumbs.db"
    for _ in range(50):
        if db.exists():
            break
        time.sleep(0.1)

    assert db.exists(), "Thumbnail DB was not created in the folder"

    # Ensure any background DB operator threads are shut down to avoid test leaks
    DbOperator.shutdown_all(wait=True)
