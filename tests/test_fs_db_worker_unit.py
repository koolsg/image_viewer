import pytest

from image_viewer.image_engine.fs_db_worker import FSDBLoadWorker


def test_worker_instantiation():
    # 단순 인스턴스화 테스트(스켈레톤 검증)
    worker = FSDBLoadWorker(db_path=":memory:")
    assert worker is not None
