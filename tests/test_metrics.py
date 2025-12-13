import sqlite3
from pathlib import Path

from image_viewer.image_engine.db_operator import DbOperator
from image_viewer.image_engine.metrics import metrics
from image_viewer.image_engine import migrations


def _create_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS thumbnails (path TEXT PRIMARY KEY, thumbnail BLOB, width INTEGER, height INTEGER, mtime INTEGER, size INTEGER)"
    )
    conn.commit()
    conn.close()


def test_metrics_db_operator_basic(tmp_path: Path):
    db_path = tmp_path / "metrics.db"
    _create_db(db_path)
    metrics.reset()
    op = DbOperator(db_path)

    def insert(conn, v):
        conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, value INTEGER)")
        conn.execute("INSERT INTO t (value) VALUES (?)", (v,))
        return v

    futures = [op.schedule_write(insert, i) for i in range(3)]
    results = [f.result(timeout=2) for f in futures]
    assert results == [0, 1, 2]
    snap = metrics.snapshot()
    assert snap["counters"].get("db_operator.write_queued", 0) >= 3
    assert "db_operator.task_duration" in snap["timings"]
    op.shutdown()


def test_metrics_db_operator_retry_counts(tmp_path: Path):
    db_path = tmp_path / "metrics_retry.db"
    _create_db(db_path)
    metrics.reset()
    op = DbOperator(db_path)
    calls = {"count": 0}

    def flaky_insert(conn):
        calls["count"] += 1
        if calls["count"] == 1:
            raise sqlite3.OperationalError(" locked")
        conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, value INTEGER)")
        conn.execute("INSERT INTO t (value) VALUES (?)", (123,))
        return 123

    fut = op.schedule_write(flaky_insert, retries=3)
    assert fut.result(timeout=5) == 123
    snap = metrics.snapshot()
    assert snap["counters"].get("db_operator.write_retries", 0) >= 1
    op.shutdown()


def test_metrics_migrations(tmp_path: Path):
    db_path = tmp_path / "migrate.db"
    conn = sqlite3.connect(str(db_path))
    # create legacy schema (user_version 0)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS thumbnails (path TEXT PRIMARY KEY, thumbnail BLOB, width INTEGER, height INTEGER, mtime INTEGER, size INTEGER)"
    )
    conn.commit()
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    metrics.reset()
    migrations.apply_migrations(conn)
    snap = metrics.snapshot()
    # we should have applied v1 migration
    assert snap["counters"].get("migrations.applied_v1", 0) == 1
    conn.close()
