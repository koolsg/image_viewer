# Image Viewer - What to do

> 구현할 기능과 개선 사항을 우선순위별로 관리

> NOTE (2026-01-10): QML 단일 경로는 `image_viewer/ui/qml/` 입니다. 과거 문서에 남아있는 `image_viewer/qml/*` 경로는 레거시이며 제거되었습니다.

## 🔥 High Priority (다음에 할 것)

### 이미지 편집 기능
- [ ] Crop/Save 구현
  - 목표: 크롭 영역 선택 후 저장 기능
  - UI: 마우스 드래그로 영역 선택
  - 저장: 원본 유지 또는 덮어쓰기 옵션
  - 파일: ui_canvas.py, file_operations.py

### 이미지 배치 처리
- [ ] 이미지 Merge/Split 기능
  - Merge: 여러 이미지를 하나로 합치기 (세로/가로)
  - Split: 큰 이미지를 여러 조각으로 나누기
  - UI: 다이얼로그로 옵션 설정
  - 파일: 새 모듈 image_batch.py

- [ ] 간단한 회전/반전 저장
  - 현재: 뷰어에서만 회전, 저장 안 됨
  - 목표: "Save Rotated" 버튼 추가
  - 파일: file_operations.py

- [ ] Fix scroll/transform state inconsistency when switching HQ prescale/normal path in Fit mode
  - 문제: View transform/scroll offsets become inconsistent when switching decoding path (HQ prescale vs normal), causing misaligned selection/view.
  - 파일: `ui_canvas.py`, `image_viewer/image_engine/decoder.py`, `image_viewer/image_engine/strategy.py`

### QML Migration — Viewer POC (High Priority)
- [x] QML Viewer POC skeleton (T-QLM-01)
  - 목표: `ViewerPage.qml`을 `QMainWindow` 중앙에 embed 하고 `AppController` bridge를 추가하여 QML에서 이미지를 표시할 수 있음을 검증.
  - 완료 기준: QML Viewer가 이미지 표시, fit/actual, wheel zoom, drag pan의 기본 동작이 작동.
  - 작업 파일: `image_viewer/main.py`, `image_viewer/qml/ViewerPage.qml`, `image_viewer/qml_bridge.py`


- [x] QML ImageProvider & engine integration (T-QLM-02)
  - 구현: `QQuickImageProvider` 또는 QObject bridge를 통해 엔진 캐시/디코더와 연동. preview decode 요청 및 generation id로 stale discard 보장.
  - 테스트: generation discard 단위 테스트 추가.
  - 작업 파일: `image_viewer/image_engine/engine.py`, `image_viewer/qml_bridge.py`


- [ ] Fullscreen behavior validation & fix (T-QLM-03)
  - 구현: embed → detached `QQuickView` 전환 로직(윈도우 전용 fullscreen 처리 검증).
  - 테스트: Windows에서 풀스크린 전환 시 깜박임/플리커/크래시 없는지 확인.
  - 작업 파일: `image_viewer/main.py`, `image_viewer/qml/ViewerPage.qml`

- [ ] Metrics & instrumentation (T-QLM-04)
  - 구현: decode time, cache hit/miss, frame upload latency 측정 및 로그/메트릭 노출.
  - 작업 파일: `image_viewer/image_engine/metrics.py`, `image_viewer/qml_bridge.py`

- [ ] Refine flow & stale result handling (T-QLM-05)
  - 구현: preview → refine 프레임 교체, stale generation 무시, LRU frame cache 상한 적용.
  - 테스트: 빠른 전환 상황에서 오래된 프레임이 표시되지 않음.
  - 작업 파일: `image_viewer/image_engine/loader.py`, `viewer/ViewerItem`(예정)

- [ ] Acceptance tests & docs (T-QLM-06)
  - 통합 테스트(프리뷰 요청 → QML에서 이미지 수신), 풀스크린 시나리오, 메모리 회귀 테스트
  - 문서: `dev-docs/QML/QML_migration_for_view.md` 작성 및 업데이트.


### QML Viewer — Missing implementations / follow-ups (T-QLM-07)
- [ ] Implement cursor-centered press-to-zoom alignment in QML
  - 설명: `ImageCanvas._align_cursor_after_zoom`와 동일한 동작을 QML로 재현하여, press-to-zoom 후에도 '마우스 포인터 아래의 같은 픽셀이' 동일한 화면 위치에 유지되도록 조정.
  - 수용 기준: QML에서 left-press → 임시 확대 시, 마우스 포인터 위치가 줌 전/후에 동일한 이미지 픽셀을 가리킴을 자동 테스트로 검증.
  - 파일: `image_viewer/qml/ViewerPage.qml`, `image_viewer/qml_bridge.py`, `tests/test_qml_mouse_interactions.py`

- [ ] Expose and integrate HQ downscale option to the QML viewer (fit-mode prescale)
  - 설명: HQ prescale 디코드(고품질 리샘플링)를 QML 경로에서도 사용 가능하도록 AppController/engine API로 노출하고, fit 모드에서 선택 시 HQ 출력이 사용되게 함.
  - 수용 기준: QML에서 HQ 토글 후 decode 경로가 HQ로 전환되고, 뷰포트 정렬(스크롤/오프셋)이 유지되며 테스트로 검증됨. 사이즈/성능/동작 회귀 없음.
  - 파일: `image_viewer/qml/App.qml`, `image_viewer/qml/ViewerPage.qml`, `image_viewer/qml_bridge.py`, `image_viewer/image_engine/decoder.py`, `image_viewer/image_engine/strategy.py`

