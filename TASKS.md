# Image Viewer - Implementation Tasks

> 구현할 기능과 개선 사항을 우선순위별로 관리

## 🔥 High Priority (다음에 할 것)

### Explorer Mode Phase 3 - Performance
- [x] Engine-thread Explorer model (drop QFileSystemModel)
  - 목표: Explorer Mode에서 `QFileSystemModel.setRootPath()` 기반 스캔 제거 (UI freeze 원인)
  - 구현: EngineCore(QThread)에서 폴더 스캔 + Thumb DB 프리로드 + missing 썸네일 생성(바이트)
  - UI: QAbstractTableModel 기반 ExplorerTableModel로 bytes→QIcon 변환 (UI thread만)
  - 파일: image_viewer/image_engine/engine_core.py, image_viewer/image_engine/explorer_model.py,
          image_viewer/image_engine/engine.py, image_viewer/ui_explorer_grid.py, image_viewer/explorer_mode_operations.py

- [ ] LRU 캐시 메모리 제한 (현재 무제한)
  - 목표: 최대 500MB로 제한
  - 방법: OrderedDict + 메모리 추적
  - 파일: ui_explorer_grid.py

- [ ] 대용량 폴더 lazy loading
  - 문제: 1000+ 이미지 폴더에서 썸네일 요청 폭주
  - 해결: 스크롤 시 visible items만 로드
  - 파일: ui_explorer_grid.py

### Trim UI 개선
- [ ] 크롭 프리셋 추가 (16:9, 4:3, 1:1)
  - 이유: 매번 수동 조정이 번거로움
  - UI: 드롭다운 메뉴
  - 파일: ui_trim.py

## 📋 Medium Priority (곧 할 것)

### Explorer Mode 초기 상태 개선
- [ ] C 드라이브만 보이는 문제 해결
  - 문제: 프로그램 구동 직후 Explorer Mode에서 C:/ 만 표시됨
  - 해결 방안 1: 폴더 트리 완전히 제거하고 그리드만 사용
  - 해결 방안 2: 최근 폴더 또는 사용자 홈 디렉토리로 시작
  - 파일: ui_explorer_tree.py, explorer_mode_operations.py

### 애플리케이션 아이콘
- [ ] 프로그램 아이콘 제작 및 적용
  - 목표: 전문적인 앱 아이콘 디자인
  - 형식: .ico (Windows), .png (다양한 크기)
  - 적용: 윈도우 타이틀바, 작업 표시줄, 설치 프로그램
  - 파일: resources/icon.ico, main.py

### 패키징 준비
- [ ] libvips DLL 최적화
  - 문제: 현재 libvips 라이브러리 전체 복사 (불필요한 DLL 포함)
  - 목표: 필요한 DLL만 선별하여 크기 축소
  - 방법: 의존성 분석 후 필수 DLL만 포함
  - 파일: image_viewer/libvips/
  - 다음: Installer 패키징 (NSIS, Inno Setup 등)

### UI/UX 개선
- [ ] 메뉴 구조 정리
  - 목표: 직관적인 메뉴 구조
  - 검토: 중복 항목 제거, 논리적 그룹화
  - 파일: ui_menus.py

- [ ] 상단 툴바 아이콘 메뉴 추가
  - 목표: 자주 사용하는 기능 빠른 접근
  - 아이콘: Open Folder, Prev/Next, Zoom, Fullscreen, Settings
  - 파일: main.py, ui_menus.py

- [ ] 단축키 정리 및 문서화
  - 목표: 일관된 단축키 체계
  - 작업: shortcuts_context.md 업데이트
  - 추가: README.md에 단축키 표 추가
  - 파일: shortcuts_context.md, README.md

### 이미지 편집 기능
- [ ] Crop/Save 구현
  - 목표: 크롭 영역 선택 후 저장 기능
  - UI: 마우스 드래그로 영역 선택
  - 저장: 원본 유지 또는 덮어쓰기 옵션
  - 파일: ui_canvas.py, file_operations.py

