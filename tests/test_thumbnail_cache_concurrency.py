import threading
import time
from pathlib import Path

from image_viewer.image_engine.thumbnail_cache import ThumbnailCache
from image_viewer.image_engine.thumb_db import ThumbDB


def _setter(cache: ThumbnailCache, base: str, count: int, barrier: threading.Barrier):
    barrier.wait()
    for i in range(count):
        try:
            cache.set_meta(f"{base}-{i}.jpg", time.time(), i, 100, 100, 128, 128)
        except Exception:
            pass


def _getter(cache: ThumbnailCache, base: str, count: int, barrier: threading.Barrier, results: list):
    barrier.wait()
    for i in range(count):
        try:
            row = cache.get_meta(f"{base}-{i}.jpg", time.time(), i)
            results.append(row is not None)
        except Exception:
            results.append(False)


def test_thumbnail_cache_concurrent_set_and_get(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache = ThumbnailCache(cache_dir)

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
