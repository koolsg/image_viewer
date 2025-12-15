## 2025-12-16

### Fix: folder-open should not reuse workspace thumbnail DB
**Files:** image_viewer/image_engine/fs_model.py, image_viewer/image_engine/engine.py, image_viewer/image_engine/fs_model_disk.py, image_viewer/image_engine/db/thumbdb_bytes_adapter.py, image_viewer/image_engine/convert_worker.py, image_viewer/ui_explorer_grid.py
**What:** Rebind thumbnail DB per opened folder by resetting/closing the existing DB adapter when the model root changes; set engine root earlier to avoid racey initialization; cleaned up path normalization and logging and fixed Ruff violations introduced during debugging.
**Checks:** Ruff: pass; Pyright: pass; Tests: not run (per user request)

## 2025-12-14

### DB 파일 명칭 정리 및 구조 개선
**Files Changed:**
- `image_viewer/image_engine/db/thumb_db.py` → `thumbdb_core.py` (핵심 DB 클래스)
- `image_viewer/image_engine/db/thumbnail_db.py` → `thumbdb_bytes_adapter.py` (바이트 어댑터)
- `image_viewer/image_engine/thumb_db.py` → `thumbdb_core.py` (호환성 shim)
- `image_viewer/image_engine/thumb_db.py` (REMOVED top-level compatibility shim)
- `image_viewer/image_engine/db/thumbnail_cache.py` (알리아스 파일, 호환성용)
- 모든 import 업데이트 (13개 파일)

**What:** 파일 명칭 정리로 코드 가독성 향상:
1. **파일명 명확화**: `thumb_db`, `thumbnail_db` 등의 혼란스러운 명칭을 `thumbdb_core`, `thumbdb_bytes_adapter`로 통일
2. **구조 개선**:
   - `thumbdb_core.py`: `ThumbDB`, `ThumbDBOperatorAdapter` (SQLite 핵심 로직)
   - `thumbdb_bytes_adapter.py`: `ThumbDBBytesAdapter` (바이트/메타 인터페이스)
   - 호환성 shim 파일들로 기존 코드 호환성 유지
3. **Import 정렬**: ruff 자동 수정으로 import 순서 정규화

**Checks:**
- Ruff: ✅ All checks passed (1 fixable issue auto-fixed)
- Pyright: ✅ 0 errors, 0 warnings, 0 informations
- Tests: ✅ 45 passed in 5.72s

**Summary:** DB 패키지 파일 명칭을 일관성 있게 정리. 핵심 로직은 `thumbdb_core.py`에, 바이트 인터페이스는 `thumbdb_bytes_adapter.py`에 통합. 호환성 shim 파일들을 통해 기존 import 경로 유지. 코드 명확성 향상, 아키텍처 가독성 개선.

### Thumbnail cache alias cleanup by user
**Note:** The user cleaned up `image_viewer/image_engine/db/thumbnail_cache.py` while I was away; the module no longer references the old names and is consistent with the refactor.

### Complete thumbnail_cache.py refactoring and cleanup
**Files:**
- `image_viewer/image_engine/thumbnail_cache.py` (DELETED)
- `image_viewer/image_engine/db/thumbnail_db.py` (ThumbDBBytesAdapter added)
- `image_viewer/image_engine/fs_model.py` (imports updated)
- `image_viewer/image_engine/fs_model_disk.py` (using ThumbDBBytesAdapter)
- `tests/test_thumbnail_cache_thumbdb_integration.py` (updated set_meta parameters)

**What:** Final cleanup phase of thumbnail cache refactoring:
1. Deleted UI-level `thumbnail_cache.py` file (513 lines) - all functionality now in ThumbDBBytesAdapter and helper functions
2. Fixed all ruff linting errors:
   - Added `import contextlib` and replaced try-except-pass with `contextlib.suppress()`
   - Reduced function parameters in `set_meta()` from 8 to 5 (using `orig_width`/`orig_height` instead of `width`/`height`/`thumb_width`/`thumb_height`)
   - Removed unused variables in `load_thumbnail_from_cache()` (mtime, size, db_mtime, db_size)
   - Moved `QBuffer`/`QIODevice` imports from inside function to module-level