- [ ] 간단한 회전/반전 저장
  - 현재: 뷰어에서만 회전, 저장 안 됨
  - 목표: "Save Rotated" 버튼 추가
  - 파일: file_operations.py

- [ ] 밝기/대비 조정
  - UI: 슬라이더 다이얼로그
  - 적용: pyvips로 실시간 프리뷰

### 이미지 배치 처리
- [ ] 이미지 Merge/Split 기능
  - Merge: 여러 이미지를 하나로 합치기 (세로/가로)
  - Split: 큰 이미지를 여러 조각으로 나누기
  - UI: 다이얼로그로 옵션 설정
  - 파일: 새 모듈 image_batch.py

### 키보드 단축키 개선/정리
- [ ] 숫자 키로 줌 레벨 설정 (1=100%, 2=200%)
  - 이유: 빠른 확대/축소
  - 파일: main.py keyPressEvent


## 🔮 Low Priority (나중에)

### 코드 리팩토링 - ui_explorer_grid.py
**현재 상태 (2025-12-05):**
- 파일 크기: 806줄 (Phase 2 완료 후)
- Phase 2 완료: 파일 작업 분리 (172줄 감소, 19%)
- 주요 클래스:
  - `ImageFileSystemModel`: ~373줄 (썸네일 + 메타데이터)
  - `ThumbnailGridWidget`: ~330줄 (메인 위젯)
  - `_ThumbnailListView`: ~63줄 (커스텀 툴팁)
  - `_ImageOnlyIconProvider`: ~10줄

**추가 리팩토링 검토:**
- [ ] Phase 1: 썸네일 관리 분리 (우선순위: Low)
  - 현재 ImageFileSystemModel에 잘 통합되어 있음
  - 분리 시 Signal/Slot 연결 복잡도 증가
  - 성능 문제 발생 시 재검토

- [ ] Phase 3: 메타데이터 관리 분리 (우선순위: Low)
  - 로직이 단순하여 분리 효과 미미
  - 현재 코드로 충분히 관리 가능

**결론:** Phase 2 완료로 주요 리팩토링 목표 달성. 추가 분리는 실제 필요성 발생 시 진행.

### 슬라이드쇼 모드
- [ ] 자동 재생 (3초/5초/10초 간격)
- [ ] 페이드 전환 효과

### 메타데이터 표시
- [ ] EXIF 정보 오버레이
- [ ] 촬영 날짜/카메라 모델

## 💡 Ideas (검토 필요)

- 듀얼 모니터 지원 (전체화면을 특정 모니터에)
- 이미지 비교 모드 (2개 이미지 나란히)
- 폴더 즐겨찾기
- 최근 열어본 폴더 히스토리

---

## ✅ Recently Completed (최근 1주일)

### 2025-12-17
- [x] Cleanup: remove unused compatibility shims and re-exports
  - Removed `image_viewer/image_viewer.py` compatibility shim
  - Removed `image_viewer/image_engine/migrations.py` and `image_viewer/image_engine/db_operator.py` re-export shims
  - Deleted unused `image_viewer/image_engine/fs_db_iface.py` (IDBLoader)
  - Updated `scripts/migrate_thumb_db.py` to import directly from `image_viewer.image_engine.db.migrations`
  - Updated `image_viewer/image_engine/fs_db_worker.py` imports to use `image_viewer.image_engine.db.db_operator`
  - Updated `AGENTS.md` to reflect FSModel refactor and added Development policies
- [x] View Mode 개선 - Hover 서랍 메뉴 implemented
  - Implemented left-edge hover drawer with Crop menu and smooth animation (QPropertyAnimation)
  - Files: `ui_hover_menu.py` / `ui_canvas.py` (canvas integration)

### 2025-12-07
- [x] 코드 리뷰 및 린트 수정
  - mousePressEvent, delete_current_file, start_trim_workflow 함수 분리
  - Magic numbers 상수화 (RGB_CHANNELS, ROTATION_MAX 등)
  - pyright 0 errors, ruff 67→45 issues

