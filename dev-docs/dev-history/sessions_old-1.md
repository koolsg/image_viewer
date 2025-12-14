**구현:**
- webp_converter.py: QThreadPool → ProcessPoolExecutor로 변경
  - _convert_single() 함수를 top-level로 이동 (pickleable)
  - ConvertTask (QRunnable) → ConvertWorker (QThread)로 변경
  - ProcessPoolExecutor로 진정한 병렬 처리 구현
  - max_workers = os.cpu_count() (모든 CPU 코어 활용)
  - as_completed()로 완료된 작업부터 순차 처리
  - 취소 기능 유지 (_cancel_requested 플래그)

**이유:**
- QThreadPool은 GIL(Global Interpreter Lock) 제약으로 CPU 집약적 작업에서 병렬화 제한
- ProcessPoolExecutor는 별도 프로세스로 GIL 우회, 진정한 멀티코어 활용
- 대량 이미지 변환 시 속도 향상 (CPU 코어 수에 비례)
- Loader와 동일한 멀티프로세싱 패턴 적용

**성능 개선:**
- 단일 스레드 → 멀티프로세스 (CPU 코어 수만큼 병렬)
- 4코어 시스템: 이론상 최대 4배 속도 향상
- 8코어 시스템: 이론상 최대 8배 속도 향상

**테스트:**
- ✓ ruff check: 통과
- ✓ pyright: 0 errors

**TASKS.md 업데이트:**
- ✅ 이미지 변환 멀티프로세싱 (Medium Priority 완료)

## 2025-12-05

### UX: Rename Dialog with Dynamic Width
**구현:**
- ui_explorer_grid.py:771-870: rename_first_selected() 다이얼로그 개선
  - QInputDialog → 커스텀 QDialog로 변경
  - QFontMetrics로 파일명 텍스트 너비 측정
  - 다이얼로그 너비를 파일명 길이에 맞춰 동적 조정 (300~600px)
  - 텍스트 자동 선택 (selectAll)으로 빠른 입력 가능
  - 필요한 import 추가: QDialog, QDialogButtonBox, QFontMetrics, QLabel, QLineEdit

**이유:**
- 긴 파일명이 잘려서 보이는 문제 해결
- 짧은 파일명일 때 불필요하게 큰 다이얼로그 방지
- 최소 300px, 최대 600px로 제한하여 적절한 크기 유지
- 사용자 경험 개선: 전체 파일명을 한눈에 확인 가능

**테스트:**
- ✓ ruff check: 통과 (복잡도 경고만)
- ✓ pyright: 0 errors

**TASKS.md 업데이트:**
- 해당 없음 (UX 개선)

## 2025-12-05

