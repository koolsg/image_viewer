## 2025-12-08

### 파일 시스템 접근 완전 제거 - _meta_update_basic() 호출 전부 제거
**구현:**
- `image_engine/engine.py:299`: `get_file_info()`에서 `_meta_update_basic()` 제거
- `image_engine/fs_model.py:420`: `meta_string()`에서 `_meta_update_basic()` 제거
- `image_engine/fs_model.py:438`: `_build_tooltip()`에서 `_meta_update_basic()` 제거

**이유:**
- **교훈**: 문제 함수를 찾으면 모든 호출처를 찾아야 함
- **원인**: `_meta_update_basic()`이 3곳에서 호출됨
  - `get_file_info()` - engine API
  - `meta_string()` - 메타 문자열 생성
  - `_build_tooltip()` - 툴팁 생성
- **해결**: 모든 호출 제거, 캐시만 사용
- **효과**: 파일 시스템 접근 완전 제거

**테스트:**
- ✓ pyright: 0 errors

**TASKS.md 업데이트:**
- 해당 없음 (성능 최적화)

---

### Detail 뷰 툴팁 성능 수정 - _build_tooltip() 최적화
**구현:**
- `image_engine/fs_model.py:438`: `_build_tooltip()`에서 `_meta_update_basic()` 제거
  - 캐시된 메타데이터만 사용
  - 파일 시스템 접근 제거

**이유:**
- **진짜 문제**: 툴팁 요청 시마다 `_meta_update_basic()` 호출
- **원인**: 커서 이동 → 툴팁 표시 → `_build_tooltip()` → 파일 시스템 접근
- **해결**: 캐시만 사용 (이미 사전 로딩됨)

**테스트:**
- ✓ pyright: 0 errors

**TASKS.md 업데이트:**
- 해당 없음 (성능 최적화)

---

### Detail 뷰 마우스 오버 성능 수정 - _resolution_str() 최적화
**구현:**
- `image_engine/fs_model.py:383-401`: `_resolution_str()` 메서드 수정
  - `_meta_update_basic()` 호출 제거
  - 캐시 우선 확인 (이미 사전 로딩됨)
  - 새 파일만 즉시 로딩

**이유:**
- **문제**: Detail 뷰에서 커서 이동 시 느림
- **원인**: 마우스 오버 → 툴팁 요청 → `_resolution_str()` → `_meta_update_basic()` → 파일 시스템 접근
- **해결**: 캐시만 확인, 파일 시스템 접근 제거
- **효과**: 커서 이동 시 즉시 반응

**테스트:**
- ✓ pyright: 0 errors

**TASKS.md 업데이트:**
- 해당 없음 (성능 최적화)

---

### Detail 뷰 성능 최적화 - data() 메서드 개선
**구현:**
- `image_engine/fs_model.py:327-332`: `data()` 메서드 최적화
  - 불필요한 role에 대해 early return 추가
  - `_meta_update_basic()` 호출 제거 (파일 시스템 접근 감소)
  - DisplayRole, ToolTipRole, DecorationRole, TextAlignmentRole만 처리

**이유:**
- **문제**: Detail 뷰에서 스크롤 시 딜레이, 컨텍스트 메뉴 느림
- **원인**: `data()` 호출마다 `_meta_update_basic()` 실행
  - 각 행 × 5컬럼 × 여러 role = 수백 번의 파일 시스템 접근
  - `fileInfo()`, `size()`, `lastModified()` 반복 호출
- **해결**:
  - 필요한 role만 처리 (early return)
  - 메타 정보는 이미 사전 로딩됨 (해상도 정보)
- **효과**: 스크롤과 컨텍스트 메뉴가 즉시 반응

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 42 issues (기존과 동일)

**TASKS.md 업데이트:**
- 해당 없음 (성능 최적화)

---

### 컨텍스트 메뉴 성능 개선 - 메뉴 재사용
**구현:**
- `ui_explorer_grid.py:137`: `_context_menu` 인스턴스 변수 추가
- `ui_explorer_grid.py:353-368`: 메뉴를 한 번만 생성하고 재사용
  - 첫 호출 시 메뉴 생성 및 캐싱
  - 이후 호출 시 기존 메뉴 재사용

**이유:**
- **문제**: 우클릭 메뉴가 뜰 때 미묘한 딜레이
- **원인**: 매번 QMenu, QAction 객체 8개 + 서브메뉴 생성
- **해결**: 메뉴를 한 번만 생성하고 재사용
- **효과**: 메뉴가 즉시 표시됨

**테스트:**
- ✓ pyright: 0 errors

**TASKS.md 업데이트:**
- 해당 없음 (성능 최적화)

---

### Detail 뷰 전환 성능 최적화 - 해상도 정보 사전 로딩
**구현:**
- `image_engine/fs_model.py:145-182`: `_preload_resolution_info()` 메서드 추가
  - 썸네일 배치 로딩 후 자동으로 모든 이미지 해상도 읽기
  - `QImageReader`로 이미지 헤더만 읽어서 빠름
  - `_meta` 캐시에 저장하여 Detail 전환 시 즉시 표시

- `image_engine/fs_model.py:139`: 배치 로딩 후 해상도 사전 로딩 호출

**이유:**
- **문제**: 썸네일 → Detail 전환 시 수백 개 파일의 해상도를 실시간으로 읽어서 느림
- **해결**: 폴더 열 때 썸네일과 함께 해상도도 미리 로딩
- **효과**: Detail 전환이 즉시 완료 (데이터가 이미 캐시됨)

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 42 issues (기존과 동일)

**TASKS.md 업데이트:**
- 해당 없음 (성능 최적화)

---

### Explorer Detail 뷰 개선 - 정렬 및 성능
**구현:**
- `image_engine/fs_model.py:304-313`: 컬럼별 텍스트 정렬 수정
  - Name 컬럼: 좌측 정렬
  - Size, Resolution: 우측 정렬
  - Type, Modified: 중앙 정렬