### 2025-12-05
- [x] WebP 변환 멀티프로세싱
  - ProcessPoolExecutor로 변경, 모든 CPU 코어 활용
  - 4코어: 최대 4배, 8코어: 최대 8배 속도 향상
- [x] Rename 다이얼로그 동적 너비 조정
  - 파일명 길이에 맞춰 300~600px 자동 조정
- [x] 삭제 확인 다이얼로그 가시성 개선
  - 큰 버튼, 명확한 색상, 포커스 표시

### 2025-12-04
- [x] Explorer 파일 작업 리팩토링 (Phase 2)
  - file_operations.py로 분리 (172줄 감소)
  - copy/cut/paste/delete/rename 함수화
- [x] Busy Cursor 구현
  - 폴더 로드, 이미지 전환, 썸네일 로딩 시 표시

### 2025-12-03
- [x] SQLite 썸네일 캐시 (thumbs.db)
  - Windows Thumbs.db 방식, 단일 파일 캐시
- [x] Theme System (Dark/Light)
- [x] Enter key toggle View↔Explorer
- [x] Window state restoration

### 2025-11-29
- [x] Explorer grid QFileSystemModel 전환
  - Windows-like 파일 작업 지원

### 2025-11-23
- [x] WebP 변환 도구

### 2025-12-12
- [x] ThumbnailCache → ThumbDB 통합
  - image_viewer/image_engine/thumb_db.py: DB wrapper 추가 및 schema fallback
  - image_viewer/image_engine/fs_db_worker.py: DB background loader (Chunked emit)
  - image_viewer/image_engine/thumbnail_cache.py: set/get/write flows use ThumbDB when available
  - tests/test_thumb_db_wrapper.py: Unit tests for get/probe/upsert
  - tests/test_thumbnail_cache_thumbdb_integration.py: Integration test (requires PySide6 to run locally)

---

### 2025-12-14
- [x] Phase 5 — Migration framework, CLI, and tests

  ## ⚙️ Phase 6 — Metrics & Finalization (In Progress)
  - [x] Add metrics/tracing to `DbOperator`, `ThumbDB`, and `migrations`
    - 목표: retry counts, task durations, migration durations
    - 파일: `image_viewer/image_engine/metrics.py`, `db_operator.py`, `thumb_db.py`, `migrations.py`
    - 테스트: `tests/test_metrics.py` 추가
    - 체크: ruff/pyright & unit tests

  ### Phase 6 progress
  - [x] Add metrics collector and integrate into `DbOperator`, `ThumbDB`, `migrations`
  - [ ] Add CI checks to exercise migrations and metrics (integration)
  - [ ] Remove legacy fallback code paths for pre-v1 DB (if safe)
  - [x] Add metrics collector and integrate into `DbOperator`, `ThumbDB`, `migrations`
    - tests: `tests/test_metrics.py` added and passing
    - docs: `dev-docs/metrics.md` added; README references metrics
    - tests: `uv run pytest` → 44 passed


  - 구현: `image_viewer/image_engine/migrations.py`, `scripts/migrate_thumb_db.py`, `tests/test_thumb_db_migration.py`
  - 주요 효과: legacy thumbnail DB 업그레이드 지원, schema `user_version` 관리, migration CLI로 수동 업그레이드 가능
  - 체크: ruff/pyright 통과, 41 tests passed


## 📝 작업 시작 전 체크리스트

1. High Priority에서 항목 선택
2. TASKS.md에 task 추가 (T-XXX)
3. 작업 완료 후:
   - [ ] TASKS.md 체크박스 체크
   - [ ] SESSIONS.md에 상세 기록
  - [ ] SESSIONS.md에 기록 상태 업데이트
   - [ ] Recently Completed로 이동
4. 1주일 후: Recently Completed에서 제거 (SESSIONS.md에는 영구 보관)