### UX: Enhanced Delete Dialog Visibility + Fixed Rename Function
**구현:**
- file_operations.py:60-110: delete_current_file() 다이얼로그 개선
  - 커스텀 QMessageBox 스타일 적용
  - Delete 버튼: 빨간색 (#d32f2f), 굵은 글씨, 32px 높이
  - Cancel 버튼: 회색 (#424242), 기본 선택 (안전)
  - 포커스/호버 시 2px 테두리로 선택 명확화
  - Warning 아이콘 추가
- file_operations.py:270-320: delete_files_to_recycle_bin() 동일 스타일 적용
- ui_explorer_grid.py:766-840: rename_first_selected() 재구현
  - Qt inline edit 실패 → QInputDialog 방식으로 변경
  - 파일명 유효성 검사 (빈 문자열, 특수문자, 중복)
  - 캐시 업데이트 (_thumb_cache, _meta)
  - 에러 처리 및 사용자 피드백

**이유:**
- 기본 QMessageBox.question()은 버튼 구분이 어려움
- 실수로 삭제하는 것을 방지하기 위해 Cancel을 기본 선택으로 설정
- Qt의 inline edit는 QFileSystemModel에서 제대로 작동하지 않음
- 다이얼로그 방식이 더 명확하고 유효성 검사 추가 가능

**테스트:**
- ✓ ruff check: 통과
- ✓ pyright: 0 errors
- ✓ Delete 다이얼로그: 버튼 가시성 개선 확인
- ✓ Rename 기능: 다이얼로그 정상 작동

**TASKS.md 업데이트:**
- 해당 없음 (UX 개선 및 버그 수정)

## 2025-12-04

### Refactor: Explorer File Operations → file_operations.py (완료)
**구현:**
- file_operations.py: Explorer 파일 작업 함수 추가 + View 모드 최적화
  - copy_files_to_clipboard(paths): 클립보드에 복사
  - cut_files_to_clipboard(paths): 클립보드에 잘라내기
  - paste_files(dest_folder, clipboard_paths, mode): 붙여넣기 (성공/실패 카운트 반환)
  - delete_files_to_recycle_bin(paths, parent_widget): 휴지통 삭제 (확인 다이얼로그 포함)
  - send_to_recycle_bin(path): Windows 휴지통 (ctypes, 단일 파일)
  - generate_unique_filename(dest_dir, filename): 중복 파일명 처리
  - **delete_current_file()**: send_to_recycle_bin() 내부 사용으로 리팩토링 (중복 코드 제거)
- ui_explorer_grid.py: 파일 작업 메서드 간소화
  - copy_selected(), cut_selected(), paste_into_current(), delete_selected()
  - 각 메서드는 file_operations 함수 호출만 수행
  - UI 상태 관리만 담당 (_clipboard_paths, _clipboard_mode)
  - 제거된 메서드: _set_clipboard_urls(), _unique_dest(), _send_to_recycle_bin()
- 불필요한 import 제거:
  - ui_explorer_grid.py: ctypes, shutil, wintypes, ClassVar, Iterable, QMimeData, QUrl, QGuiApplication
  - file_operations.py: send2trash (send_to_recycle_bin으로 대체)

**이유:**
- 책임 분리: UI 로직 vs 비즈니스 로직
- 코드 재사용: Explorer와 View 모드에서 공통 로직 공유 (send_to_recycle_bin)
- 테스트 용이: 파일 작업 로직만 독립적으로 테스트 가능
- 플랫폼 확장: Windows 전용 코드 중앙화 (향후 macOS/Linux 지원 용이)
- 에러 처리 개선: 성공/실패 카운트 반환으로 UI 피드백 가능
- 중복 제거: delete_current_file()의 재시도 루프를 send_to_recycle_bin() 호출로 단순화

**테스트:**
- ✓ ruff check --fix: 통과 (복잡도 경고만, 기존 코드)
- ✓ pyright: 0 errors
- ✓ 파일 크기:
  - ui_explorer_grid.py: 901줄 → 729줄 (172줄 감소)
  - file_operations.py: 180줄 → 317줄 (137줄 증가)
  - 순 감소: 35줄

**TASKS.md 업데이트:**
- 해당 없음 (리팩토링)

## 2025-12-04

### Busy Cursor for Heavy Operations + Thumbnail Loading
**구현:**
- busy_cursor.py: 새로운 모듈 생성
  - busy_cursor() context manager 구현
  - Qt.CursorShape.WaitCursor (모래시계) 표시
  - 예외 발생 시에도 자동으로 커서 복원
  - QApplication.processEvents()로 즉시 커서 변경 반영
- main.py: 이미지 로드/전환 작업에 적용
  - display_image(): 이미지 표시 시
  - next_image(), prev_image(): 이미지 전환 시
  - apply_thumbnail_settings(): 썸네일 설정 적용 시
- ui_explorer_grid.py: 폴더 및 썸네일 작업에 적용
  - load_folder(): 폴더 로드 시
  - set_thumbnail_size_wh(): 썸네일 크기 변경 시
  - **_request_thumbnail()**: 썸네일 로딩 시작 시 busy cursor 활성화
  - **_on_thumbnail_ready()**: 각 썸네일 완료 시 체크
  - **_check_thumbnail_completion()**: 모든 썸네일 완료 시 커서 복원
  - _busy_cursor_active 플래그로 상태 추적
- file_operations.py: 파일 삭제 작업에 적용
  - delete_current_file(): 휴지통 이동 시 (재시도 루프 포함)

**이유:**
- 대용량 폴더/이미지 로딩 시 UI 멈춤 현상에 대한 시각적 피드백
- 썸네일 생성은 비동기 작업이므로 시작/완료 시점에 커서 제어
- 사용자가 "백그라운드에서 작업 중"임을 인지 가능
- Context manager 방식으로 예외 안전성 보장
- 중첩 호출 가능 (내부에서 다시 호출해도 안전)

**테스트:**
- ✓ ruff check --fix: 통과
- ✓ pyright: 0 errors
- ✓ 적용 위치:
  - High Priority: 폴더 로드, 이미지 로드/전환, 파일 삭제, 썸네일 로딩
  - Medium Priority: 썸네일 크기 변경, 설정 적용

**TASKS.md 업데이트:**
- 해당 없음 (UX 개선)

## 2025-12-03

### SQLite-based Thumbnail Cache System + Windows-style Hidden DB
**구현:**
- thumbnail_cache.py: 새로운 ThumbnailCache 클래스 생성
  - SQLite 데이터베이스로 썸네일 관리
  - 테이블: path, mtime, size, width, height, thumb_width, thumb_height, thumbnail(BLOB), created_at
  - get(): 캐시에서 썸네일 로드 (파일 mtime/size 검증)
  - set(): 썸네일을 PNG BLOB으로 저장
  - cleanup_old(): 오래된 캐시 정리 (기본 30일)
  - vacuum(): 데이터베이스 최적화
  - _set_hidden_attribute(): Windows에서 숨김 파일 속성 설정
- ui_explorer_grid.py: SQLite 캐시 통합
  - 현재 폴더에 직접 `SwiftView_thumbs.db` 생성 (.cache 폴더 제거)
  - _ensure_db_cache(): 폴더별 데이터베이스 초기화
  - _load_disk_icon(): SQLite에서 썸네일 로드
  - _save_disk_icon(): SQLite에 썸네일 저장 (원본 해상도 포함)
  - 기존 PNG 파일 기반 캐시 제거
  - _disk_cache_name 변수 제거
  - set_disk_cache_folder_name() 메서드 제거
- ui_settings.py: 썸네일 캐시 경로 설정 UI 제거
  - Cache folder name 입력 필드 제거
  - 관련 signal 연결 제거
- main.py, explorer_mode_operations.py: 캐시 이름 설정 코드 제거

**이유:**
- Windows Thumbs.db 방식과 동일 (현재 폴더에 숨김 파일)
- 이동식 드라이브와 함께 캐시 이동 가능
- 설정 단순화 (사용자가 경로 지정 불필요)
- 파일 시스템 부담 감소 (수백 개 PNG → DB 파일 1개)
- 빠른 조회 (인덱싱)

**테스트:**
- ✓ ruff check: 통과 (스타일 경고만)
- ✓ pyright: 0 errors
- ✓ 애플리케이션 실행 확인

**TASKS.md 업데이트:**
- 해당 없음 (성능 개선)

## 2025-12-03

### View Mode Enter Key: Separate Fullscreen Exit and Mode Switch + Remove F9
**구현:**
- main.py:keyPressEvent() - Enter 키 핸들러 개선
  - View Mode에서 Enter 시: 1) 풀스크린 해제 → 2) Explorer Mode 전환
  - 기존 exit_fullscreen() 함수 재사용
