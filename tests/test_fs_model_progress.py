import sqlite3
from pathlib import Path
import contextlib

from image_viewer.image_engine.fs_db_worker import FSDBLoadWorker
from image_viewer.image_engine.fs_model import ImageFileSystemModel


def _create_db_with_thumb(db_path: Path, path: str, mtime: int, size: int):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS thumbnails (path TEXT PRIMARY KEY, thumbnail BLOB, width INTEGER, height INTEGER, mtime INTEGER, size INTEGER, thumb_width INTEGER NOT NULL DEFAULT 0, thumb_height INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL DEFAULT 0)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO thumbnails (path, thumbnail, width, height, mtime, size, thumb_width, thumb_height, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (path, b"blob", 200, 100, mtime, size, 128, 128, 0.0),
    )
    conn.commit()
    conn.close()


def test_fs_model_progress_forwarding(tmp_path: Path):
    # prepare files
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    a.write_bytes(b"aa")
    b.write_bytes(b"bb")

    # create DB and insert a thumb for a.jpg
    db_path = tmp_path / "thumbs.db"
    st = a.stat()
    mtime = int(st.st_mtime_ns) // 1_000_000
    size = st.st_size
    _create_db_with_thumb(db_path, str(a.as_posix()), mtime, size)

    model = ImageFileSystemModel()
    model.setRootPath(str(tmp_path))

    # Create a worker directly (not via model) and connect to model._on_thumb_db_progress
    worker = FSDBLoadWorker(folder_path=str(tmp_path), db_path=str(db_path), chunk_size=1)

    progresses = []
    worker_progresses = []
    # Connect to the model's progress signal and to the worker's progress
    model.progress.connect(lambda p, t: progresses.append((p, t)))
    with contextlib.suppress(Exception):
        worker.progress.connect(lambda p, t: worker_progresses.append((p, t)))
        worker.progress.connect(model._on_thumb_db_progress)

    # Run the worker synchronously in the test thread to exercise forwarding
    worker.run()

    # Worker should emit progress; model should forward it
    assert worker_progresses
    assert worker_progresses[-1][1] == 2
    assert progresses
    assert progresses[-1][1] == 2