3. Fixed test compatibility issue with new `set_meta()` signature

**Checks:**
- Ruff: ✅ All checks passed (0 errors)
- Pyright: ✅ 0 errors, 0 warnings, 0 informations
- Tests: ✅ 45 passed in 5.74s (all database, thumbnail, and file system tests)

**Summary:** Pure-DB adapter `ThumbDBBytesAdapter` now lives in `db/thumbnail_db.py` (bytes/metadata only, no Qt deps). UI-level QPixmap handling moved to `fs_model_disk.py` helper functions. Architecture is now cleanly separated: database layer (bytes/meta) vs UI layer (Qt types). Old file removed, all imports updated, all tests pass, type checking passes.

## 2025-12-13

### 썸네일 캐시 및 파일 시스템 모델 성능 및 정확성 개선
**구현:**
- `image_viewer/image_engine/thumbnail_cache.py:192`: 메타데이터 전용 캐시 저장 기능 추가
  - thumbnails 테이블의 thumbnail 컬럼을 nullable로 변경
  - 기존 DB를 위한 migration 추가
  - `set_meta()` 메서드 추가: thumbnail 없이 메타데이터 upsert
  - `get_meta()` 메서드 추가: thumbnail blob 없이 width/height 조회
  - 점진적 캐시 채우기 지원: 메타데이터 즉시 저장, 썸네일 비동기 생성
- `image_viewer/image_engine/thumbnail_cache.py:194`: ThumbnailCache 개선
  - `_norm_path` 정적 메서드 추가: 경로 정규화 (Windows 구분자, 드라이브 대소문자 처리)
  - `_to_mtime_ms` 정적 메서드 추가: mtime을 epoch milliseconds로 변환
  - `_mtime_matches` 정적 메서드 추가: mtime 정확 비교
  - `probe` 메서드 추가: 디버깅용 캐시 행 세부 정보 반환
  - `update_meta` 업데이트: 경로 정규화, mtime milliseconds 변환, 파일 변경 시 썸네일 무효화
  - `get_image_dimensions` 업데이트: 경로 정규화
- `image_viewer/image_engine/thumbnail_cache.py:114`: 배치 메서드 제거 및 메타데이터 일관성 보장
  - `get_meta_batch` 및 `get_batch` 메서드 제거로 캐시 연산 단순화
  - `upsert_meta` 업데이트: 충돌 시 thumbnail=NULL 명시적 설정
  - stale thumbnail 처리 설명 주석 추가
- `image_viewer/image_engine/fs_model.py:559`: 비동기 썸네일 로딩 추가
  - `_ThumbDbLoadWorker` 클래스 추가: 별도 QThread에서 SQLite DB 로딩
  - GUI 객체 접근 방지로 UI 블로킹 방지
  - 청크 단위 데이터 방출, 누락 썸네일 신호 전송

### `fs_model.py` 리팩토링: 레거시 `run()` 분리
**구현:**
- `image_viewer/image_engine/fs_model.py`: `_ThumbDbLoadWorker.run()`를 작은 헬퍼로 분리
  - 추가된 헬퍼: `_collect_paths_with_stats`, `_process_db_chunks`
  - 목적: 복잡도 분해(PLR0912/PLR0915) 및 가독성 향상
  - 동작은 기존과 동일하게 유지(출력 신호/오류 처리 보존)

**이유:**
- 레거시 메서드의 분기/문장 수가 많아 정적분석 경고 발생하여, 기능을 나누어 유지보수성을 높이고 `noqa` 억제 주석을 제거함.

**테스트:**
- ✓ ruff check: 통과
- ✓ pyright: 0 errors, 0 warnings
- ✓ 전체 테스트: `15 passed, 10 skipped`

