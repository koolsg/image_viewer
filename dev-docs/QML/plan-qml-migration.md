# Plan: QWidget → QML 전환 (요약)

목표: 현재 PySide6 QWidget/QGraphicsView 기반 UI를 QML( Qt Quick Controls )로 전환하는 실용적이고 안전한 로드맵을 제시합니다. 최대한 기존 엔진(디코드/캐시/DB)을 재사용하면서, 사용자 경험과 유지보수성을 개선하는 것이 핵심입니다.

---

## 1) 핵심 요약 ✅
- 권장 방식: **하이브리드(점진적 도입)** — 기존 `QMainWindow`는 유지하고, 화면 단위(먼저 Viewer)를 QML로 교체해 점진 마이그레이션.
- 최종 옵션: 전면 QML Shell(모든 UI를 QML로 재작성) — 더 깔끔하나 위험/리소스·시간 비용 큼.
- POC(우선): `Viewer`만 QML로 옮겨 **렌더 성능과 엔진 통합(이미지 제공)** 이슈를 먼저 검증.

---

## 2) 왜 하이브리드가 좋은가
- 엔진과 IO(썸네일 DB, multi-process decode)가 이미 잘 분리되어 있어 재사용 이점이 큼.
- Crop 도구 및 Explorer 같은 복잡한 위젯을 즉시 포팅하기보다 안정성을 보장하며 단계적으로 교체 가능.
- Windows fullscreen/렌더링 문제 같은 플랫폼별 버그를 단계적으로 검증 가능.

---

## 3) 세부 마이그레이션 단계 (하이브리드, 권장)

1. 준비: QML 호스트 도입
   - `QQuickWidget` 또는 `QQuickView`를 중앙 위젯 대안으로 추가한다.
   - `AppController`(QObject)로 핵심 명령/상태/시그널을 QML에 노출.

2. POC: Viewer 페이지만 QML로 전환
   - QML `ViewerPage.qml` + C++ `ViewerItem : QQuickItem`(권장) 또는 `Image` 기반으로 빠르게 구현.
   - 기존 `DecodeService`와 `ImageEngine`에서 제공하는 이미지(또는 provider)를 QML에서 소비할 수 있도록 `QQuickImageProvider` 또는 `ImageProvider` 계층을 추가.

3. Explorer(썸네일 그리드) 전환
   - `FolderItemsModel(QAbstractListModel)`로 roles 정의(`thumbKey`, `fileName`, `dimensions` 등).
   - `GridView`에서 delegate와 바인딩.

4. Settings / Menus / Dialogs 전환
   - 설정 창 등은 QML Dialogs 또는 기존 QWidget과 혼용.

5. Crop 포팅(마지막)
   - 고난이도: 핸들, 좌표계, press-zoom, preview 동작을 QML로 옮기기 전, 임시로 기존 `ui_crop.py` 다이얼로그를 QML에서 호출하는 하이브리드 유지 가능.

6. 정리: 완전 전환하거나, 필요한 부분만 QML로 유지 후 QWidget 제거.

---

## 4) 전면 QML Shell (대안)
- `QQmlApplicationEngine` 기반으로 모든 UI를 QML로 재작성.
- 장점: 깔끔한 상태 관리, 일관된 스타일, QML 장점(애니메이션, 레이아웃)
- 단점: 많은 UI 재작성 비용, 복잡·위험이 큰 작업(특히 Crop/Explorer)

권장 시나리오: 하이브리드 진행 후 문제를 모두 확인한 뒤에 결정.

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
- 새 파일(권장): `app/qml/ViewerPage.qml`, `app/qml/components/StatusOverlay.qml`, `image_viewer/qml_bridge.py` 또는 C++ QObject bridge

---

## 8) 권장 작업 순서(단계별, 단기 목표)
1. Viewer POC(2주): Viewer QML 구현 + engine provider 연결
2. Explorer model 준비(1–2주): QAbstractListModel 작성 및 QML grid 연결
3. 썸네일 캐시/프리패치 확인(1–2주)
4. Crop 하이브리드 유지(설계 1주) → QML 포팅(2–4주)
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