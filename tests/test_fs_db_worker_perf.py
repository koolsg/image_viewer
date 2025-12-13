import sqlite3
import time
from pathlib import Path

from image_viewer.image_engine.fs_db_worker import FSDBLoadWorker
from image_viewer.image_engine.db_operator import DbOperator


def _create_db_for_many(db_path: Path, paths):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS thumbnails (path TEXT PRIMARY KEY, thumbnail BLOB, width INTEGER, height INTEGER, mtime INTEGER, size INTEGER, thumb_width INTEGER NOT NULL DEFAULT 0, thumb_height INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL DEFAULT 0)"
    )
    stmt = "INSERT OR REPLACE INTO thumbnails (path, thumbnail, width, height, mtime, size, thumb_width, thumb_height, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    rows = [(p, None, 200, 100, 0, 1, 128, 128, 0.0) for p in paths]
    conn.executemany(stmt, rows)
    conn.commit()
    conn.close()


def _make_paths(tmp_path: Path, n: int):
    arr = []
    for i in range(n):
        p = tmp_path / f"img_{i:04d}.jpg"
        p.write_bytes(b"x")
        arr.append(p.as_posix())
    return arr


def test_fs_db_worker_perf_direct_vs_operator(tmp_path: Path):
    # Create 1000 files
    n = 1000
    paths = _make_paths(tmp_path, n)
    db_path = tmp_path / "thumbs.db"
    _create_db_for_many(db_path, paths)

    # Direct reads
    worker = FSDBLoadWorker(folder_path=str(tmp_path), db_path=str(db_path), chunk_size=800)
    t0 = time.time()
    worker.run()
    direct_elapsed = time.time() - t0

    # Operator reads
    operator = DbOperator(db_path)
    worker2 = FSDBLoadWorker(folder_path=str(tmp_path), db_path=str(db_path), chunk_size=800, db_operator=operator, use_operator_for_reads=True)
    t1 = time.time()
    worker2.run()
    op_elapsed = time.time() - t1

    # Print timings for human inspection when running locally
    print(f"direct_elapsed={direct_elapsed:.3f}s operator_elapsed={op_elapsed:.3f}s")

    # Basic sanity: both should complete
    assert direct_elapsed > 0
    assert op_elapsed > 0