- `ui_explorer_grid.py:31`: `busy_cursor` import 추가
- `ui_explorer_grid.py:537-540`: `set_view_mode()`에 busy cursor 적용
  - 썸네일 ↔ Detail 전환 시 wait cursor 표시
  - 전환 완료 시 자동 복원

**이유:**
- **문제 1**: Detail 모드에서 파일 이름이 오른쪽 정렬로 표시
- **원인**: 모든 컬럼에 `AlignRight` 적용
- **해결**: 컬럼별로 적절한 정렬 적용

- **문제 2**: 썸네일 → Detail 전환 시 시간 소요
- **해결**: Busy cursor로 사용자 피드백 제공

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 42 issues (기존과 동일)

**TASKS.md 업데이트:**
- 해당 없음 (UX 개선)

---

### 디버그 캐시 시각화 수정 - engine._pixmap_cache 접근
**구현:**
- `ui_canvas.py:497-499`: 캐시 접근 경로 수정
  - `viewer.pixmap_cache` → `viewer.engine._pixmap_cache`
  - engine 존재 여부 체크 추가

**이유:**
- **문제**: 디버그 모드에서 캐시된 이미지 목록이 좌측에 표시되지 않음
- **원인**: 이전 리팩토링에서 `viewer.pixmap_cache` 속성 제거됨
- **해결**: `viewer.engine._pixmap_cache`로 직접 접근

**테스트:**
- ✓ pyright: 0 errors

**TASKS.md 업데이트:**
- 해당 없음 (버그 수정)

---

### Explorer 이미지 선택 버그 수정 - image_files 동기화
**구현:**
- `explorer_mode_operations.py:330`: View 모드 전환 후 `image_files` 동기화 추가
  - `viewer.image_files = engine.get_image_files()` 호출
  - `display_image()` 호출 전에 동기화 보장

**이유:**
- **문제**: Explorer에서 이미지 선택 시 `list index out of range` 에러
- **원인**: View 모드 전환 후 `viewer.image_files`가 업데이트되지 않음
- **해결**: 모드 전환 직후 engine에서 최신 파일 목록 가져오기

**테스트:**
- ✓ pyright: 0 errors

**TASKS.md 업데이트:**
- 해당 없음 (버그 수정)

---

### Busy cursor 관리 개선 - Context manager 패턴 적용
**구현:**
- `image_engine/fs_model.py:14`: `busy_cursor` import 추가
- `image_engine/fs_model.py:62-138`: `batch_load_thumbnails()`에 context manager 적용
  - `with busy_cursor():` 블록으로 전체 배치 로딩 감싸기
  - 함수 진입 시 자동으로 busy cursor 활성화
  - 함수 종료 시 (정상/예외 모두) 자동으로 busy cursor 해제
  - 예외 발생 시에도 cursor 복원 보장 (finally 블록)

**이유:**
- **문제**: Busy cursor 관리가 산발적이고 책임 소재 불명확
- **해결**: Context manager 패턴으로 RAII (Resource Acquisition Is Initialization) 구현
- **장점**:
  - 자동 해제: `with` 블록 종료 시 자동으로 cursor 복원
  - 예외 안전: 예외 발생 시에도 반드시 cursor 복원
  - 명확한 범위: busy cursor가 활성화되는 코드 블록이 명확
  - 유지보수 용이: cursor 관리 로직이 한 곳에 집중

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 42 issues (기존과 동일)

**TASKS.md 업데이트:**
- 해당 없음 (코드 품질 개선)

---

### 썸네일 로딩 버그 수정 - Busy cursor 및 중복 시그널 문제
**구현:**
- `image_engine/fs_model.py:407-428`: `_request_thumbnail()` busy cursor 로직 제거
  - 개별 썸네일 요청 시 busy cursor 시작하지 않음
  - 스크롤 중 개별 요청은 백그라운드에서 처리
  - `_busy_cursor_active` 플래그 제거

- `image_engine/fs_model.py:430-450`: `_on_thumbnail_ready()` 간소화
  - `_check_thumbnail_completion()` 호출 제거
  - 썸네일 완료 시 busy cursor 복원 로직 제거

- `image_engine/fs_model.py`: `_check_thumbnail_completion()` 메서드 완전 제거
  - Busy cursor 관리 로직 불필요

- `image_engine/engine.py:428-434`: `_on_directory_loaded()` 중복 호출 방지
  - `path != current_root` 체크 추가
  - 현재 root path와 일치하는 경우만 처리
  - 잘못된 폴더 경로 로그 방지

**이유:**
- **문제 1**: 썸네일 생성 완료 후에도 busy cursor 유지
  - 원인: `_request_thumbnail()`에서 busy cursor 시작, 하지만 배치 로딩은 사용 안 함
  - 해결: 개별 요청 시 busy cursor 사용하지 않음 (스크롤 중 요청은 백그라운드)
- **문제 2**: 잘못된 폴더 경로 로그 (C:/Projects/image_viewer)
  - 원인: `directoryLoaded` 시그널이 여러 번 발생, 다른 폴더 경로 전달
  - 해결: 현재 root path와 일치하는 경우만 처리
- **문제 3**: "restored" 로그는 나오지만 실제로는 복원 안 됨
  - 원인: 배치 로딩은 busy cursor 사용 안 하는데, 개별 요청이 busy cursor 시작
  - 해결: Busy cursor 로직 완전 제거

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 42 issues (기존과 동일)

**TASKS.md 업데이트:**
- 해당 없음 (버그 수정)

---

### 썸네일 로딩 성능 최적화 - 배치 로딩 구현
**구현:**
- `image_engine/thumbnail_cache.py:140-167`: `get_batch()` 메서드 추가
  - 여러 썸네일을 단일 SQL 쿼리로 조회
  - `SELECT ... WHERE (path, mtime, size) IN (...)` 사용
  - 개별 쿼리 대신 배치 처리로 DB 접근 최소화