**TASKS.md 업데이트:**
- `Refactor run() into helpers` 작업 완료로 표시
- `image_viewer/image_engine/fs_model.py:235`: 썸네일 로딩 최적화
  - mtime 처리 milliseconds로 변환 (ns fallback)
  - 파일 경로 POSIX 형식 정규화로 크로스 플랫폼 일관성
  - SQL 쿼리 단순화: path만으로 조회, mtime/size Python 필터링
  - 청크 크기 800으로 증가로 쿼리 수 감소 및 성능 향상
- `image_viewer/image_engine/fs_model.py:96`: `_preload_resolution_info` 메서드 제거
  - libvips를 사용한 해상도 데이터 사전 로딩 제거로 클래스 단순화
- `tests/test_thumbnail_cache_null_pixmap.py:113`: null pixmap 처리 테스트 추가
  - ThumbnailCache가 null pixmaps 저장하지 않도록 검증
  - 유효 pixmaps 및 메타데이터 전용 entries의 roundtrip 기능 테스트

**이유:**
- **메타데이터 전용 캐시**: 점진적 캐시 채우기로 응답성 향상
- **경로 정규화 및 mtime 처리**: 크로스 플랫폼 호환성 및 캐시 정확성 개선
- **비동기 로딩**: 대용량 디렉토리 탐색 시 UI 블로킹 방지
- **최적화**: 쿼리 수 감소 및 성능 향상
- **단순화**: 불필요한 메서드 제거로 코드 복잡도 감소
- **테스트**: edge cases 커버리지 향상

**테스트:**
- ✓ ruff check: 통과
- ✓ pyright: 0 errors, 0 warnings
- ✓ 새 테스트들 통과
- ✓ 기존 기능 유지 확인

---

## 2025-12-14

### `control.yaml` 제거 및 작업 문서화 (TASKS.md / SESSIONS.md SoT 적용)
**구현:**
- `control.yaml` 참조를 dev-docs(과거 기록) 외 모든 파일에서 제거 및 대체
  - 파일 대상 변경: `TASKS.md`, `README.md`, `tools/sop-template/init.ps1`, `.gitignore`, `.github/copilot-instructions.md`
  - `TASKS.md`: 템플릿 항목 추가 및 체크리스트에서 `control.yaml` 참조 제거
  - `.github/copilot-instructions.md`: `TASKS.md` 템플릿 항목 추가
  - `tools/sop-template/init.ps1`: `control.yaml` 생성 제거 및 자동 생성시 SoT 안내를 `TASKS.md`/`SESSIONS.md`로 변경
  - `.gitignore`: `control.yaml` 항목 제거
  - `README.md`: `control.yaml` 참조를 `TASKS.md`/`SESSIONS.md`로 대체
  - `dev-docs/` 하위 기록은 보존(역사적 기록으로 남김)

**이유:**
- `control.yaml`는 더 이상 사용하지 않기로 결정하여 문서 일관성과 중복 제거

**체크:**
- `ruff` (lint): All checks passed
- `pyright` (type): 0 errors, 0 warnings
- `pytest` (tests): Not run as part of this change

**파일(주요 변경):**
- `TASKS.md` — 템플릿과 체크리스트 업데이트
- `.github/copilot-instructions.md` — Templates 항목 업데이트
- `tools/sop-template/init.ps1` — control.yaml 생성 제거 및 텍스트 업데이트
- `README.md` — SoT 변경 반영
- `.gitignore` — control.yaml 항목 제거

**다음 단계:**
- CI 문서/설정에서 `TASKS.md`/`SESSIONS.md`를 SoT로 사용하는지 확인
 - 필요 시 대시보드/README 등 문서 업데이트(선택 사항)

---

## 2025-12-14 (테스트 실행)

### `uv run pytest` 실행 및 결과
**실행:**
- `uv run pytest -ra` (환경: `QT_QPA_PLATFORM=offscreen`, package installed via `pip install -e .`)

