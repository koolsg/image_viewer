import tempfile
from pathlib import Path

from image_viewer.image_engine.db.db_operator import DbOperator


def test_db_operator_shutdown_after_tasks(tmp_path: Path):
    db_path = tmp_path / "testdb.sqlite"
    op = DbOperator(db_path)

    # Schedule a bunch of quick writes
    def write_fn(conn, idx):
        conn.execute("CREATE TABLE IF NOT EXISTS t (i INTEGER)")
        conn.execute("INSERT INTO t (i) VALUES (?)", (idx,))

    for i in range(50):
        op.schedule_write(write_fn, i)

    # Shutdown and wait; worker should stop and thread should not be alive
    op.shutdown(wait=True)
    assert not op.is_alive()