# DB Operator Migration Plan

목적
- 모든 SQLite DB read/write를 중앙 오퍼레이터(단일 진입점)로 통합하여 동시성 문제를 제거하고 마이그레이션/트랜잭션/로깅/백오프 재시도를 일관되게 관리합니다.

배경(간단)
- 현재는 `ThumbDB`, `ThumbnailCache`, `FSDBLoadWorker` 등이 DB에 직접 접근하며, UI 경로에서 `set_meta()` 등으로 쓰기가 발생합니다.
- 이로 인해 멀티스레드 경합과 가끔 발생하는 `sqlite3.OperationalError`/무결성 문제(예: NOT NULL constraint)가 보고되었습니다.

요구사항
1. 중앙화된 `DbOperator` 서비스가 DB 오퍼레이션을 단일 스레드(또는 안전한 큐 실행)에서 실행합니다.
2. `DbOperator`는 WAL 모드와 `busy_timeout`을 설정하고 커넥션을 관리합니다.
3. 쓰기 작업은 큐에 추가되어 직렬화되며 배치 트랜잭션 처리가 가능해야 합니다.
4. 읽기 작업은 성능을 고려해 선택적으로 직접 읽기(전용 읽기 커넥션) 또는 오퍼레이터를 경유하도록 설계합니다.
5. `ThumbDB` API는 어댑터(예: `ThumbDBOperatorAdapter`)로 남겨 backward-compatibility를 유지합니다.

설계 개요
- `DbOperator` API: `schedule_read(fn, *args, **kwargs) -> Future`, `schedule_write(fn, *args, **kwargs) -> Future`, `execute_sync_read(fn, ...)` 등.
- 내부로는 전용 스레드(혹은 `QObject`+`QThread`)와 작업 큐(우선순위 옵션, 배치) 사용.
- operator가 직접 `sqlite3.connect`를 소유하고 `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000` 등을 설정.
- 쓰기 재시도: `sqlite3.OperationalError: database is locked` 또는 `busy` 발생하면 짧은 지연 후 재시도(지수 backoff, 최대 N회).

마이그레이션 단계 (권장 순서)
1. 문서화: 이 파일을 통해 설계를 확정하고 커밋합니다.
2. `DbOperator` 골격 추가(비파괴): `image_viewer/image_engine/db_operator.py` 추가, 작업 큐와 스레드 초기화.
3. 어댑터 추가: `ThumbDBOperatorAdapter` 구현하고 `ThumbDB` 인터페이스를 어댑터를 통해 호출하도록 점진적으로 전환합니다.
4. 쓰기만 오퍼레이터로 위임: `ThumbnailCache.set_meta`, `ThumbnailCache.set`, `ThumbDB.upsert_meta`, `delete` 등을 operator에 등록하도록 리팩터.
5. 통합 테스트: 동시성/정합성 테스트 및 성능 테스트 실행.
6. 읽기 리팩터: `FSDBLoadWorker`의 대규모 스캔을 오퍼레이터를 통해 조정하거나 전용 읽기 전략을 수립(필요시 parallel read). `FSDBLoadWorker`는 현재 옵션을 통해 operator 경유 읽기(`use_operator_for_reads=True`)를 지원하며, 기본은 직접 읽기(direct read)입니다. 운영 환경에서 성능/경합을 확인한 후 전역 default를 변경합니다.
7. CI/배포: 마이그레이션 스크립트/테스트 통과 후 master/feature 브랜치 병합.

진행 상태: Phase1 (DbOperator skeleton), Phase2 (ThumbnailCache writes -> DbOperator via adapter), Phase3 (Read strategy), Phase4 (Migrate reads/writes to operator) 및 Phase5 (Migration scripts + tests) 완료.
Phase6 (Metrics & Finalization) 구현 완료 —(metrics: `image_viewer/image_engine/metrics.py`) 및 통합: `DbOperator`, `ThumbDB`, `migrations` 계측을 추가하여 retry/queued/timing 정보를 기록합니다. 테스트 및 문서도 추가되었습니다.