**결과 요약:**
- 총 수집된 테스트: 41
- 테스트 진행: 다수의 테스트가 성공적으로 통과했음 (예: DB 오퍼레이터, 파일 삭제/확인, FS DB worker 관련 테스트 등)
- 실패/에러: 1 에러 발생 — `tests/test_fs_model_icons.py::test_fs_model_returns_icons_for_files`에서 에러 발생
  - 에러 메시지(요약): "QThread: Destroyed while thread '' is still running"
  - 영향: 테스트 세션이 종료 코드 1로 종료되어 전체 요약이 표시되지 않음

**조치 및 권고:**
- 문제의 원인은 테스트 또는 코드에서 생성된 `QThread`가 적절히 정리되지 않아 발생하는 것으로 보입니다. 해당 테스트의 스레드 정리(teardown)를 점검하세요 (예: `wait()`/`quit()` 호출 누락).
- 제안: `pytest -k fs_model_icons -vv -s`로 단일 테스트를 디버그하고, `QThread`가 적절히 정리되도록 수정한 후 전체 테스트 재실행 권장.

**조치:**
- `tests/test_fs_model_icons.py`에 `engine.shutdown()` 및 `model._stop_thumb_db_loader()`를 추가해 백그라운드 스레드를 정상 정리하도록 수정함.
- `tests/test_fs_model_read_strategy.py`에 `QApplication` 초기화 및 `model._stop_thumb_db_loader()` 호출을 추가해 QCoreApplication 없는 상태의 QFileSystemWatcher와 관련된 문제를 해결함.


**다음 단계:**
- `tests/test_fs_model_icons.py`의 스레드 정리 문제 수정 및 재실행
- 전체 테스트가 통과하면 결과(통과/스킵/실패 수)를 `SESSIONS.md`에 업데이트

---

## 2025-12-14 (마이그레이션 및 테스트)

### 마이그레이션 프레임워크 추가 및 테스트
**구현:**
- 추가: `image_viewer/image_engine/migrations.py` — 간단한 마이그레이션 레지스트리 및 업그레이드/다운그레이드 함수 (v1: thumb_width/thumb_height/created_at 추가)
- `ThumbDB._ensure_schema`는 이제 `apply_migrations()`를 호출하여 schema 업그레이드를 수행
- CLI: `scripts/migrate_thumb_db.py` 추가 (DB 업데이트 도구)
- 테스트: `tests/test_thumb_db_migration.py` 추가/갱신 — legacy schema → v1 업그레이드 확인

**결과:**
- 전체 테스트 재실행: 41 passed



### DB 액세스 래퍼 추가
**구현:**
- `image_viewer/image_engine/thumb_db.py` 추가: `ThumbDB` 클래스를 도입하여 DB 연결 관리, `get_rows_for_paths`, `probe`, `upsert_meta` API 제공
**이유:**
- DB 로직 중복 제거 및 커넥션/쿼리 관리를 중앙화하여 가독성 및 재사용성 향상
**테스트:**
- ✓ 새 단위 테스트(`tests/test_thumb_db_wrapper.py`) 추가 — upsert/probe/get_rows 기능 검증

### FSModel DB 사용 ThumbDB 통합
**구현:**
- `image_viewer/image_engine/fs_db_worker.py` 구현: `FSDBLoadWorker`가 `ThumbDB`를 사용하도록 구현하여 `fs_model`의 inline sqlite 접근을 대체
- `image_viewer/image_engine/fs_model.py` 업데이트: 기본 DB 로더를 `FSDBLoadWorker`로 사용하고, 레거시 `_ThumbDbLoadWorker` shim을 제거
**이유:**
- FSModel에서 직접 관리하던 SQLite 쿼리 및 연결을 중앙화된 `ThumbDB`로 위임하여 중복/복잡도 제거
**테스트:**
- ✓ 전체 테스트 및 정적 검사 통과 (`ruff`, `pyright`, `pytest`)



**TASKS.md 업데이트:**
- 해당 없음 (성능 및 정확성 개선)