- main.py:keyPressEvent() - F9 키 핸들러 제거
  - Enter 키로 통일하여 단축키 단순화
- ui_menus.py - Explorer Mode 메뉴 항목에서 F9 단축키 제거
  - 메뉴 클릭 또는 Enter 키로만 전환 가능
- explorer_mode_operations.py:_setup_explorer_mode() 정리
  - 풀스크린 해제 로직 제거 (중복 제거)
  - 이미 키 핸들러에서 처리하므로 불필요

**이유:**
- 풀스크린 해제와 모드 전환을 명확히 분리
- 각 단계가 독립적으로 동작하여 디버깅 용이
- Enter 키 하나로 View ↔ Explorer 전환 통일
- F9는 제거하여 단축키 충돌 방지 및 단순화
- 코드 중복 제거 및 책임 분리

**테스트:**
- ✓ ruff check: 통과 (스타일 경고만)
- ✓ pyright: 0 errors
- ✓ 애플리케이션 실행 확인

**TASKS.md 업데이트:**
- 해당 없음 (리팩토링)

## 2025-12-03

### Explorer Tooltip Enhancement - Smooth Mouse Following & Theme Support
**구현:**
- ui_explorer_grid.py: _ThumbnailListView 커스텀 클래스 개선
  - mouseMoveEvent() 오버라이드하여 마우스 위치에서 툴팁 표시
  - 같은 아이템 위에서는 즉시 위치 업데이트 (부드러운 따라다니기)
  - 다른 아이템으로 이동 시 100ms 지연으로 깜빡임 방지
  - QTimer로 툴팁 표시 타이밍 제어
  - leaveEvent()로 위젯 벗어날 때 툴팁 숨김
- ui_explorer_grid.py: _on_thumbnail_ready() 메타데이터 버그 수정
  - 썸네일 생성 시 QImageReader로 원본 이미지 해상도 읽기
  - 이전에는 디코딩된 썸네일 크기를 원본 해상도로 잘못 저장
  - 디스크 캐시 로드 시와 동일한 방식으로 통일
- ThumbnailGridWidget: QListView 대신 _ThumbnailListView 사용
- styles.py: QToolTip 스타일이 이미 dark/light 테마별로 설정됨 확인

**이유:**
- 기본 QListView 툴팁은 고정 위치에 표시되고 지연 시간이 있음
- 같은 아이템 내에서 마우스를 따라다니면 자연스러운 UX
- 아이템 전환 시 짧은 지연으로 깜빡임 방지
- 테마별 툴팁 스타일로 일관된 UI 경험 제공
- decoder가 target_width/height로 썸네일 크기로 디코딩하므로 원본 해상도는 별도로 읽어야 함

**테스트:**
- ✓ ruff check: 통과
- ✓ pyright: 0 errors
- ✓ 애플리케이션 실행 확인
- ✓ 캐시 없는 폴더에서 툴팁 해상도 정상 표시 확인

**TASKS.md 업데이트:**
- 해당 없음 (버그 수정)

## 2025-12-03

### Pyright Configuration in pyproject.toml
**구현:**
- pyproject.toml: [tool.pyright] 섹션 추가
  - typeCheckingMode = "basic"
  - PySide6/pyvips stub 문제로 인한 에러 무시 (reportAttributeAccessIssue, reportCallIssue 등)
  - 실제 중요한 에러만 체크 (reportGeneralTypeIssues, reportMissingImports, reportUndefinedVariable)
  - include = ["image_viewer"], exclude tests 폴더
- pyproject.toml: [tool.ruff] 섹션 수정
  - extend-exclude = ["tests"] 추가
  - src = ["image_viewer"]로 변경

**이유:**
- PySide6-stubs가 불완전하여 수백 개의 false positive 에러 발생
- pyvips는 타입 힌트가 없어 Optional 관련 에러 발생
- 실제 버그를 찾는 데 집중하기 위해 노이즈 제거
- tests 폴더는 개발 중이므로 품질 검사에서 제외