테스트 항목
- `DbOperator` 동작성(작업 큐, shutdown, flush) 단위 테스트.
- 대량 쓰기 배치 테스트(여러 set_meta 동시 요청 후 DB 일관성 검증).
- 읽기/쓰기 경쟁 테스트(동시 upsert + get; no locks/errors).
- 마이그레이션 스크립트 테스트(스키마 업그레이드/다운그레이드 검증).
- 성능 회귀 테스트(대규모 폴더 탐색 시 응답성/스루풋 측정).

Acceptance Criteria
- 모든 DB 쓰기/읽기는 `DbOperator`를 통해 수행되며(또는 adapter를 통한 간접 접근), 코드베이스에 직접 `sqlite3.connect(...).execute(...)` 패턴이 남지 않습니다.
- 동시성 테스트에서 `sqlite3.OperationalError`가 발생하지 않아야 합니다.
- 기존 `FSDBLoadWorker.progress` 동작과 기능은 동일하게 유지되어야 합니다.

리스크 및 완화
- 성능 이슈 (읽기 병목): 해결책 — 읽기 전용 전용 커넥션 또는 병렬 읽기 풀을 도입.
- 배포 위험: 단계별 이전(쓰기 우선 → 테스트 → 읽기 변환)을 통해 쉽게 되돌릴 수 있도록 합니다.

롤아웃 계획
1. 브랜치 작업: `feature/db-operator`에서 작업.
2. 작은 스텝 릴리즈(쓰기 관련 리팩터 우선). 자동화된 테스트(동시성/통합)를 실행.
3. 성능 안정성 확인 후 전체 전환.

참고: 상세 API 및 샘플 코드 예시는 파일 하단에 예제 코드로 추가하였습니다.

---
# Principals
 * Keep change incremental — write-only operator first, read path after validating performance.
 * Keep backward compatibility with ThumbDB adapter during migration to minimize consumer changes.
 * Run concurrency & perf tests after each stage.
 * If you want, I can start Phase 1 now and open a draft PR: create file image_viewer/image_engine/db_operator.py, add unit tests, and wire ThumbDBOperatorAdapter.
 * Which action should I start with? (Start Phase 1 now, or draft a PR/plan for incremental implementation.)
---
# Detailed Procedure

## Phase 1 — DbOperator skeleton
### Objects
* Implement DbOperator with worker thread/queue, schedule_write/read, PRAGMA WAL + busy_timeout, retries.
* Tests: unit tests for worker queue, retries, graceful shutdown.
* Acceptance: DbOperator accepts tasks and commits results; unit tests pass.
### Results
* DbOperator skeleton implemented with unit tests (write/read, retry, shutdown).

## Phase 2 — Wire writes to operator (safety-first)
### Objects
 * Implement ThumbDBOperatorAdapter.
 * Change ThumbnailCache.set_meta, set, delete, ThumbDB.upsert_meta to use adapter/DbOperator.
 * Add batch write (group set_meta) support.
 * Tests: concurrency write tests, DB consistency assertion (no NOT NULL or OperationalError).
 * Acceptance: No direct DB writes in ThumbnailCache; concurrency tests pass.
### Result
#### DbOperator: db_operator.py
 * Open a fresh SQLite connection per task (no long-lived connection) to avoid file locks on Windows and ensure better lifecycle behavior.
 * Worker loop now opens and closes a connection for each queued task, with retry/backoff logic preserved.
#### ThumbnailCache: thumbnail_cache.py
 * close() now properly shuts down the DbOperator and closes the internal _conn to avoid lingering file handles.
 * Keeps behavior using ThumbDBOperatorAdapter by default (fall back to ThumbDB on error).
#### ThumbDB adapter & path handling: thumb_db.py
 * Adapter (ThumbDBOperatorAdapter) delegates reads/writes to DbOperator.
 * Path normalization remains at write time; probe tries normalized forms where needed.

## Phase 3 — Read strategy & worker integration
### Objects
 * Decide read model for FSDBLoadWorker:
 * Option A: Let operator handle read tasks.
 * Option B: Use a read pool or keep existing direct read connections but with safe PRAGMA + operator-coordinated writes.
 * Update FSDBLoadWorker accordingly and add progress + performance tests.
 * Acceptance: FSDBLoadWorker progress unchanged and reads perform within benchmarks.