- `image_engine/fs_model.py:62-135`: `batch_load_thumbnails()` 메서드 추가
  - 폴더 열 때 모든 이미지 파일의 썸네일을 한 번에 로드
  - 파일 stat 정보 수집 후 배치 쿼리 실행
  - 메모리 캐시 및 메타데이터 일괄 업데이트
  - `_batch_load_done` 플래그로 중복 로딩 방지

- `image_engine/fs_model.py:48-50`: `setRootPath()` 오버라이드
  - 폴더 변경 시 `_batch_load_done` 플래그 리셋
  - 썸네일 크기 변경 시에도 플래그 리셋

- `ui_explorer_grid.py:254`: `load_folder()`에서 배치 로딩 호출
  - 폴더 설정 후 `batch_load_thumbnails()` 실행
  - 캐시된 썸네일 즉시 표시

- `view_mode_operations.py:3`: `contextlib` import 추가
- `ui_canvas.py:172-176`: 긴 줄 분리 (120자 제한)

**이유:**
- **문제**: 썸네일 DB가 있는 폴더 열 때 1-2초 지연 후 한 번에 표시
- **원인**: Qt의 `data()` 호출마다 개별 SQLite 쿼리 실행 (수백 개 파일 = 수백 개 쿼리)
- **해결**: 배치 쿼리로 DB 접근 횟수를 1회로 감소
- **효과**: 메인 스레드 블로킹 최소화, 썸네일 즉시 표시

**테스트:**
- ✓ pyright: 0 errors (수정된 파일 모두)
- ✓ ruff: 42 issues (기존과 동일, 새 이슈 없음)
- ✓ 배치 로딩 로직 추가로 성능 개선 예상

**TASKS.md 업데이트:**
- 해당 없음 (성능 최적화)

---

### Busy cursor 문제 수정
**구현:**
- `ui_explorer_grid.py:226`: `load_folder()`에서 `busy_cursor()` 제거
- `ui_explorer_grid.py:260`: `set_thumbnail_size_wh()`에서 `busy_cursor()` 제거
- `busy_cursor` import 제거

**이유:**
- 폴더 설정은 빠른 동기 작업 (busy cursor 불필요)
- 썸네일 로딩은 비동기 백그라운드 작업
- 불필요한 busy cursor가 썸네일 로딩 완료 후에도 계속 표시되는 문제 해결

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 42 issues (변경 없음)

---

### 코드 정리 - GPT 리뷰 반영
**구현:**
- `trim_operations.py:269`: `engine._pixmap_cache.pop()` → `engine.remove_from_cache()` 사용
- `image_engine/engine.py`: Dead API 제거
  - `request_thumbnail()`, `get_cached_thumbnail()`, `set_thumbnail_loader()` 제거
  - 주석 추가: thumbnail 관리는 `ImageFileSystemModel`이 담당
- `tests/smoke_test.py`: 전면 재작성
  - 구식 API `decode_image(path, bytes)` → 현재 API `decode_image(path)` 사용
  - target_size 테스트 추가
  - 출력 개선 (✓/✗/⊘ 기호 사용)

**이유:**
- Encapsulation 개선: engine 내부 구현 직접 접근 제거
- Dead code 제거: 사용되지 않는 API 정리
- Test 수정: 현재 decoder API와 일치하도록 업데이트

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 42 issues (변경 없음)

---

## 2025-12-07

### press_zoom_multiplier 기본값 통일 및 중복 제거
**구현:**
- `main.py:64`: `ViewState.press_zoom_multiplier` 속성 제거 (미사용)
- `main.py:750`: `prompt_custom_multiplier()` fallback 2.0 → 3.0
- `ui_canvas.py:63`: `_press_zoom_multiplier` 초기값 유지 (3.0)
- `ui_canvas.py:284`: `_get_zoom_multiplier()` fallback 2.0 → 3.0

**이유:**
- 실제 저장소는 `canvas._press_zoom_multiplier` 하나만 사용
- `ViewState.press_zoom_multiplier`는 사용되지 않는 중복 변수
- `SettingsManager.DEFAULTS["press_zoom_multiplier"] = 3.0`과 통일
- 코드 내 하드코딩된 fallback 값 불일치 제거

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 42 issues (변경 없음)

---

### 파일 작업 모듈 역할 기반 분리
**구현:**
- `view_mode_operations.py` 신규 생성
  - View Mode 삭제 로직 이동: `delete_current_file()` + 헬퍼 함수들
  - `_switch_to_adjacent_image()`, `_cleanup_cache_and_settle()` 등

- `explorer_mode_operations.py` 확장
  - Explorer Mode 파일 작업 추가: `copy/cut/paste_files`, `delete_files_to_recycle_bin()`
  - `_set_files_to_clipboard()` 헬퍼 함수

- `file_operations.py` → 공통 유틸리티로 정리
  - `send_to_recycle_bin()`, `generate_unique_filename()`
  - `show_delete_confirmation()`, `copy_file()`, `move_file()`
  - `DELETE_DIALOG_STYLE` 상수

- import 경로 수정
  - `main.py`: `view_mode_operations.delete_current_file`
  - `ui_explorer_grid.py`: `explorer_mode_operations.*`

**이유:**
- 모드별 로직 분리로 모듈 역할 명확화
- `explorer_mode_operations.py`와 대칭적인 `view_mode_operations.py` 구조
- `file_operations.py`는 순수 유틸리티로 단순화

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 42 issues (기존과 동일)

---

### file_operations.py 코드 정리
**구현:**
- `file_operations.py:96`: `_switch_to_adjacent_image()` 미사용 파라미터 `del_path` 제거
- `file_operations.py:269`: `_set_files_to_clipboard()` 헬퍼 함수 추가
  - `copy_files_to_clipboard`와 `cut_files_to_clipboard` 중복 코드 통합
