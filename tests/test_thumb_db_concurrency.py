import sqlite3
import threading
import time
from pathlib import Path

from image_viewer.image_engine.thumb_db import ThumbDB


def _create_test_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS thumbnails (path TEXT PRIMARY KEY, thumbnail BLOB, width INTEGER, height INTEGER, mtime INTEGER, size INTEGER)"
    )
    conn.commit()
    conn.close()


def _writer_thread(db_path: Path, base: str, count: int, barrier: threading.Barrier):
    barrier.wait()
    for i in range(count):
        with ThumbDB(db_path) as db:
            db.upsert_meta(f"{base}-{i}.jpg", int(time.time() * 1000), i, meta={"width": 100, "height": 100, "thumbnail": b"x"})


def _reader_thread(db_path: Path, base: str, count: int, barrier: threading.Barrier, result_list: list):
    barrier.wait()
    for _ in range(count):
        with ThumbDB(db_path) as db:
            rows = db.get_rows_for_paths([f"{base}-{i}.jpg" for i in range(count)])
            result_list.append(len(rows))


def test_thumb_db_concurrent_upsert_and_read(tmp_path: Path):
    db_path = tmp_path / "thumbs.db"
    _create_test_db(db_path)

    writer_count = 4
    writer_loop = 50
    reader_count = 3
    barrier = threading.Barrier(writer_count + reader_count)

    # start writer threads
    writers = [threading.Thread(target=_writer_thread, args=(db_path, f"w{n}", writer_loop, barrier)) for n in range(writer_count)]
    readers_results: list = []
    readers = [threading.Thread(target=_reader_thread, args=(db_path, f"w0", writer_loop, barrier, readers_results)) for _ in range(reader_count)]

    for t in writers + readers:
        t.start()
    for t in writers + readers:
        t.join()

    # After concurrent writes, verify there are writer_count * writer_loop rows
    with ThumbDB(db_path) as db:
        rows = db.get_rows_for_paths([f"w{i}-{j}.jpg" for i in range(writer_count) for j in range(writer_loop)])
        assert len(rows) == writer_count * writer_loop

