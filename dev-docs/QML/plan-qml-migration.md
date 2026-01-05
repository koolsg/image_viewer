# Plan: QML Shell 전면 전환 (결정)

목표: 기존 QWidget UI는 더 이상 유지하지 않고, **사용자 조작 UI는 전부 QML**로 옮긴다.
Python은 `AppController`(명령/상태) + `ImageEngine`(디코드/캐시/DB/스캔)만 담당한다.

---

## 1) 현재 결정/상태 ✅

- **전면 QML Shell로 전환한다.** 과도기/하이브리드는 하지 않는다.
- 엔트리포인트는 `QQmlApplicationEngine` 기반이며, QML의 `ApplicationWindow`가 메인 윈도우다.
- 이미지 제공은 QML ImageProvider로 한다.
   - full image: `image://engine/...` (엔진 pixmap cache)
   - thumbnail: `image://thumb/...` (thumb DB PNG bytes)

---

## 2) 우선순위 (trim/crop은 나중)

1) Explorer: **썸네일 grid + 메타데이터 + 컨텍스트 메뉴 + 단축키 체계(QML)**
2) Viewer: QML View가 Explorer와 자연스럽게 연동되고 키보드 네비가 일관적일 것
3) 마지막: trim/crop 포팅

---

## 3) Explorer(QML) 구현 스펙

### 3.1 Model (Python)
- `QAbstractListModel` 기반(예: `QmlImageGridModel`)
- 역할(roles) 예시:
  - `path`, `name`, `sizeText`, `mtimeText`, `resolutionText`, `thumbUrl`
- 데이터 소스는 `ImageEngine` 스냅샷 신호를 사용한다:
  - `explorer_entries_changed(folder, entries)`
  - `explorer_thumb_rows(rows)` / `explorer_thumb_generated(payload)`

### 3.2 View (QML)
- `GridView` + delegate 카드 UI
- 우클릭 `Menu`:
  - Open
  - Copy path
  - Reveal in Explorer

### 3.3 Shortcuts (QML)
- `Ctrl+O`: 폴더 열기
- `Esc`: Viewer → Explorer
- `Left/Right/Home/End`: Viewer에서 이미지 이동
- `Ctrl+C`: 현재 path 복사

---

## 4) 검증 체크리스트

- Explorer에서 썸네일이 DB preload/생성에 따라 점진적으로 채워진다.
- Explorer에서 더블클릭(또는 Open) → Viewer로 진입하고 currentIndex/currentPath가 일치한다.
- Viewer에서 키보드 네비(Left/Right/Home/End)와 Esc 종료가 안정적으로 동작한다.
- 컨텍스트 메뉴 동작(복사/탐색기 열기)이 Windows에서 정상.

---

## 5) 주요 리스크와 완화책 ⚠️
- **렌더 성능 / 메모리**: QML 텍스처/이미지 업로드가 메모리를 급격히 소모할 수 있음.
  - 완화: preview/refine 전략 유지, 텍스처/GPU 캐시 상한, LRU 정책.

- **스레드 안전성**: GUI 리소스는 UI 스레드에서만 생성해야 함.
  - 완화: 워커는 raw bytes/공유메모리/바이트를 만들어 전달하고, UI에서 QImage/QPixmap/QSGTexture 생성.

- **Crop의 복잡성**: 히트테스트·좌표 변환 등 재현이 어려움.
  - 완화: Crop을 마지막으로 옮기고, 임시로 QML에서 기존 다이얼로그를 호출.

- **Windows fullscreen/호환성 문제**
  - 완화: POC에서 fullscreen 동작 검증(특히 QQuickWidget vs QQuickView 차이).

---

## 6) Acceptance Criteria (POC 기준) 🎯
- Viewer QML로 교체 후: fit/actual, wheel zoom, drag pan, status overlay 동작이 기존과 동등하거나 더 안정적일 것.
- 엔진 통합: decode pipeline(프리뷰/리파인)과 QML provider 연동 시 stale result(오래된 결과) 방지.
- 퍼포먼스: 기본 탐색(폴더 이동, 이미지 전환)에서 체감 지연이 없을 것.

---

## 7) 초기 POC 파일/터치포인트(권장 변경 목록)
- `image_viewer/main.py` — QML 호스트 등록 및 토글 기능 추가
- `image_viewer/ui_canvas.py` — 기존 Viewer 동작 참조, QML로 대체될 부분 명세
- `image_viewer/image_engine/engine.py` — QML ImageProvider용 API(이미지 크기/디코드 정보 노출)
- `image_viewer/ui_explorer_grid.py`, `ui_explorer_tree.py` — 탐색기 재구성 시 참고
- 새 파일(권장): `image_viewer/qml/ViewerPage.qml`, `image_viewer/qml/components/StatusOverlay.qml`, `image_viewer/qml_bridge.py` 또는 C++ QObject bridge

---

## 8) 권장 작업 순서(단계별, 단기 목표)
1. Viewer POC(2주): Viewer QML 구현 + engine provider 연결
2. Explorer model 준비(1-2주): QAbstractListModel 작성 및 QML grid 연결
3. 썸네일 캐시/프리패치 확인(1-2주)
4. Crop 하이브리드 유지(설계 1주) -> QML 포팅(2-4주)
5. 완전 전환/정리

---

## 9) 기타 메모
- 디자인/스타일: `styles.py`에 있던 색·테마를 QML로 재현하는 스펙 필요
- 테스트: Viewer 동작(zoom anchor, cursor stability)과 engine↔UI 계약을 중심으로 자동화된 테스트 케이스 우선 작성

---

Why (quick trade-offs) ⚖️
Keep QMainWindow (recommended for hybrid)

Easier incremental migration and testing (menus, shortcuts, dialogs remain unchanged).
Keeps existing app shell code and wiring (ImageViewer, commands) intact.
Need a small bridge to expose state/commands to QML.
Full QML Shell (long-term/alternative)

Cleaner long-term architecture if you rebuild everything.
Larger, riskier rewrite — not ideal for stepwise POC.
Practical options & recommendations 🔧
Embed QML in QMainWindow:
Use createWindowContainer(QQuickView) or QQuickView hosted inside the QWidget world (recommended).
QQuickWidget is simpler but can have more rendering/GL quirks on Windows; avoid it if you plan fullscreen or heavy GPU usage.
Fullscreen behavior:
Preferred: detach to top-level QQuickWindow / QQuickView when entering fullscreen (show as WindowFullScreen) to avoid flicker and embedding issues.
Alternative: hide QMainWindow chrome and expand the container — workable but riskier on Windows.
Expose app functionality via a small bridge object (AppController : QObject) with properties/signals/slots bound into QML.
Implementation notes & gotchas ⚠️
Keep menus/shortcuts in QMainWindow or forward them to QML consistently.
Ensure texture creation/updating follows Qt rules: create textures on GUI/render thread; worker → UI must only pass raw bytes/handles.
Test fullscreen transitions on Windows early (embedding vs detached window).
For the Crop tool, consider keeping the existing QWidget dialog during migration and call it from QML until ported.
Acceptance tests (POC) ✅
Viewer loads inside QMainWindow and displays images via QML provider.
Fit/actual, wheel-zoom, drag-pan, and overlay work as expected.
Fullscreen toggles to native fullscreen without visible flicker/crash on Windows.
Keyboard shortcuts and context menus still work.