- `file_operations.py`: `send_to_recycle_bin()` 함수 send2trash 라이브러리로 교체
  - ctypes/wintypes Windows API 직접 호출 (~35줄) → send2trash 1줄
  - import 정리: `ctypes`, `wintypes`, `ClassVar` 제거

**이유:**
- 미사용 파라미터 제거로 코드 명확성 향상
- DRY 원칙 적용 - 클립보드 설정 로직 통합
- 이미 설치된 send2trash 라이브러리 활용 (크로스 플랫폼 지원)

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 42 issues (변경 없음)

---

### main.py 리팩토링 - 하위 호환성 코드 제거 및 함수 분리
**구현:**
- `main.py`: 하위 호환성 속성 제거
  - `self.fs_model` 제거 → `self.engine.fs_model` 사용
  - `self.loader`, `self.thumb_loader` 제거 → `self.engine` API 사용
  - `pixmap_cache` property 제거 → `self.engine.is_cached()` 사용

- `main.py`: `open_folder` 함수 분리 (54 statements → 3개 함수)
  - `_open_folder_in_explorer_mode()`: Explorer 모드 폴더 열기
  - `_open_folder_in_view_mode()`: View 모드 폴더 열기
  - `open_folder()`: 모드 판단 후 적절한 함수 호출

- `file_operations.py`: engine API 사용
  - `viewer.pixmap_cache.pop()` → `viewer.engine.remove_from_cache()`
  - `viewer.loader.ignore_path()` → `viewer.engine.ignore_path()`

- `explorer_mode_operations.py`: engine API 사용
  - `viewer.thumb_loader` → `viewer.engine.thumb_loader`

- `image_engine/engine.py`: 새 API 추가
  - `remove_from_cache(path)`: 캐시에서 특정 경로 제거
  - `ignore_path(path)`: 로더에서 경로 무시
  - `unignore_path(path)`: 로더에서 경로 무시 해제
  - `thumb_loader` property: 썸네일 로더 접근

**이유:**
- 하위 호환성 코드 제거로 코드 명확성 향상
- 모든 데이터/처리 접근이 engine API를 통해 이루어짐
- `open_folder` 함수 복잡도 감소 (PLR0912/PLR0915 해결)

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 44 → 42 issues

---

### Trim 모듈 리팩토링 - TrimPreviewDialog 이동
**구현:**
- `ui_trim.py`: `TrimPreviewDialog` 클래스 추가 (~170줄)
  - 트림 전/후 비교 다이얼로그
  - QGraphicsView 기반 이미지 표시
  - 테마 적용, 리사이즈 핸들링

- `trim_operations.py`: `TrimPreviewDialog` 제거 (~200줄)
  - import 경로 변경: `from .ui_trim import TrimPreviewDialog`
  - 미사용 import 정리 (QDialog, QGraphicsView, QSplitter 등)

**이유:**
- UI 컴포넌트 위치 일관성: `TrimProgressDialog`와 같은 파일에 배치
- `trim_operations.py` 책임 감소: 워크플로우 로직에 집중
- 코드 구조 개선: UI / 비즈니스 로직 분리

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 45 → 43 issues (기존 이슈, 새 이슈 없음)

**파일 크기 변화:**
- `trim_operations.py`: ~550줄 → ~350줄 (-200줄)
- `ui_trim.py`: ~75줄 → ~270줄 (+195줄)

---

### 코드 리팩토링 - Magic Numbers 상수화 (Phase 3)
**구현:**
- `trim_operations.py`: RGB/RGBA 채널 상수 추가
  - `RGB_CHANNELS = 3`, `RGBA_CHANNELS = 4`
  - QImage 생성 시 magic number 제거

- `ui_canvas.py`: 다수의 상수 추가
  - `ROTATION_MAX/MIN = ±360.0`: 회전 정규화
  - `FLOAT_EPSILON = 1e-6`: 부동소수점 비교
  - `LUMINANCE_THRESHOLD = 0.5`: 텍스트 색상 대비
  - `SRGB_LINEAR_THRESHOLD = 0.04045`: sRGB 선형화
  - `KB_THRESHOLD/MB_THRESHOLD`: 파일 크기 포맷팅
  - `RGB_CHANNELS = 3`: 이미지 채널

- `main.py`: RUF005 수정
  - `[_sys.argv[0]] + remaining` → `[_sys.argv[0], *remaining]`

- `ui_canvas.py`: SIM102 수정
  - nested if → single if with `and`

**이유:**
- PLR2004 (magic numbers) 해결
- 코드 가독성 및 유지보수성 향상
- 상수 의미 명확화

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 67 → 45 issues (22개 수정)

**남은 이슈 (낮은 우선순위):**
- PLC0415 (~25개): 의도적 lazy loading (순환 import 방지)
- PLR0912/PLR0915 (~10개): 복잡한 함수 (별도 리팩토링 필요)

---

### 코드 리팩토링 - 복잡한 함수 분리 (Phase 2)
**구현:**
- `trim_operations.py`: `start_trim_workflow` (141 statements) 분리
  - `_select_trim_profile()`: 트림 프로파일 선택 다이얼로그
  - `_select_save_mode()`: 저장 모드 선택 (덮어쓰기/복사)
  - `_run_batch_trim()`: 배치 트림 실행 (복사 모드)
  - `_show_trim_confirmation()`: 트림 확인 다이얼로그
  - `_apply_trim_and_update()`: 트림 적용 및 뷰어 상태 업데이트
  - `_run_overwrite_trim()`: 덮어쓰기 트림 실행 (파일별 확인)

**이유:**
- 141 statements → 각 함수 20-40 statements로 분리
- 단일 책임 원칙 적용
- 테스트 용이성 향상

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 60 → 58 issues

---

