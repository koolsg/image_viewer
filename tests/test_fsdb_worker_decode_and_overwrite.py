import time
from pathlib import Path

from image_viewer.image_engine.fs_db_worker import FSDBLoadWorker
from image_viewer.image_engine.db.thumbdb_bytes_adapter import ThumbDBBytesAdapter
from image_viewer.path_utils import db_key


def test_fsdb_worker_missing_then_decode_overwrites_db(tmp_path):
    # Setup folder and image
    folder = tmp_path / "folder"
    folder.mkdir()
    img = folder / "img.jpg"
    img.write_bytes(b"hello-decode")

    # Create DB with an existing (old) row that has wrong mtime/size and no thumbnail
    db_path = folder / "SwiftView_thumbs.db"
    adapter = ThumbDBBytesAdapter(db_path)
    path_key = db_key(str(img))
    adapter.upsert_meta(path_key, 1, 1, meta={"thumbnail": None, "width": 10, "height": 10, "thumb_width": 256, "thumb_height": 195, "created_at": time.time()})

    # Run FSDBLoadWorker and capture missing paths
    worker = FSDBLoadWorker(str(folder), str(db_path), db_operator=None, use_operator_for_reads=False)

    missing = []

    def _on_missing(paths):
        missing.extend(paths)

    worker.missing_paths.connect(_on_missing)
    worker.run()

    # The path should be reported as missing because mtime/size mismatch
    assert path_key in missing

    # Simulate decode result by writing thumbnail bytes and current mtime/size
    stat = img.stat()
    mtime_ms = int(stat.st_mtime_ns) // 1_000_000
    size = int(stat.st_size)

    adapter.upsert_meta(
        path_key,
        mtime_ms,
        size,
        meta={
            "thumbnail": b"fake-thumb-bytes",
            "width": 100,
            "height": 100,
            "thumb_width": 256,
            "thumb_height": 195,
            "created_at": time.time(),
        },
    )

    # Probe DB and verify it was overwritten with new thumbnail and stats
    probe = adapter.probe(path_key)
    assert probe is not None
    assert probe[1] is not None and probe[1] == b"fake-thumb-bytes"
    assert probe[4] is not None and int(probe[4]) == int(mtime_ms)
    assert probe[5] is not None and int(probe[5]) == int(size)
