import sqlite3
from pathlib import Path
from image_viewer.image_engine.fs_db_worker import FSDBLoadWorker
from image_viewer.image_engine.thumbdb_core import ThumbDB


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


def test_fs_db_worker_progress(tmp_path: Path):
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

    worker = FSDBLoadWorker(folder_path=str(tmp_path), db_path=str(db_path), chunk_size=1)
    progresses: list[tuple[int, int]] = []

    worker.progress.connect(lambda p, t: progresses.append((p, t)))
    worker.run()

    # Expect at least an initial and final progress update and final equals total 2
    assert progresses
    assert progresses[-1][0] == progresses[-1][1]
    assert progresses[-1][1] == 2