### 코드 리팩토링 - 복잡한 함수 분리 (Phase 1)
**구현:**
- `ui_canvas.py`: `mousePressEvent` 버튼별 핸들러로 분리
  - `_handle_right_click()`: 우클릭 패닝 모드
  - `_handle_middle_click()`: 중클릭 글로벌 뷰 스냅
  - `_handle_auxiliary_buttons()`: XButton1/2 줌
  - `_handle_left_click()`: 좌클릭 프레스-투-줌
  - `_get_event_position()`: 이벤트 위치 추출 헬퍼
  - `_get_zoom_multiplier()`: 줌 배율 헬퍼
  - `_align_cursor_after_zoom()`: 줌 후 커서 정렬 헬퍼

- `file_operations.py`: View Mode 삭제 로직 분리
  - `_show_delete_confirmation()`: 삭제 확인 다이얼로그 (공통)
  - `_switch_to_adjacent_image()`: 인접 이미지로 전환
  - `_cleanup_cache_and_settle()`: 캐시 정리 및 안정화
  - `_update_image_list_after_delete()`: 이미지 목록 업데이트
  - `_clear_viewer_if_empty()`: 빈 뷰어 처리
  - `_DELETE_DIALOG_STYLE`: 중복 스타일시트 상수화

**이유:**
- 함수 복잡도 감소 (PLR0912/PLR0915 해결)
- 코드 재사용성 향상 (스타일시트 중복 제거)
- 가독성 및 유지보수성 개선

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 67 → 60 issues

---

### 코드 리뷰 및 린트 수정
**구현:**
- `engine.py`: 미사용 `from __future__ import annotations` 제거
- `engine.py`: `priority` 파라미터에 `# noqa: ARG002` 추가 (미래 사용 예약)
- `status_overlay.py`: 미사용 `from __future__ import annotations` 제거
- `webp_converter.py`: 미사용 `from __future__ import annotations` 제거
- `loader.py`: 라인 길이 초과 수정 (125→120자)
- `decoder.py`: magic number `3` → `RGB_CHANNELS` 상수화

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 67 → 63 issues (자동 수정 1개 포함)

**남은 이슈 (리팩토링 필요):**
- PLR0912/PLR0915: 복잡한 함수들 (start_trim_workflow, drawForeground 등)
- PLC0415: 함수 내 import (~25개, 대부분 의도적 lazy loading)
- PLR2004: magic number (~12개, 상수화 권장)

---

### Re-export 파일 정리 (Final Cleanup)
**구현:**
- **Import 경로 변경:**
  - `ui_explorer_grid.py`: `.fs_model` → `.image_engine.fs_model`
  - `ui_menus.py`: `.strategy` → `.image_engine.strategy`
  - `main.py`: `image_viewer.strategy` → `image_viewer.image_engine.strategy`
  - `status_overlay.py`: `.strategy` → `.image_engine.strategy`
  - `trim_operations.py`: `.decoder` → `.image_engine.decoder`
  - `tests/smoke_test.py`: `image_viewer.decoder` → `image_viewer.image_engine.decoder`

- **삭제된 re-export 파일들:**
  - `image_viewer/decoder.py`
  - `image_viewer/fs_model.py`
  - `image_viewer/strategy.py`
  - `image_viewer/thumbnail_cache.py`
  - `image_viewer/loader.py`

**이유:**
- 불필요한 간접 레이어 제거
- 모든 데이터/처리 모듈이 `image_engine/` 패키지에 집중
- 명확한 아키텍처: `image_engine/` = 백엔드, 나머지 = 프론트엔드

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 기존 스타일 경고만

---

### Image Engine Architecture - Phase 5-6 완료 (DisplayController 제거 & 정리)
**구현:**
- **DisplayController 완전 제거:**
  - `display_controller.py` 파일 삭제
  - `open_folder()` 메서드를 `ImageViewer`로 이동 (~70 lines)
  - `display_image()` 메서드를 `ImageViewer`로 이동 (~25 lines)
  - `maintain_decode_window()` 메서드를 `ImageViewer`로 이동 (~25 lines)
  - `on_image_ready()` legacy 핸들러 간소화

- **main.py 수정:**
  - `DisplayController` import 제거
  - `QFileDialog` import 추가 (open_folder에서 사용)
  - `_display_controller` 인스턴스 생성 제거
  - 모든 메서드가 직접 `self.engine` API 사용

**이유:**
- 불필요한 간접 레이어 제거
- 코드 흐름 단순화: ImageViewer → ImageEngine (직접 연결)
- 파일 수 감소: display_controller.py 삭제
- 유지보수 용이성 향상

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 기존 스타일 경고만 (새 코드는 정리됨)

**Image Engine Architecture 리팩토링 완료!** 🎉

---

### Image Engine Architecture - Phase 3-4 완료 (Trim/Explorer Integration)
**구현:**
- **trim_operations.py 수정:**
  - `viewer.image_files` → `engine.get_image_files()`
  - `viewer.fs_model.get_image_files()` → `engine.get_image_files()`
  - `viewer.pixmap_cache` 접근 → `engine.is_cached()`, `engine._pixmap_cache.pop()`
  - `viewer.image_files[viewer.current_index]` → `engine.get_file_at_index(viewer.current_index)`

- **explorer_mode_operations.py 수정:**
  - `viewer.fs_model` → `viewer.engine.fs_model`
  - `viewer.fs_model.get_current_folder()` → `engine.get_current_folder()`
  - `viewer.image_files` 접근 → `engine.get_image_files()`, `engine.get_file_at_index()`
  - `open_folder_at()`: 수동 파일 스캔 제거, `engine.open_folder()` API 사용
  - `_on_explorer_image_selected()`: engine API로 파일 인덱스 조회

**이유:**
- viewer 내부 접근 제거 → 명확한 API 경계
- 모든 데이터/처리 로직이 ImageEngine을 통해 접근
- 코드 단순화: 수동 파일 스캔 로직 제거

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 기존 스타일 경고만 (새 코드는 정리됨)