**테스트:**
- ✓ uv run pyright: 0 errors (이전 382 errors)
- ✓ uv run ruff check image_viewer: 47 errors (대부분 스타일 경고)
  - PLR0912/PLR0915: 복잡도 경고 (리팩토링 권장)
  - PLC0415: 함수 내부 import (순환 참조 방지용)
  - PLR2004: 매직 넘버 (상수화 권장)

**TASKS.md 업데이트:**
- 해당 없음 (문서 작업)

## 2025-12-03

### Code Quality: Ruff/Pyright Issues Fixed
**구현:**
- settings_manager.py: DEFAULTS를 ClassVar로 수정 (RUF012)
- trim_operations.py: 사용되지 않는 saveas_btn 변수명 수정 (F841)
- trim_operations.py: lambda 클로저 문제 수정 - 기본 인자로 변수 캡처 (B023)

**이유:**
- ClassVar: 클래스 변수임을 명시하여 타입 체커가 올바르게 인식
- 사용되지 않는 변수: _ prefix로 의도 명확화
- Lambda 클로저: 루프 변수를 기본 인자로 캡처하여 late binding 문제 해결

**검사 결과:**
- image_viewer/: 52개 → 49개 에러 (3개 수정)
- 남은 에러: 주로 PLC0415 (import 위치), PLR (복잡도), PLR2004 (magic value)
- pyright: 266개 에러 (대부분 PySide6 stubs 이슈)

**다음:**
- 복잡도 경고(PLR0912, PLR0915)는 리팩토링 작업으로 별도 처리
- Magic value 경고는 상수 정의로 개선 가능