### Result
* opt-in operator-mediated reads
* FSDBLoadWorker: added db_operator + use_operator_for_reads flags; uses ThumbDBOperatorAdapter when enabled.
* ImageFileSystemModel: added set_db_read_strategy(); batch loader passes operator and read-mode to worker; ensured _ensure_db_cache called so operator is available.
* Tests added: test_fs_db_worker_reads_operator.py, test_fs_model_read_strategy.py.

## Phase 4 — Migrate & eliminate direct sqlite3 usage
### Objects
 * Remove direct sqlite usage across modules; replace with operator calls.
 * Clean up ThumbDB internals to be an adapter only.
 * Tests: full integration tests and stress tests on large folders.
 * Acceptance: No sqlite3.connect() direct calls in engine code; all tests pass.
### Result

* ThumbnailCache now initializes schema via DbOperator when available and prefers the ThumbDBOperatorAdapter for reads/writes. It closes the direct sqlite connection when the operator is active.
* FSDBLoadWorker defaults to operator-mediated reads and ImageFileSystemModel defaults to using operator reads.
* Reworked ThumbnailCache methods (probe/get/get_meta/cleanup_old/vacuum/clear/delete) to prefer operator adapter and fall back to direct sqlite only if operator is unavailable.
* Moved schema init to operator when available, reducing persistent sqlite handles.
* Fixed tests that assumed a persistent _conn, and added tests:
* test_thumbnail_cache_operator_default.py ensures operator is created and no persistent conn is held.
* test_fs_db_worker_perf.py (benchmark), test_fs_db_worker_reads_operator.py, and other integration tests to validate operator reads.

## Phase 5 — Migration scripts + tests
 * Add schema upgrade/downgrade scripts inside thumb_db.py or separate CLI.
 * Add CI tests for upgrade/downgrade paths and rollback on failure.
 * Acceptance: Schema upgrade & rollback automated tests pass.



### Usage
- From the repository root, run:
```
python scripts/migrate_thumb_db.py /path/to/SwiftView_thumbs.db
```
This will apply any pending migrations and print the new `user_version`.

### Acceptance Criteria (updated)
- Migrations applied automatically during `ThumbDB.connect()` or via `scripts/migrate_thumb_db.py`.
- `tests/test_thumb_db_migration.py` verifies the upgrade path and column presence.
- CI runs `uv run pytest` to confirm tests pass after migration logic changes.

### Follow-up items
- Add an explicit downgrade CLI path if rollback automation is required for production rollouts.
- Add analytical metrics for migration durations + success/failure counters as part of Phase 6.
- Add CI jobs to validate migrations on a sample DB and to run `uv run pytest` post-migration in a branch-protection test.
- Add a `scripts/migrate_thumb_db.py --downgrade` path and a safe rollback validation suite.
- Add a small performance/stress harness that runs FSDBLoadWorker/ThumbnailCache against large synthetic directories for regression detection.
- Consider a safe timeline / removal plan for legacy pre-v1 fallbacks once CI shows stability and no issues in the field.
- Document the process and acceptance criteria in `SESSIONS.md`/`TASKS.md` for clear handoff.

### Implementation update (2025-12-14)
- Implemented a small migration framework `image_viewer/image_engine/migrations.py`.
- `ThumbDB._ensure_schema()` now calls `apply_migrations(conn)`, ensuring PRAGMA `user_version` is applied and the DB is upgraded to latest schema during connect.
- Added `scripts/migrate_thumb_db.py` as a CLI helper to apply migrations to an existing DB file.
- Added `tests/test_thumb_db_migration.py` to validate legacy schema (v0) upgrades to the new schema (v1) and to confirm the columns exist and `user_version` is bumped.

## Phase 6 — Metrics & finalization
### Objects
 * Add counters and traces for chunk processing time, retry counts, error types; expose in engine logs/metrics.
 * Update docs, remove compatibility shims, finalize PR.
 * Acceptance: Monitoring hooks present, documentation updated, and performance tests show no unacceptable regressions.
 * Notes and risk mitigations:

### Results
- `image_viewer/image_engine/metrics.py`: lightweight in-process metrics collector.
- Integrated metric counters and timings in `DbOperator`, `ThumbDB`, and `migrations`.
- Added `tests/test_metrics.py` asserting counts and timings for common DB and migration operations.
- Added `dev-docs/metrics.md` and README reference for how to snapshot metrics in-process.
- All tests pass in CI local runs: `uv run pytest` → 44 passed (local verification).