- [ ] Add automated test for right-drag pan in QML viewer
  - 설명: QML `MouseArea`의 right-drag 동작(패닝)이 Flickable의 contentX/Y를 적절히 변경하는지 검증하는 단위 테스트 추가.
  - 수용 기준: `qtbot` 기반 테스트에서 우클릭 드래그로 contentX/Y 변화가 발생하고, 팬 동작이 재현됨.
  - 파일: `tests/test_qml_mouse_interactions.py`


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

- [ ] 숫자 키로 줌 레벨 설정 (1=100%, 2=200%)
  - 이유: 빠른 확대/축소
  - 파일: main.py keyPressEvent



- [ ] 밝기/대비 조정
  - UI: 슬라이더 다이얼로그
  - 적용: pyvips로 실시간 프리뷰







### Decoding & Quality
- [ ] HQ Downscale quality automation: Apply BICUBIC + GaussianBlur(0.4~0.6) for heavy downscaling (scale < 0.6), Lanczos otherwise
  - 파일: `image_viewer/image_engine/decoder.py`, `image_viewer/image_engine/strategy.py`
- [ ] HQ prescale debounce: Resample only once 150~250ms after resize ends
  - 파일: `image_viewer/ui_canvas.py`, `image_viewer/image_engine/loader.py`
- [ ] Save/restore HQ toggle/filter/blur/gamma-aware options in settings.json
  - 파일: `image_viewer/settings_manager.py`, `image_viewer/ui_settings.py`
- [ ] Make prefetch window size configurable (back/ahead)
  - 파일: `image_viewer/image_engine/engine.py`, `image_viewer/main.py` (settings)
- [ ] Introduce current frame priority processing (priority queue/epoch), ignore stale results
  - 파일: `image_viewer/image_engine/loader.py`, `image_viewer/image_engine/engine.py`
- [ ] Add cursor-based zoom/pan lock option during left-click temporary zoom
  - 파일: `image_viewer/ui_canvas.py`, `image_viewer/crop/ui_crop.py`

## 🔮 Low Priority (나중에)

### [ ] LRU 캐시 메모리 제한 (현재 무제한)
  - 목표: 최대 500MB로 제한
  - 방법: OrderedDict + 메모리 추적
  - 파일: ui_explorer_grid.py

- [ ] 대용량 폴더 lazy loading
  - 문제: 1000+ 이미지 폴더에서 썸네일 요청 폭주
  - 해결: 스크롤 시 visible items만 로드
  - 파일: ui_explorer_grid.py
### 코드 리팩토링 - ui_explorer_grid.py
**현재 상태 (2025-12-05):**
- 파일 크기: 806줄 (Phase 2 완료 후)
- Phase 2 완료: 파일 작업 분리 (172줄 감소, 19%)
- 주요 클래스:
  - `ImageFileSystemModel`: ~373줄 (썸네일 + 메타데이터)
  - `ThumbnailGridWidget`: ~330줄 (메인 위젯)
  - `_ThumbnailListView`: ~63줄 (커스텀 툴팁)
  - `_ImageOnlyIconProvider`: ~10줄


- [ ] Phase 3: 메타데이터 관리 분리 (우선순위: Low)
  - 로직이 단순하여 분리 효과 미미
  - 현재 코드로 충분히 관리 가능

- [ ] HQ path: Add viewport alignment (1:1 placement) option and code separation
  - 파일: `image_viewer/ui_canvas.py`, `image_viewer/image_engine/decoder.py`
- [ ] Modularize loader/sliding window logic (maintain_decode_window → util)
  - 파일: `image_viewer/image_engine/loader.py`, `image_viewer/image_engine/engine.py`

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

## ✅ Recently Completed (간소화)

- 2025-12-17: Cleanup & Viewer improvements
  - Removed legacy compatibility shims and updated migration/imports.
  - Implemented hover drawer menu (Crop) and integrated with the canvas.

- Early December: Engine & UI work
  - Reworked Explorer to use engine-thread scanning with ThumbDB-backed thumbnail cache.
  - Added WebP conversion worker, rename dialog sizing, busy cursor, and file operation refactors.

- 2025-12-14: Migration framework & metrics
  - Added ThumbDB migrations, metrics collector and instrumentation, with tests and docs.

Notes:
- Tests and linters run locally (unit tests passing; pyright clean). QML Viewer POC and interaction tests were added.

---


## 📝 작업 시작 전 체크리스트

1. High Priority에서 항목 선택
2. TASKS.md에 task 추가 (T-XXX)
3. 작업 완료 후:
   - [ ] TASKS.md 체크박스 체크
   - [ ] SESSIONS.md에 상세 기록
  - [ ] SESSIONS.md에 기록 상태 업데이트
   - [ ] Recently Completed로 이동
4. 1주일 후: Recently Completed에서 제거 (SESSIONS.md에는 영구 보관)