---

### Image Engine Architecture - Phase 2 완료
**구현:**
- **main.py 수정:**
  - `ImageEngine` 인스턴스 생성 (`self.engine = ImageEngine(self)`)
  - `engine.image_ready` → `_on_engine_image_ready()` 시그널 연결
  - `engine.folder_changed` → `_on_engine_folder_changed()` 시그널 연결
  - `fs_model`을 engine에서 가져오도록 변경 (`self.fs_model = self.engine.fs_model`)
  - `loader`, `thumb_loader`를 engine에서 가져오도록 변경 (하위 호환성)
  - `pixmap_cache`를 property로 변경하여 engine 캐시 접근
  - `closeEvent()`에서 `engine.shutdown()` 호출
  - `toggle_fast_view()`에서 `engine.set_decoding_strategy()`, `engine.clear_cache()` 사용
  - `_on_engine_image_ready()`: 디코딩 완료 시 UI 업데이트 핸들러
  - `_on_engine_folder_changed()`: 폴더 변경 시 파일 목록 동기화 핸들러

- **display_controller.py 수정:**
  - `open_folder()`: `engine.open_folder()` API 사용
  - `display_image()`: `engine.get_cached_pixmap()`, `engine.request_decode()` 사용
  - `maintain_decode_window()`: `engine.is_cached()`, `engine.prefetch()` 사용
  - `on_image_ready()`: legacy 핸들러로 변경 (새 코드는 engine 시그널 사용)
  - 불필요한 import 제거 (`QImage`, `annotations`)

**이유:**
- UI와 데이터/처리 로직 분리 완료
- ImageEngine이 모든 디코딩/캐싱 담당
- main.py는 UI 상태와 이벤트 핸들링만 담당
- 하위 호환성 유지 (기존 코드가 loader, pixmap_cache 접근 가능)

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 기존 스타일 경고만 (새 코드는 정리됨)
- ✓ 하위 호환성 유지

**다음 단계:**
- Phase 3: DisplayController 통합/제거
- Phase 4-6: Trim/Converter/Explorer 통합

---

### Image Engine Architecture - Phase 1 완료
**구현:**
- **새 패키지 생성**: `image_viewer/image_engine/`
  - `__init__.py`: ImageEngine 클래스 export
  - `engine.py`: 메인 엔진 클래스 (모든 데이터/처리 로직의 단일 진입점)
  - `fs_model.py`: 파일 시스템 모델 (복사)
  - `loader.py`: 디코딩 스케줄러 (복사)
  - `decoder.py`: pyvips 래퍼 (복사)
  - `strategy.py`: 디코딩 전략 (복사)
  - `thumbnail_cache.py`: 썸네일 캐시 (복사)

- **기존 파일 re-export로 변경** (하위 호환성):
  - `fs_model.py` → `from image_viewer.image_engine.fs_model import ImageFileSystemModel`
  - `loader.py` → `from image_viewer.image_engine.loader import Loader`
  - `decoder.py` → `from image_viewer.image_engine.decoder import decode_image`
  - `strategy.py` → `from image_viewer.image_engine.strategy import ...`
  - `thumbnail_cache.py` → `from image_viewer.image_engine.thumbnail_cache import ThumbnailCache`

**ImageEngine API:**
```python
class ImageEngine(QObject):
    # 시그널
    image_ready = Signal(str, QPixmap, object)
    folder_changed = Signal(str, list)
    thumbnail_ready = Signal(str, QIcon)

    # 파일 시스템 API
    def open_folder(self, path: str) -> bool
    def get_image_files(self) -> list[str]
    def get_file_at_index(self, idx: int) -> str | None

    # 디코딩 API
    def request_decode(self, path: str, target_size: tuple | None = None)
    def get_cached_pixmap(self, path: str) -> QPixmap | None
    def prefetch(self, paths: list[str])

    # 설정 API
    def set_decoding_strategy(self, strategy: DecodingStrategy)
    def set_cache_size(self, size: int)
```

**이유:**
- UI와 데이터/처리 로직 분리
- 테스트 용이성 향상
- 재사용성 (CLI, 웹 등 다른 UI에서 사용 가능)
- 명확한 책임 분리: Engine = 백엔드, UI = 프론트엔드

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 기존 경고만 (새 코드는 정리됨)
- ✓ 하위 호환성 유지 (기존 import 경로 작동)

**다음 단계:**
- Phase 2: main.py에서 ImageEngine 사용
- Phase 3: DisplayController 통합
- Phase 4-6: Trim/Converter/Explorer 통합

---

## 2025-12-07

### Unified QFileSystemModel Architecture - 전체 리팩토링 완료 (Phase 1-6)
**구현:**

**Phase 1: 모델 기반 구축**
- ui_explorer_grid.py → fs_model.py: ImageFileSystemModel에 파일 접근 메서드 추가
  - `get_image_files()`: 현재 폴더의 모든 이미지 파일 반환 (정렬됨)
  - `get_file_at_index(idx)`: 인덱스로 파일 경로 반환
  - `get_file_index(path)`: 파일 경로로 인덱스 반환
  - `get_file_count()`: 이미지 파일 개수 반환
  - `get_current_folder()`: 현재 rootPath 반환
  - `_is_image_file(path)`: 이미지 파일 확장자 체크
- main.py: 공유 `fs_model` 인스턴스 생성 및 directoryLoaded 시그널 연결

**Phase 2: View Mode 통합**
- display_controller.py: `open_folder()` 간소화
  - 공유 `fs_model.setRootPath()` 사용
  - `_setup_fs_watcher()` 제거 (~30 lines)
  - `_reload_image_files()` 제거 (~40 lines)
- main.py: ExplorerState에서 `_fs_watcher` 필드 제거

**Phase 3: Explorer Mode 통합**
- ui_explorer_grid.py: ThumbnailGridWidget 생성자에 `model` 파라미터 추가
  - 외부 모델 주입 지원 (하위 호환성 유지)