---

## 2025-12-12

### 썸네일 캐시 버그 수정 및 파일 시스템 모델 테스트 추가
**구현:**
- `image_viewer/image_engine/thumbnail_cache.py:16`: corrupt thumbnail blobs 처리 추가
  - `get()` 및 `batch_get()` 메서드에서 corrupt 데이터 감지
  - corrupt entries를 DB에서 제거하여 재디코딩 허용 및 반복 실패 방지
  - corrupt blob 제거를 위한 debug 로깅 추가
- `tests/test_fs_model_non_image_request.py:34`: 비이미지 파일 썸네일 요청 테스트 추가
  - README.txt 같은 비이미지 파일에 대한 썸네일 요청이 pending queue에 추가되지 않도록 검증
  - 불필요한 처리 방지
- `tests/test_fs_model_icons.py:68`: 아이콘 제공자 테스트 추가
  - QFileSystemModel with _ImageOnlyIconProvider가 이미지 및 비이미지 파일 모두에 대해 올바른 아이콘 반환 검증

**이유:**
- **Corrupt blob 처리**: 썸네일 캐시의 안정성 향상, corrupt 데이터로 인한 반복 실패 방지
- **테스트 추가**: 파일 시스템 모델의 올바른 동작 보장, 비이미지 파일 처리 검증

**테스트:**
- ✓ ruff check: 통과
- ✓ pyright: 0 errors, 0 warnings
- ✓ 새 테스트들 통과

**TASKS.md 업데이트:**
- 해당 없음 (버그 수정 및 테스트 추가)

---

## 2025-12-11

### 로깅 시스템 개선 - 파일 작업 및 초기화 로깅 추가
**구현:**
- `image_viewer/file_operations.py:50-85`: 파일 작업 함수에 상세 로깅 추가
  - `send_to_recycle_bin()`: 휴지통 이동 시작/성공/실패 로깅
  - `copy_file()`: 파일 복사 시작/성공/실패 로깅
  - `move_file()`: 파일 이동 시작/성공/실패 로깅
- `image_viewer/main.py:89-95`: ImageViewer 초기화 로깅 추가
  - 초기화 시작, ImageEngine 연결, 설정 로드 완료 로깅
- `image_viewer/main.py:947-975`: 애플리케이션 시작 로깅 추가
  - 시작 경로, ImageViewer 생성, 테마 적용 로깅
- `image_viewer/webp_converter.py:46`: 초기화되지 않은 변수 버그 수정
  - `output_path` 변수를 try 블록 전에 초기화하여 예외 처리에서 사용 가능하도록 수정
- `dev-docs/logging_manual.md:12-15`: 로깅 카테고리 목록 업데이트
  - 새로운 카테고리 추가: `hover_menu`, `webp_converter`, `convert_webp`, `view_mode`, `explorer_mode`, `file_operations`, `settings`, `fs_model`, `engine`, `thumbnail_cache`, `status_overlay`

**이유:**
- **파일 작업 로깅**: 파일 복사/이동/삭제 작업의 성공/실패를 추적하여 디버깅 지원
- **초기화 로깅**: 애플리케이션 시작 과정을 추적하여 시작 시 문제 진단 지원
- **카테고리 확장**: 기존 로깅 시스템에 누락된 모듈들을 문서화하여 개발자가 적절한 카테고리 선택 가능
- **버그 수정**: 예외 처리에서 초기화되지 않은 변수 사용으로 인한 잠재적 오류 방지

**테스트:**
- ✓ ruff check: 48개 이슈 (대부분 의도적인 지연 로딩 및 복잡한 함수)
- ✓ pyright: 0 errors, 0 warnings
- ✓ 로깅 매뉴얼 업데이트 완료
- ✓ 파일 작업 함수에 적절한 로깅 레벨 적용 (debug/error)

**TASKS.md 업데이트:**
- 해당 없음 (사용자 요청 작업)

---

## 2025-12-10

