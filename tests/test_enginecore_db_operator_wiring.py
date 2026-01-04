from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from image_viewer.image_engine.db.thumbdb_bytes_adapter import ThumbDBBytesAdapter
from image_viewer.image_engine.engine_core import EngineCore


def test_enginecore_start_db_loader_uses_adapter_operator(monkeypatch, tmp_path):
    """Regression: EngineCore used to reference a non-existent `_db_operator` attribute.

    Ensure the DB preload worker is wired with `ThumbDBBytesAdapter.operator`.
    """

    created: list[DummyWorker] = []

    class NoStartThread(QThread):
        def start(self, priority: QThread.Priority = QThread.InheritPriority) -> None:  # type: ignore[override]
            # Prevent spawning an actual thread in this unit test.
            return

    class DummyWorker(QObject):
        chunk_loaded = Signal(list)
        finished = Signal(int)
        missing_paths = Signal(list)

        def __init__(
            self,
            *,
            folder_path: str,
            db_path: str,
            db_operator,
            use_operator_for_reads: bool,
            thumb_width: int,
            thumb_height: int,
            generation: int,
            prefetch_limit: int,
            chunk_size: int,
        ) -> None:
            super().__init__()
            self.folder_path = folder_path
            self.db_path = db_path
            self.db_operator = db_operator
            self.use_operator_for_reads = use_operator_for_reads
            self.thumb_width = thumb_width
            self.thumb_height = thumb_height
            self.generation = generation
            self.prefetch_limit = prefetch_limit
            self.chunk_size = chunk_size
            created.append(self)

        def run(self) -> None:
            # Not executed in this test (thread is not started).
            return

    # Patch threading/worker pieces in the module under test.
    import image_viewer.image_engine.engine_core as engine_core

    monkeypatch.setattr(engine_core, "QThread", NoStartThread)
    monkeypatch.setattr(engine_core, "FSDBLoadWorker", DummyWorker)

    folder = tmp_path
    adapter = ThumbDBBytesAdapter(folder / "SwiftView_thumbs.db")

    core = EngineCore()
    core._db = adapter  # wire directly; EngineCore normally does this internally

    core._start_db_loader(str(folder))

    assert len(created) == 1
    assert created[0].db_operator is adapter.operator