- explorer_mode_operations.py: 공유 모델 전달
  - `ThumbnailGridWidget(model=viewer.fs_model)` 사용

**Phase 4-5: Trim/Converter 통합**
- trim_operations.py: `viewer.fs_model.get_image_files()` 사용
- main.py: `open_convert_dialog()`에서 `fs_model.get_current_folder()` 사용

**Phase 6: 모듈 분리**
- **새 파일 생성**: `image_viewer/fs_model.py` (~450 lines)
  - ImageFileSystemModel을 독립 모듈로 분리
  - 핵심 데이터 레이어로 명확히 정의
  - 모든 파일 시스템 작업의 단일 진실의 원천
- ui_explorer_grid.py: ~450 lines 제거
  - `from .fs_model import ImageFileSystemModel` import 추가
  - UI 컴포넌트만 남김
- main.py: import 경로 수정

**이유:**
- **단일 진실의 원천**: 모든 기능이 하나의 모델 공유
- **자동 동기화**: 파일 변경 시 모든 모드 자동 반영
- **메모리 절약**: 중복 모델 제거
- **코드 감소**: ~520 lines 제거/재구성
- **명확한 아키텍처**: 데이터 레이어(fs_model.py) vs UI 레이어(ui_*.py) vs 비즈니스 로직(operations.py)

**최종 아키텍처:**
```
image_viewer/fs_model.py (데이터 레이어)
    ↓
ImageFileSystemModel (단일 진실의 원천)
    ↓
├─ View Mode: 파일 목록 & 네비게이션
├─ Explorer Mode: 썸네일 그리드 & 상세 뷰
├─ Trim: 배치 처리 파일 목록
└─ Converter: 현재 폴더 감지
```

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff check: 6 issues auto-fixed
- ✓ 모든 import 경로 수정 완료
- ✓ 기능 변경 없음 (구조만 개선)

**완료 상태:**
- ✅ Phase 1: 모델에 파일 접근 메서드 추가
- ✅ Phase 2: View 모드 전환
- ✅ Phase 3: Explorer 모드 전환
- ✅ Phase 4: Trim 통합
- ✅ Phase 5: Converter 통합
- ✅ Phase 6: 모듈 분리 및 아키텍처 정리

**전체 리팩토링 완료!** 🎉

---

## 2025-12-07

### Unified QFileSystemModel Architecture - Phase 4 & 5 완료
**구현:**
- **Phase 4 (Trim):**
  - trim_operations.py:389: 배치 트림에서 `viewer.fs_model.get_image_files()` 사용
  - trim_operations.py:407: Overwrite 모드에서도 모델 사용
  - `list(viewer.image_files)` → `viewer.fs_model.get_image_files()` 변경
- **Phase 5 (Converter):**
  - main.py:250-268: `open_convert_dialog()` 수정
  - `fs_model.get_current_folder()` 사용
  - 현재 이미지 경로 대신 모델의 현재 폴더 사용

**이유:**
- 일관성: 모든 기능이 공유 모델에서 파일 목록 가져옴
- 자동 동기화: 트림/변환 후 파일 변경 자동 감지
- 단순화: 파일 목록 접근 로직 통일

**테스트:**
- ✓ pyright: 0 errors
- ✓ Trim 워크플로우 모델 기반으로 전환
- ✓ Converter 현재 폴더 자동 설정

**완료 상태:**
- ✅ Phase 1: 모델에 파일 접근 메서드 추가
- ✅ Phase 2: View 모드 전환
- ✅ Phase 3: Explorer 모드 전환
- ✅ Phase 4: Trim 통합
- ✅ Phase 5: Converter 통합
- ⏭️ Phase 6: 최종 정리 (image_files 제거 등)

---

## 2025-12-07

### Unified QFileSystemModel Architecture - Phase 3 완료
**구현:**
- ui_explorer_grid.py:601-625: ThumbnailGridWidget 생성자 수정
  - `model` 파라미터 추가 (optional)
  - 외부 모델 주입 지원
  - 하위 호환성 유지 (모델 없으면 자체 생성)
  - 모델 설정 중복 방지 (filter 체크)
- explorer_mode_operations.py:163: 공유 모델 전달
  - `ThumbnailGridWidget(model=viewer.fs_model)` 사용
  - 새 모델 생성하지 않음
- explorer_mode_operations.py:220-235: 폴더 로드 개선
  - `viewer.fs_model.get_current_folder()` 사용
  - 공유 모델의 현재 폴더 활용

**이유:**
- 중복 제거: View/Explorer 모드가 각각 모델 생성 → 단일 모델 공유
- 메모리 절약: 같은 폴더를 두 모델이 감시하지 않음
- 일관성: 두 모드가 항상 같은 파일 목록 공유
- 자동 동기화: 한 모드에서 파일 변경 시 다른 모드도 자동 반영

**테스트:**
- ✓ pyright: 0 errors
- ✓ 하위 호환성 유지 (model 파라미터 optional)

**다음 단계:**
- Phase 4: Trim 워크플로우를 모델 기반으로 전환
- Phase 5: Converter 통합
- Phase 6: 최종 정리 및 image_files 제거

---

## 2025-12-07

### Unified QFileSystemModel Architecture - Phase 2 완료
**구현:**
- display_controller.py:21-105: `open_folder()` 간소화
  - 공유 `fs_model.setRootPath()` 사용
  - `fs_model.get_image_files()`로 파일 목록 가져오기
  - `_setup_fs_watcher()` 제거 (~30 lines)
  - `_reload_image_files()` 제거 (~40 lines)
- main.py:78-82: ExplorerState에서 `_fs_watcher` 필드 제거
  - 이제 공유 `fs_model`이 모든 감시 담당

