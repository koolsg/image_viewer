Metrics and Diagnostics
=======================

This document describes the minimal in-process metrics available for
development and CI debugging. The project ships a lightweight collector
(`image_viewer/image_engine/metrics.py`) which records simple counters and
timings.

Available keys (examples):
- `db_operator.write_queued` - number of scheduled write tasks
- `db_operator.read_queued` - number of scheduled read tasks
- `db_operator.write_retries` - retry attempts for write operations
- `db_operator.task_duration` - durations for DB tasks (list)
- `thumb_db.connects` - number of times `ThumbDB.connect()` was called
- `thumb_db.ensure_schema_duration` - time spent ensuring schema

How to access metrics in a running process
-----------------------------------------
Import and snapshot:

```python
from image_viewer.image_engine.metrics import metrics
print(metrics.snapshot())
```

Testing guidance
----------------
- `tests/test_metrics.py` contains unit tests exercising metrics for
  `DbOperator` and the migration framework.
- The metrics collector supports `metrics.reset()` for test isolation.

Future improvements
-------------------
- Export metrics via a HTTP endpoint or Prometheus client for richer
  observability.
- Add histogram buckets / percentiles for timing metrics.
