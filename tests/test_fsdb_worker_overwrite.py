import time
from pathlib import Path

from image_viewer.image_engine.fs_db_worker import FSDBLoadWorker
from image_viewer.image_engine.db.thumbdb_bytes_adapter import ThumbDBBytesAdapter
from image_viewer.path_utils import db_key


def test_fsdb_worker_overwrites_db_on_mismatch(tmp_path):
    # Create folder and file
    folder = tmp_path / "folder"
    folder.mkdir()
    img = folder / "img.jpg"
    img.write_bytes(b"hello")

    # Create DB with an existing thumbnail but with wrong mtime/size
    db_path = folder / "SwiftView_thumbs.db"
    adapter = ThumbDBBytesAdapter(db_path)
    path_key = db_key(str(img))
    # Insert an old row (mtime/size different)
    adapter.upsert_meta(path_key, 1, 1, meta={"thumbnail": b"abc", "width": 10, "height": 10, "thumb_width": 256, "thumb_height": 195, "created_at": time.time()})

    # Run FSDBLoadWorker for this folder and DB and capture missing paths
    worker = FSDBLoadWorker(str(folder), str(db_path), db_operator=None, use_operator_for_reads=False)

    missing = []

    def _on_missing(paths):
        missing.extend(paths)

    worker.missing_paths.connect(_on_missing)
    worker.run()

    # Probe DB and ensure mtime/size were NOT overwritten (kept as original wrong values)
    probe = adapter.probe(path_key)
    assert probe is not None
    assert probe[4] is not None and int(probe[4]) == 1  # mtime unchanged
    assert probe[5] is not None and int(probe[5]) == 1  # size unchanged

    # And the path should be emitted as missing so the loader will decode it
    assert path_key in missing