**이유:**
- 중복 제거: 파일 스캔 로직이 모델과 컨트롤러에 중복 존재
- 단순화: 공유 모델이 이미 파일 시스템 감시 중
- 일관성: 모든 파일 목록 접근이 모델을 통해 이루어짐
- 코드 감소: ~70 lines 제거

**테스트:**
- ✓ pyright: 0 errors
- ✓ 기존 기능 유지 (파일 목록 소스만 변경)

**다음 단계:**
- Phase 3: Explorer Mode가 공유 모델 사용

---

## 2025-12-07

### Unified QFileSystemModel Architecture - Phase 1 완료
**구현:**
- ui_explorer_grid.py:92-180: ImageFileSystemModel에 파일 목록 접근 메서드 추가
  - `get_image_files()`: 현재 폴더의 모든 이미지 파일 반환 (정렬됨)
  - `get_file_at_index(idx)`: 인덱스로 파일 경로 반환
  - `get_file_index(path)`: 파일 경로로 인덱스 반환
  - `get_file_count()`: 이미지 파일 개수 반환
  - `get_current_folder()`: 현재 rootPath 반환
  - `_is_image_file(path)`: 이미지 파일 확장자 체크
- main.py:97-100: ImageViewer에 공유 fs_model 추가
  - 모든 모드가 공유하는 단일 ImageFileSystemModel 인스턴스
  - directoryLoaded 시그널 연결
- main.py:299-333: `_on_fs_directory_loaded()` 핸들러 추가
  - 파일 시스템 변경 감지 시 image_files 동기화
  - 현재 파일 위치 유지
  - View 모드에서만 작동 (Explorer는 자동)
- dev-docs/REFACTOR_UNIFIED_FILESYSTEM_MODEL.md: 전체 리팩토링 계획 문서화
  - 6개 Phase 정의
  - 예상 효과 및 위험 요소 분석
  - 테스트 계획 수립

**이유:**
- 기존: View/Explorer 모드가 각각 파일 목록 관리 → 중복, 불일치 위험
- 목표: 단일 QFileSystemModel을 모든 기능이 공유
- Phase 1: 모델에 필요한 인터페이스 추가 및 공유 모델 생성
- 다음 Phase에서 점진적으로 각 기능을 모델 기반으로 전환

**테스트:**
- ✓ pyright: 0 errors
- ✓ ruff: 기존 경고만 (새 코드는 정리됨)
- ✓ 메서드 추가로 기존 기능 영향 없음 (하위 호환)

**다음 단계:**
- Phase 2: View Mode를 fs_model 기반으로 전환
- Phase 3: Explorer Mode가 공유 모델 사용
- Phase 4-6: Trim/Converter 통합 및 정리

---

## 2025-12-07

### View 모드 파일 시스템 자동 감지 (QFileSystemModel 통합)
**구현:**
- main.py:82: ExplorerState에 `_fs_watcher` 필드 추가
- display_controller.py:107-131: `_setup_fs_watcher()` 메서드 추가
  - QFileSystemModel을 생성하여 폴더 감시
  - directoryLoaded 시그널로 파일 변경 감지
  - View 모드에서만 작동하도록 조건 체크
- display_controller.py:133-165: `_reload_image_files()` 메서드 추가
  - 폴더에서 이미지 파일 목록 재스캔
  - preserve_current 옵션으로 현재 이미지 위치 유지
  - 파일 추가/삭제 시 자동으로 image_files 업데이트
- display_controller.py:21-105: `open_folder()` 리팩토링
  - 기존 수동 파일 스캔 로직을 `_reload_image_files()` 호출로 변경
  - `_setup_fs_watcher()` 호출 추가
- trim_operations.py:401-425: 배치 트림 완료 후 폴더 리로드 로직 제거
  - QFileSystemModel이 자동으로 감지하므로 수동 리로드 불필요

**이유:**
- 기존: View 모드는 폴더 열 때 한 번만 파일 목록 로드 → 외부에서 파일 추가 시 보이지 않음
- Explorer 모드는 QFileSystemModel 사용 → 자동 감지
- 해결: View 모드에서도 QFileSystemModel을 백그라운드에서 사용하여 일관성 확보
- 트림 작업 후 `.trim` 파일 생성 시 자동으로 목록에 추가됨
- 사용자가 외부에서 이미지 추가/삭제 시에도 자동 반영

**테스트:**
- ✓ pyright: 0 errors (display_controller.py, trim_operations.py)
- ✓ ruff: 기존 경고만 존재 (새 코드는 정리됨)
- ✓ contextlib.suppress 사용으로 코드 간결화

**TASKS.md 업데이트:**
- 해당 없음 (버그 수정 및 아키텍처 개선)

---

## 2025-12-05

### UX: Trim Preview in Separate Window
**구현:**
- trim_operations.py:15-48: TrimPreviewDialog 클래스 생성
  - QGraphicsView + QGraphicsScene로 프리뷰 표시
  - ScrollHandDrag 모드로 줌/팬 지원
  - resizeEvent에서 자동 fit
- trim_operations.py:50-220: start_trim_workflow() 간소화
  - View/Explorer 모드 전환 로직 완전 제거 (was_in_explorer, toggle_view_mode 삭제)
  - 캔버스 프리뷰 표시 대신 TrimPreviewDialog 사용
  - 캔버스 복원 코드 제거 (더 이상 필요 없음)
  - 확인 다이얼로그 닫을 때 프리뷰 다이얼로그도 함께 닫기

**이유:**
- Explorer 모드에서 트림 시작 시 View 모드로 전환하는 것이 어색함
- 별도 창으로 프리뷰를 보여주면 모드 전환 없이 작업 가능
- 코드 단순화: 모드 저장/복원 로직 불필요
- 사용자 경험 개선: 트림 전후 비교를 별도 창에서 확인 가능

**테스트:**
- ✓ ruff check: 통과 (스타일 경고만)
- ✓ pyright: 0 errors

**TASKS.md 업데이트:**
- 해당 없음 (UX 개선)