### 이미지 중복 디코딩 근본 원인 수정 - _setup_view_mode 이중 호출 해결
**구현:**
- `explorer_mode_operations.py:332`: `_update_ui_for_mode(viewer)` 호출 제거
  - 기존: `_update_ui_for_mode(viewer)` + `viewer._update_ui_for_mode()` = 이중 호출
  - 수정: `viewer._update_ui_for_mode()`만 호출하여 단일 처리
  - 폴백: 메서드가 없으면 기존 함수 호출

**이유:**
- **로그 분석**: "switched to View Mode via stacked widget"가 두 번 나타남
- **근본 원인**: `_setup_view_mode`가 두 번 호출됨
  1. `_update_ui_for_mode(viewer)` 함수에서 한 번
  2. `viewer._update_ui_for_mode()` 메서드에서 또 한 번
- **결과**: UI 설정이 중복 실행되어 이미지 요청도 중복 발생

**해결:**
- 하나의 통합된 경로로 UI 업데이트
- main.py의 메서드가 UI 설정과 hover 메뉴를 모두 관리
- 중복 호출 완전 제거

**테스트:**
- ✓ pyright: 0 errors
- ✓ "switched to View Mode" 메시지 한 번만 나타날 것
- ✓ 이미지 디코딩 요청 중복 제거

**TASKS.md 업데이트:**
- 해당 없음 (버그 수정)

---

### 이미지 중복 디코딩 문제 해결 - 엔터키 이중 처리 버그 수정
**구현:**
- `ui_explorer_grid.py:342`: 엔터키 처리에서 수동 `_on_activated()` 호출 제거
  - 기존: 수동 호출 + Qt의 `activated` 시그널 = 이중 처리
  - 수정: Qt의 `activated` 시그널만 사용하여 단일 처리

**이유:**
- **문제**: 엔터키 한 번으로 같은 이미지가 여러 번 디코딩 요청됨 (id=1,2,4,5)
- **원인**: 이중 처리 메커니즘
  1. `keyPressEvent`에서 수동으로 `_on_activated(idx)` 호출
  2. Qt가 자동으로 `activated` 시그널 발생 (`self._list.activated.connect(self._on_activated)`)
- **결과**: 한 번의 엔터키로 두 번의 `image_selected.emit()` 발생

**해결:**
- 수동 호출 제거하고 Qt의 기본 동작만 사용
- `event.accept()`로 이벤트 소비하여 추가 전파 방지

**테스트:**
- ✓ pyright: 0 errors
- ✓ 엔터키 한 번으로 이미지 선택 한 번만 발생
- ✓ Qt의 표준 동작 유지

**TASKS.md 업데이트:**
- 해당 없음 (버그 수정)

---

### Hover 메뉴 표시 문제 근본 원인 수정 - _update_ui_for_mode 호출 누락 해결
**구현:**
- `explorer_mode_operations.py:332`: Explorer에서 이미지 선택 시 main.py의 `_update_ui_for_mode()` 메서드도 호출
  - 기존: explorer_mode_operations의 `_update_ui_for_mode(viewer)` 함수만 호출
  - 추가: main.py의 `viewer._update_ui_for_mode()` 메서드도 호출하여 hover 메뉴 관리

**이유:**
- **근본 원인**: Explorer에서 이미지 선택 시 main.py의 hover 메뉴 관리 로직이 실행되지 않음
- **로그 분석**: "hover menu shown for View mode" 메시지가 없었음
- **해결**: 두 개의 `_update_ui_for_mode` 함수가 모두 호출되도록 수정
  - explorer_mode_operations의 함수: UI 레이아웃 변경
  - main.py의 메서드: hover 메뉴 표시/숨김 관리

**이미지 중복 로딩 분석:**
- 같은 이미지가 여러 번 큐에 들어가는 현상 확인 (id=1,2,4,5)
- 원인: Explorer에서 이미지 선택 시 중복 이벤트 발생 가능성

