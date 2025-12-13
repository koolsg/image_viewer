import threading
import time
from pathlib import Path

from image_viewer.image_engine.db.thumbdb_bytes_adapter import ThumbDBBytesAdapter
from image_viewer.image_engine.thumbdb_core import ThumbDB


def _setter(cache: ThumbDBBytesAdapter, base: str, count: int, barrier: threading.Barrier):
    barrier.wait()
    for i in range(count):
        try:
            cache.upsert_meta(f"{base}-{i}.jpg", int(time.time() * 1000), i, meta={
                "width": 100,
                "height": 100,
                "thumb_width": 128,
                "thumb_height": 128,
                "created_at": time.time(),
            })
        except Exception:
            pass


def _getter(cache: ThumbDBBytesAdapter, base: str, count: int, barrier: threading.Barrier, results: list):
    barrier.wait()
    for i in range(count):
        try:
            row = cache.probe(f"{base}-{i}.jpg")
            results.append(row is not None)
        except Exception:
            results.append(False)


def test_thumbnail_cache_concurrent_set_and_get(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache = ThumbDBBytesAdapter(cache_dir / "thumbs.db")

    writer_threads = 4
    writer_loop = 50
    reader_threads = 4
    barrier = threading.Barrier(writer_threads + reader_threads)

    readers_results: list = []
    writers = [threading.Thread(target=_setter, args=(cache, f"w{n}", writer_loop, barrier)) for n in range(writer_threads)]
    readers = [threading.Thread(target=_getter, args=(cache, f"w0", writer_loop, barrier, readers_results)) for _ in range(reader_threads)]

    for t in writers + readers:
        t.start()
    for t in writers + readers:
        t.join()

    # Verify the number of inserted rows using ThumbDB helper
    db_path = cache.db_path
    with ThumbDB(db_path) as db:
        rows = db.get_rows_for_paths([f"w{i}-{j}.jpg" for i in range(writer_threads) for j in range(writer_loop)])
        assert len(rows) == writer_threads * writer_loop