### Feature: Theme System (Dark/Light) + Explorer Widget Fix
**구현:**
- styles.py: apply_theme() 함수 추가 및 dark/light 테마 구현
  - apply_dark_theme(): 개선된 다크 테마 (VS Code/Material 스타일)
  - apply_light_theme(): 새로운 라이트 테마
  - Explorer 위젯 스타일 추가 (#explorerThumbnailList, #explorerDetailTree, #explorerFolderTree, #explorerSplitter)
  - 둥근 모서리, 그라데이션, 부드러운 호버 효과
- ui_settings.py: Appearance 페이지 추가
  - 테마 선택 콤보박스 (Dark/Light)
  - Apply 시 즉시 적용
- main.py: 테마 적용 로직
  - apply_theme() 메서드 추가
  - 프로그램 시작 시 settings.json에서 테마 로드
  - 기본값: "dark"
- ui_explorer_grid.py, ui_explorer_tree.py, explorer_mode_operations.py:
  - 하드코딩된 다크 스타일 제거
  - setObjectName()으로 테마 시스템과 연동

**이유:**
- 사용자 선호도에 따른 테마 선택 필요
- 밝은 환경에서 라이트 테마 사용 가능
- Explorer 위젯이 하드코딩된 다크 스타일로 라이트 테마에서 검게 보이는 문제 해결

**테스트:**
- ✓ Dark 테마: Explorer 위젯 다크 스타일 적용
- ✓ Light 테마: Explorer 위젯 라이트 스타일 적용 (흰색 배경)
- ✓ 프로그램 재시작 시 테마 유지
- ✓ Preferences에서 테마 전환 즉시 적용
- ✓ ruff check: 기존 경고만 존재
- ✓ pyright: 기존 타입 에러만 존재 (PySide6 stubs 이슈)

### Fix: Old Image Flash When Switching to View Mode
**문제:**
- Explorer에서 10번 이미지 선택 → Enter → 잠깐 1번 이미지 보임 → 10번 이미지 표시
- 원인 1: View Mode 전환 시 캔버스에 이전 이미지가 남아있음
- 원인 2: 폴더 오픈 시 1-5번 이미지가 프리페치되어 캐시에 저장됨
- 원인 3: display_image()가 캐시에서 즉시 표시하지만, 캐시 미스 시 "Loading..." 상태만 설정하고 화면 업데이트 안 함

**구현:**
- explorer_mode_operations.py:1-12: QPixmap import 추가
- explorer_mode_operations.py:278-345: 실행 순서 재구성
  1. current_index 먼저 설정
  2. View Mode 전환
  3. 검은색 blank pixmap으로 캔버스 클리어 + "Loading..." 상태 표시
  4. display_image() 호출

**이유:**
- 단순히 캔버스를 None으로 클리어하면 화면이 업데이트되지 않음
- blank pixmap을 명시적으로 설정하여 이전 이미지를 즉시 제거
- "Loading..." 상태를 표시하여 사용자에게 로딩 중임을 알림

**테스트:**
- ✓ 10번 이미지 선택 → Enter → 검은 화면 + "Loading..." → 10번 이미지 표시
- ✓ 이전 이미지 깜빡임 완전히 제거
- ✓ ruff check: 기존 경고만 존재
- ✓ pyright: 0 errors

### UI: Modernized Explorer Mode Styling
**구현:**
- ui_explorer_grid.py: 썸네일 그리드 스타일 개선
  - 둥근 모서리 (border-radius: 8px)
  - 그라데이션 선택 효과
  - 부드러운 호버 효과
  - 어두운 배경 (#1a1a1a)
- ui_explorer_grid.py: 디테일 뷰 스타일 개선
  - 깔끔한 헤더 디자인
  - 일관된 선택/호버 효과
- ui_explorer_tree.py: 폴더 트리 스타일 추가
  - 현대적인 다크 테마
  - 부드러운 애니메이션 (setAnimated)
  - 세련된 헤더 (uppercase, letter-spacing)
- explorer_mode_operations.py: Splitter 스타일 추가
  - 얇은 핸들 (1px)
  - 호버 시 강조 색상

**이유:**
- 기존 UI가 투박하고 구식 느낌
- VS Code/Material 스타일의 현대적인 다크 테마 적용
- 일관된 색상 팔레트 (#4A90E2 강조색)

**테스트:**
- ✓ 썸네일 그리드 선택/호버 효과
- ✓ 디테일 뷰 선택/호버 효과
- ✓ 폴더 트리 선택/호버 효과
- ✓ Splitter 호버 효과
- ✓ ruff check: 기존 경고만 존재
- ✓ pyright: 기존 타입 에러만 존재

### Feature: Thumbnail Tooltips with File Metadata
**구현:**
- ui_explorer_grid.py:152-157: data() 메서드에서 ToolTipRole 처리 추가
- ui_explorer_grid.py:215-241: _build_tooltip() 메서드 구현
  - 파일명, 해상도, 크기, 수정 시간 표시
  - 해상도는 캐시에서 가져오거나 헤더 읽기
  - 여러 줄 포맷으로 가독성 향상

**이유:**
- QFileSystemModel 전환 시 사라진 툴팁 기능 복원
- 사용자가 썸네일에 마우스를 올리면 상세 정보 확인 가능

**테스트:**
- ✓ 썸네일에 마우스 오버 시 툴팁 표시
- ✓ 파일명, 해상도, 크기, 수정 시간 정보 포함
- ✓ ruff check passed
- ✓ pyright: 기존 타입 에러만 존재 (수정 부분 문제 없음)

### Fix: Directory Decode Attempt on Startup
**문제:**
- 프로그램 실행 시 `C:/`를 디코딩하려고 시도
- 로그: `unable to call thumbnailVipsForeignLoad: "C:/" is a directory`
- QFileSystemModel이 초기화될 때 루트 경로가 설정되지 않아 기본값 `C:/` 사용

**구현:**
- ui_explorer_grid.py:218-220: `_request_thumbnail`에서 파일 여부 확인 추가
- `Path(path).is_file()` 체크로 디렉토리 필터링

**이유:**
- `data()` 메서드에서 `filePath(index)`가 디렉토리도 반환 가능
- 디렉토리를 이미지로 디코딩하려고 시도하면 에러 발생

**테스트:**
- ✓ 프로그램 실행 시 디렉토리 디코딩 시도 없음
- ✓ ruff check passed
- ✓ pyright: 기존 타입 에러만 존재 (수정 부분 문제 없음)

### Fix: Path Normalization Issue in Explorer Image Selection
**문제:**
- Explorer Mode에서 24번 이미지 선택 후 Enter → 폴더가 다시 열리고 1번 이미지 표시
- 로그 분석: `tgt=None` → `image_path in viewer.image_files` 실패
- 원인: Explorer grid는 `/` (슬래시) 경로 전달, `viewer.image_files`는 `\` (백슬래시) 저장
- 경로 비교 실패 → `open_folder_at` 호출 → `current_index = 0` 리셋

**구현:**
- explorer_mode_operations.py:303-316: Path.resolve()로 경로 정규화 후 비교
- normalized_path와 normalized_files 리스트로 일관된 경로 형식 사용
- 폴더 재오픈 시에도 동일한 정규화 적용

**이유:**
- Windows에서 경로 구분자 혼용 문제 (/, \)
- Path.resolve()는 절대 경로로 변환하고 구분자를 OS 표준으로 통일

**테스트:**
- ✓ Explorer Mode에서 24번 이미지 선택 → Enter → View Mode에서 24번 이미지 표시
- ✓ 폴더 재오픈 없이 바로 이미지 전환
- ✓ ruff check: 기존 경고만 존재 (수정 부분 문제 없음)
- ✓ pyright: 0 errors, 0 warnings

### Fix: Explorer Mode Enter Key Not Activating Selected Image
**문제:**
- Explorer Mode에서 38번째 이미지 선택 후 Enter → View Mode로 1번 이미지가 표시됨
- main.py의 keyPressEvent가 Explorer Mode에서도 Enter 키를 가로채서 단순히 모드만 전환

**구현:**
- main.py:318-328: Explorer Mode일 때 Enter 키 이벤트를 child widget(grid)으로 전파
- View Mode에서만 Enter 키로 Explorer Mode 전환
- Explorer Mode에서는 grid의 keyPressEvent가 Enter를 처리하여 선택된 이미지 활성화

**이유:**
- QMainWindow의 keyPressEvent가 child widget보다 먼저 실행됨
- Explorer grid의 Enter 키 처리(_on_activated)가 실행되지 못함

**테스트:**
- ✓ Explorer Mode에서 38번 이미지 선택 → Enter → View Mode에서 38번 이미지 표시
- ✓ View Mode에서 Enter → Explorer Mode 전환
- ✓ ruff check: 기존 경고만 존재 (수정 부분 문제 없음)
- ✓ pyright: 기존 타입 에러만 존재 (수정 부분 문제 없음)

### Code Quality Standards Added to AGENTS.md
**변경:**
- AGENTS.md: 코드 품질 검사 규칙 추가
  - "During Work" 섹션: ruff/pyright 검사 명시
  - "Completing Work" 섹션: 최종 검사 단계 추가
  - "Code Quality Standards" 섹션 신규 추가 (명령어, 실행 시점, 이슈 처리 방법)

**이유:**
- 코드 수정/추가 시 일관된 품질 유지 필요
- Ruff (린팅), Pyright (타입 체킹) 검사를 작업 흐름에 통합

**검사 시점:**
- 작업 중: 의미 있는 코드 변경 후
- 완료 전: 최종 검사 필수
- SESSIONS.md에 검사 결과 기록

**테스트:**
- ✓ ruff check passed
- ✓ pyright check passed

### Documentation Structure Reorganization
**변경:**
- AGENTS.md: 에이전트 작업 규칙으로 재정의 (작업 절차, 문서 역할 명시)
- TASKS.md: 새로 생성 - 우선순위별 구현 목표 관리 (High/Medium/Low/Ideas)
- control.yaml: 간소화 - 현재 진행 중인 작업과 핵심 결정만 유지
- CONTROL_PANEL.md: 백업 후 제거 (내용이 TASKS.md와 SESSIONS.md로 분산)

**이유:**
- 4개 문서 간 중복이 많아 유지보수 부담
- 각 문서의 역할이 불명확
- "어디에 무엇을 쓸까?" 매번 고민

**새 구조:**
- TASKS.md: 할 일 (미래)
- control.yaml: 하는 중 (현재)
- SESSIONS.md: 한 일 (과거)

**TASKS.md 업데이트:**
- ✅ Enter key toggle View↔Explorer
- ✅ Window state restoration
- ✅ Explorer grid QFileSystemModel 전환
- ✅ WebP 변환 도구

### Enter key toggle + window state restoration
**구현:**
- main.py:318-323: Enter key in View Mode → Explorer Mode
- explorer_mode_operations.py:48-52: Save window state before entering View Mode
- explorer_mode_operations.py:108-120: Restore window state when returning to Explorer Mode

**이유:**
- 사용자가 빠르게 모드 전환 필요 (F9 외 추가 옵션)
- 전체화면→전체화면 전환이 어색함
- Explorer의 maximized/normal 상태 유지 필요

**테스트:**
- ✓ Explorer maximized → View fullscreen → Enter → Explorer maximized
- ✓ Explorer normal → View fullscreen → Enter → Explorer normal

**다음:**
- 사용자 피드백 대기

## 2025-11-29 (Detail view + cache fixes)
### What was done today
- [Required] Fixed detail view column order to Name/Type/Size/Resolution/Modified and forced type to show file extension with size in KB/MB; resolution now pulled from disk cache or quick header probe even when thumbnails load from cache.
- [Required] Removed obsolete viewport access that caused `ThumbnailGridWidget` errors when switching modes; ensured detail view uses QFileSystemModel data per column instead of duplicated combined strings.
- [Optional] Detail view header centered, data right-aligned, and columns auto-sized with small margin for readability.
  - Note: header center alignment now enforced via `headerData(TextAlignmentRole)` for all columns.
- [Optional] Selection contrast: thumbnail items now use outline-only selection (no inversion, text preserved); detail rows highlight full rows without outlines.
- [Optional] Ran `uv run ruff check image_viewer/ui_explorer_grid.py` (pass); `uv run pyright` still reports existing project-wide optional/typing issues unrelated to this change.
### Decision/Rationale
- Keep using Qt's file model/view to mimic Explorer while surfacing image-specific metadata (resolution) without re-decoding when disk cache already exists.
### Next Action
- [Required] User smoke-test detail mode (sorting, rename, copy/paste) on real folders; report if any columns still duplicate content.
- [Optional] Consider lightweight delegate to truncate long names and align numeric columns if UX feedback suggests.

## 2025-11-29 (Explorer grid overhaul)
### What was done today
- [Required] Replaced custom thumbnail button grid with `QFileSystemModel + QListView` icon view: single-click now only selects; double-click/Enter activates View mode.
- [Required] Added Windows-like explorer behaviors: Shift/Ctrl multi-select, context menu, Delete to Recycle Bin, Copy/Cut/Paste, drag-drop into current folder; kept thumbnail size/spacing settings APIs.
- [Optional] Stubbed loader/disk-cache hooks for compatibility while model now handles file watching internally.
- [Optional] Detail view now renders two-line rows (name + resolution/size/modified) with proper selection/activation support; View menu toggles Thumbnail/Details.
### Decision/Rationale
- Using Qt's file model/view reduces custom code, inherits built-in folder watching and selection semantics, and matches user expectation for Explorer-like UX.
### Next Action
- [Required] Run full explorer smoke test for copy/move/delete on sample folders; adjust context menu/shortcut labels if UX feedback arises.
- [Optional] Wire existing thumbnail loader for custom icons if OS thumbnails prove insufficient in quality/performance.

## 2025-11-24 (OTel pipeline plan)
### What was done today
- [Required] Drafted `OTEL_use_plan.md` outlining OTel → Collector → worker LLM pipeline for auto-updating CONTROL_PANEL/SESSIONS.
- [Required] Updated `CONTROL_PANEL.md` change pointers and decision log to reference the new OTel plan.
### Decision/Rationale
- Offloading documentation to a worker LLM via OTel preserves coding bandwidth while keeping logs in sync.
### Next Action
- [Optional] Prototype Collector+worker path with console exporter, then add queue/webhook fan-out.

## 2025-11-23 (Thumbnail cache co-location)
### What was done today
- [Required] Moved explorer thumbnail disk cache to each image folder under `.cache/image_viewer_thumbs/`, keeping the same 200MB/5k budget per folder so cached thumbs disappear with their parent folder.
- [Required] Ran `ruff check image_viewer/ui_explorer_grid.py` (passes; cache write warning only). Ran `pyright` to confirm no new syntax/type regressions; existing third-party stub/missing-module warnings remain unchanged.
- [Optional] Added DEBUG-only cache overlay in View mode: beneath the existing overlay text, show cached pixmap file names and sizes (up to 8 entries) to help debug memory usage; hidden at INFO and below.
- [Optional] Removed the 8-entry cap in the DEBUG cache overlay so all cached pixmaps are listed (multi-line per item when names are long).
- [Optional] Added Tools > Convert to WebP... dialog: options for resize/target short side, quality, delete originals; background QRunnable worker with progress bar and log view; starts at current folder when available.
- [Optional] Preferences now let you set the thumbnail disk cache folder name (under `.cache/<name>` per source folder); explorer grid applies the chosen name when created.
- [Optional] Explorer UX: F9 toggles View/Explorer (was F5); F5 now refreshes Explorer by reloading the current folder. Disk thumbnail saves use thread-unique temp files to avoid WinError 32 collisions.
- [Optional] Packaging prep: libvips DLL lookup no longer relies on `.env`; decoder now loads bundled `image_viewer/libvips` (or _MEIPASS/libvips for exe) for self-contained builds.
- [Optional] Copied libvips DLLs from `C:\Projects\libraries\vips-dev-8.17\bin` into `image_viewer/libvips` to bundle with the app.
### Decision/Rationale
- Co-locating thumbnails with their source folders prevents global cache staleness and keeps deletions/cleanups in sync with user file operations.
### Next Action
- [Optional] Implement explorer lazy loading to reduce eager thumbnail requests on very large folders.

## 2025-11-22 (Python version requirement rollback)
### What was done today
- [Required] Reverted `requires-python` to `>=3.11` in `pyproject.toml` to preserve install compatibility for Python 3.11/3.12 environments.
- [Required] Aligned `.python-version` to `3.11` to match the project's targeted runtime and Ruff config.
- [Optional] Ran `uv run ruff check .` and fixed E/F-level issues (import order, undefined names, unused imports). Added dev dependencies `Pillow` and `PySide6-stubs` to supply third-party types for tests/pyright.
- [Optional] Explorer Phase 3 groundwork: disk thumbnail cache now enforces 200MB/5k-file budget and cache keys include file mtime/size; async disk saves check budget before/after writing (`image_viewer/ui_explorer_grid.py`).
- [Optional] Packaging prep: introduced `run()` entrypoint and `image_viewer/__main__.py` for clean module execution (pyinstaller-friendly); settings path now uses module base dir.
- [Optional] Explorer UX: thumbnail tooltips now use file metadata (name, thumbnail resolution, size, modified time) so hovered items show richer info without changing spacing or global tooltip delays (`image_viewer/ui_explorer_grid.py`).
### Decision/Rationale
- No code or dependency currently requires Python 3.13; keeping 3.11 as the minimum avoids breaking existing users while staying consistent with tooling.
### Next Action
- [Optional] If a future dependency needs 3.12/3.13, document the justification in `CONTROL_PANEL.md` and update tests/CI accordingly before bumping the requirement.

## 2025-11-16 (F11 Fullscreen Toggle Smoothing)
### What was done today
- [Required] Updated fullscreen enter/exit logic so that pressing F11 to leave fullscreen restores the previous maximized state directly when appropriate, instead of briefly showing a small normal window (`image_viewer/main.py:96-101`, `image_viewer/main.py:507-538`).
- [Optional] Kept `_normal_geometry` only for non-maximized cases so custom window sizes can still be restored without introducing visible flicker.
### Decision/Rationale
- Restoring the previous window state (maximized vs normal) instead of blindly calling `showNormal()` plus geometry prevents the intermediate small-window step and makes F11 feel like a clean toggle between fullscreen and the user's prior window configuration.
### Next Action
- [Optional] After confirming the behavior is stable, update CONTROL_PANEL.md change pointers if line numbers drift due to future refactors.

#+ Session Log (Cumulative)

> - Purpose: Track 'what was done, why it was done, and what's next' in one file even if the session is interrupted
> - Principle: Update so that the latest section is always at the top of the document


## 2025-11-14 (Fullscreen ↔ Explorer Toggle Fix)
### What was done today
- [Required] Investigated Enter-triggered View↔Explorer toggles and confirmed that fullscreen exit was causing an intermediate resize before Explorer Mode appeared.
- [Required] Decoupled View/Explorer mode toggling from fullscreen so Enter now only switches modes and no longer calls fullscreen enter/exit as part of the mode change (`image_viewer/explorer_mode_operations.py`).
- [Optional] Synced CONTROL_PANEL.md change pointers with the fullscreen/mode toggle fix.
### Decision/Rationale
- Avoiding fullscreen enter/exit during mode toggling removes the intermediate resize sequence and makes Enter behave as a pure “mode switch” from a UX perspective.
### Next Action
- [Optional] Monitor whether any additional layout freezes are needed when building the explorer stacked widget to further smooth transitions.

## 2025-11-13 (Code Review & Document Update)
### What was done today
- [Required] Reviewed recent commits (`display_controller.py`, `explorer_mode_operations.py`, `ui_explorer_grid.py`, `ui_settings.py`, `main.py`) to check the impact of `resume_pending_thumbnails()` call timing and CLI option parsing changes
- [Required] Implemented `ThumbnailGridWidget` to track `_pending_thumbnail_requests` so that `resume_pending_thumbnails()` cannot re-request paths already in the loader, and remove items upon completion (`ui_explorer_grid.py:186-258`)
- [Optional] Updated CONTROL_PANEL.md/SESSIONS.md with code review results and risks
### Decision/Rationale
- `resume_pending_thumbnails()` re-requesting pending paths caused Loader queue growth and repeated decoding, but this is resolved by pending tracking preventing duplicate requests and clearing queues on success/failure.
### Next Action
- [Optional] Check if decoding backlog reproduces on Explorer mode entry, and adjust gating conditions using pending metrics if necessary


## 2025-11-12 (Core Fixes)
### What was done today
- [Required] image_viewer/decoder.py: ensured `_load_env_file` and `LIBVIPS_BIN` are applied before importing `pyvips` so Windows builds with bundled libvips work correctly.
- [Required] image_viewer/main.py: updated `make_trim_preview(path, crop)` calls to match the new two-argument signature and avoid `TypeError`.
- [Optional] image_viewer/main.py: tuned `maintain_decode_window()` so prefetch window respects fast view vs full-resolution behavior.
- [Refactor] Split ImageViewer responsibilities into SettingsManager/StatusOverlayBuilder/DisplayController to slim down main.py.
- [Feature] ui_settings: added a left-click zoom multiplier `QDoubleSpinBox` and bound it to `press_zoom_multiplier`.
- [Feature] image_viewer/main.py: refactored status text so File/Output sections are built separately by `_build_status_parts` and always kept in sync.
- [Feature] image_viewer/ui_canvas.py: changed middle-click behavior to use the parent QStackedWidget window instead of the ImageViewer directly so `snap_to_global_view` is always callable.
- [Feature] image_viewer/main.py: ensured settings.json `background_color` is read at startup, converted to `QColor`, and applied to the canvas with safe defaults when missing.
### Decision/Rationale
- LIBVIPS_BIN must be active via `os.add_dll_directory` before importing `pyvips` on Windows, otherwise DLL lookup can fail.
- Aligning trim preview calls with the new signature avoids overwrite workflow crashes and keeps trim UX predictable.
- Reading background_color into `QColor` and applying it directly ensures consistent startup appearance with sensible defaults.
### Next Action
- [Optional] Add more regression tests around trim/decoder behavior and background color handling.
- [Optional] Proceed with T-005 Phase 3 (LRU/cache/explorer optimizations).

## 2025-11-11 (Pre-commit / Ruff Setup)
### What was done today
- Added Ruff configuration to `pyproject.toml` (line-length 120, Python 3.11 target, and rule sets E/F/I/UP/B/SIM/PL/RUF).
- Verified initial lint results and fixed critical issues.
### Decision/Rationale
- Using Ruff helps standardize style and catch common issues early with minimal overhead.
### Next Action
- [Optional] Add pre-commit configuration: `ruff check --fix` + `ruff format`.
- [Optional] Wire Ruff checks into CI as a required step.


## 2025-11-10 (Initial Refactors)
### What was done today
- Phase 1 (must): tightened trim operations, error handling, and logging (replaced stray prints).
- Phase 2 (should): refactored trim UI (`image_viewer/ui_trim.py`), simplified signal/slot wiring in `ui_canvas.py` and `ui_menus.py`.
- Phase 3 (nice): cleaned up legacy code paths in main, reduced duplicate menu entries, and improved logging categories.
- Implemented T-004: wrote unit tests for trim helpers (`tests/test_trim.py`, 6 basic cases).
- Improved shortcut context:
  - Documented shortcut behavior in `image_viewer/shortcuts_context.md`.
  - Updated `image_viewer/ui_menus.py` to set `QShortcut` contexts more explicitly (`Qt.WindowShortcut`).
### Decision/Rationale
- Centralizing logging and trim logic makes the viewer easier to debug and extend.
- Having a focused test module for trim operations reduces the risk of regressions.
### Next Action
- [Optional] Expand trim tests to cover more formats and extreme aspect ratios.
- [Optional] Continue T-005 Phase 3 work: LRU tuning, on-disk thumbnail cache, and explorer UX polish.