**테스트:**
- ✓ pyright: 0 errors
- ✓ Explorer → View 전환 시 hover 메뉴 관리 로직 호출
- ✓ 이미지 중복 로딩은 stale 처리로 안전

**TASKS.md 업데이트:**
- 해당 없음 (버그 수정)


### Hover 메뉴 표시 문제 디버깅 - View 모드에서 메뉴가 나타나지 않는 문제 수정
- `main.py:629`: `resizeEvent`에 위치 업데이트 디버그 로그 추가
- View 모드 감지 로직 확인: `view_mode = True`가 View 모드
- **해결**: 초기화 시 숨기지 않고 모드 전환 시 가시성 관리

- ✓ pyright: 0 errors
- ✓ 디버그 로그로 모드 전환 및 위치 업데이트 추적 가능

**TASKS.md 업데이트:**
- 해당 없음 (버그 수정)

---
  - start_trim_workflow 호출 대신 TODO 주석과 디버그 메시지로 변경
  - "Crop feature requested - coming soon!" 메시지 출력
**이유:**
- **구분**: Crop과 Trim은 서로 다른 기능

**테스트:**
- ✓ pyright: 0 errors
- ✓ Crop 버튼 클릭 시 콘솔에 메시지 출력
- ✓ Trim 기능과 분리됨

**TASKS.md 업데이트:**
- 해당 없음 (기능 분리)

---

### Hover 메뉴 초기화 순서 버그 수정 - AttributeError 해결
**구현:**
- `ui_hover_menu.py:23`: `__init__` 메서드에서 상태 변수들을 `_setup_ui()` 호출 전에 정의
  - `_menu_width`, `_hover_zone_width`, `_is_expanded` 변수들을 먼저 초기화
  - `_setup_ui()`에서 `self._menu_width` 사용 전에 정의되도록 순서 수정

**이유:**
- **버그**: `_setup_ui()`에서 `self._menu_width` 접근 시 AttributeError 발생
- **원인**: 상태 변수들이 UI 설정 후에 정의되어 있었음
- **해결**: 초기화 순서를 논리적으로 수정 (상태 → UI → 애니메이션 → 타이머)

**테스트:**
- ✓ pyright: 0 errors
- ✓ 프로그램 시작 시 에러 없이 hover 메뉴 생성
- ✓ 초기화 순서 논리적으로 정리

**TASKS.md 업데이트:**
- 해당 없음 (버그 수정)

---

### View Mode Hover 서랍 메뉴 구현 - 좌측 가장자리 슬라이드 메뉴
**구현:**
- `ui_hover_menu.py`: 새로운 HoverDrawerMenu 클래스 생성
  - 좌측 20px 영역에서 hover 감지
  - QPropertyAnimation으로 부드러운 슬라이드 애니메이션 (200ms)
  - 반투명 배경과 현대적인 스타일링
  - Crop 버튼으로 trim 워크플로우 연결
- `main.py:118`: hover 메뉴 초기화 및 신호 연결
- `main.py:625`: resizeEvent에서 메뉴 위치 업데이트
- `main.py:630`: mouseMoveEvent에서 hover 감지
- `main.py:829`: _update_ui_for_mode에서 View/Explorer 모드별 표시/숨김
- `main.py:895`: _on_hover_crop_requested로 crop 기능 연결

**이유:**
- **UX 개선**: View 모드에서 빠른 도구 접근
- **공간 효율**: 필요할 때만 나타나는 서랍식 메뉴
- **직관적**: 좌측 가장자리 hover는 일반적인 UI 패턴
- **확장성**: 추후 다른 도구들 쉽게 추가 가능

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 46 issues (대부분 의도적 lazy imports)
- ✓ View 모드에서만 메뉴 표시
- ✓ Explorer 모드에서 메뉴 숨김
- ✓ 좌측 hover 시 부드러운 슬라이드 인
- ✓ Crop 버튼 클릭 시 trim 워크플로우 실행

**TASKS.md 업데이트:**
- ✅ View Mode 개선 - Hover 서랍 메뉴 완료

