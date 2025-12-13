import sqlite3
import time
from pathlib import Path

from image_viewer.image_engine.db_operator import DbOperator


def _create_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, value INTEGER)")
    conn.commit()
    conn.close()


def test_db_operator_basic_write_and_read(tmp_path: Path):
    db_path = tmp_path / "test.db"
    _create_db(db_path)
    op = DbOperator(db_path)

    def insert(conn, v):
        conn.execute("INSERT INTO t (value) VALUES (?)", (v,))
        return v

    futures = [op.schedule_write(insert, i) for i in range(5)]
    results = [f.result(timeout=2) for f in futures]
    assert results == [0, 1, 2, 3, 4]

    def count_rows(conn):
        cur = conn.execute("SELECT count(*) FROM t")
        return int(cur.fetchone()[0])

    fut = op.schedule_read(count_rows)
    assert fut.result(timeout=2) == 5

    op.shutdown()


def test_db_operator_retry_on_operational_error(tmp_path: Path):
    db_path = tmp_path / "retry.db"
    _create_db(db_path)
    op = DbOperator(db_path)

    # Create a callable that fails first time with OperationalError, then succeeds
    calls = {"count": 0}

    def flaky_insert(conn):
        calls["count"] += 1
        if calls["count"] == 1:
            raise sqlite3.OperationalError("database is locked")
        conn.execute("INSERT INTO t (value) VALUES (?)", (123,))
        return 123

    fut = op.schedule_write(flaky_insert, retries=3)
    assert fut.result(timeout=5) == 123

    # verify row inserted
    def count_rows(conn):
        cur = conn.execute("SELECT count(*) FROM t")
        return int(cur.fetchone()[0])

    c = op.schedule_read(count_rows).result(timeout=2)
    assert c == 1
    op.shutdown()


def test_db_operator_batch_write(tmp_path: Path):
    db_path = tmp_path / "batch.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, value INTEGER)")
    conn.commit()
    conn.close()

    op = DbOperator(db_path)

    def make_insert_fn(v):
        def _fn(conn):
            conn.execute("INSERT INTO t (value) VALUES (?)", (v,))

        return _fn

    funcs = [(make_insert_fn(i), (), {}) for i in range(5)]
    fut = op.schedule_write_batch(funcs)
    fut.result(timeout=2)

    def count_rows(conn):
        cur = conn.execute("SELECT count(*) FROM t")
        return int(cur.fetchone()[0])

    assert op.schedule_read(count_rows).result(timeout=2) == 5
    op.shutdown()