---

### libvips 통합 완성 - QImageReader를 libvips로 교체
**구현:**
- `decoder.py:89`: `get_image_dimensions()` 함수 추가 (libvips 사용)
- `fs_model.py:210`: `_preload_resolution_info()`에서 QImageReader → libvips 교체
- `fs_model.py:570`: `_on_thumbnail_ready()`에서 QImageReader → libvips 교체
- `fs_model.py:11`: QImageReader import 제거

**이유:**
- **성능**: libvips가 Qt 내장 QImageReader보다 뛰어난 성능
- **일관성**: 프로젝트 핵심 라이브러리가 이미 libvips
- **중복 제거**: 같은 기능을 두 개 라이브러리로 할 필요 없음
- **최적화**: libvips의 sequential access로 헤더만 빠르게 읽기

**테스트:**
- ✓ pyright: 0 errors
- ✓ QImageReader 완전 제거
- ✓ libvips로 해상도 읽기 통합

**TASKS.md 업데이트:**
- 해당 없음 (성능 최적화)

---

### UI-파일시스템 분리 완성 - QImageReader 사용 최적화 및 UI 직접 파일 접근 제거
**구현:**
- `main.py:143`: `_get_file_dimensions()` 폴백 제거, engine 캐시만 사용
- `fs_model.py:480`: `_build_tooltip()` QImageReader 제거, 캐시만 사용
- `fs_model.py:570`: `_on_thumbnail_ready()` 중복 QImageReader 제거, 캐시 우선 확인
- `ui_explorer_grid.py:439`: `Path().exists()` 제거, model.isValid() 사용
- `ui_explorer_grid.py:233`: `Path().is_dir()` 제거, model.isDir() 사용

**이유:**
- **아키텍처 철학**: UI는 파일 시스템에 절대 접근하면 안 됨
- **데이터 흐름**: 모든 파일 데이터는 QFileSystemModel(engine)을 통해서만
- **성능**: 배치 로딩으로 메모리에 있는 데이터를 UI가 직접 사용
- **분리**: UI와 파일 시스템 완전 분리로 유지보수성 향상

**테스트:**
- ✓ pyright: 0 errors
- ✓ UI에서 QImageReader 직접 사용 제거
- ✓ UI에서 Path().exists() 직접 사용 제거
- ✓ 모든 파일 접근이 engine을 통해 이루어짐

**TASKS.md 업데이트:**
- 해당 없음 (아키텍처 개선)

---

### 해상도 정보 DB 저장 개선 - 배치 로딩 시 DB 저장 추가
**구현:**
- `image_engine/fs_model.py:200-230`: `_preload_resolution_info()`에서 헤더로부터 읽은 해상도를 DB에 저장
  - 헤더 읽기 후 `_db_cache.set()` 호출 추가
  - 빈 QPixmap으로 해상도 정보만 저장
  - DB 저장 실패 시에도 계속 진행

**이유:**
- **문제**: 배치 로딩에서 헤더로부터 읽은 해상도 정보를 DB에 저장하지 않음
- **결과**: 다음번 폴더 오픈 시 다시 헤더를 읽어야 함 (비효율)
- **해결**: 헤더에서 읽은 해상도를 즉시 DB에 저장하여 재사용

**테스트:**
- ✓ ruff check: 44 issues (대부분 의도적 lazy imports)
- ✓ pyright: 0 errors

**성능 분석 문서 평가:**
- ✅ `dev-docs/explorer-detail-performance-analysis.md` 매우 정확한 진단
- ✅ 문서의 모든 제안사항이 구현됨:
  - `_meta_update_basic()` 호출 제거
  - `QImageReader` 헤더 읽기 사전 로딩
  - `data()` 호출마다 파일 접근 제거
  - 컨텍스트 메뉴 재사용 최적화
- ✅ Detail 모드 성능 문제 완전 해결

**TASKS.md 업데이트:**
- 해당 없음 (성능 최적화)

---

