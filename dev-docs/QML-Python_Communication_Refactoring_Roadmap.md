# QML–Python(Main) 통신 개선 로드맵

> **목표**: `dev-docs/Signal-Slot_Refactoring_Concept.md`의 방향(상태=Property, UI→Backend=단일 명령 통로, 장시간 작업=task 채널)을 기반으로, 현재 코드베이스의 QML↔Python(`Main`) 통신 구조를 점진적으로 개선하는 계획.

---

## 1) 현행 구조 요약 (QML ↔ Main)

### QML에서 `Main` 주입 방식
- **`image_viewer/main.py: run()`**
  - `QQmlApplicationEngine.load(App.qml)` 이후
  - `root = qml_engine.rootObjects()[0]`
  - `root.setProperty("main", main)` 로 주입
- **QML(`App.qml`)**
  - `property var main: null`로 시작
  - `root.main`이 늦게 세팅되기 때문에 방어 코드가 많음 (`root.main ? ... : ...`, `qmlDebugSafe()` 큐잉 등)

### QML이 실제로 사용하는 Main API 표면
- **Property 바인딩 기반(상태/표시)**
  - `currentFolder`, `imageFiles`, `currentIndex`, `viewMode`, `imageUrl`
  - `zoom`, `fitMode`, `rotation`
  - `fastViewEnabled`, `backgroundColor`, `pressZoomMultiplier`, `thumbnailWidth`
  - `statusOverlayText`
  - WebP: `webpConvertRunning`, `webpConvertPercent`
- **직접 호출 슬롯(명령형 UI 이벤트)**
  - `openFolder()`, `closeView()`
  - 파일 작업: `copyFiles()`, `cutFiles()`, `pasteFiles()`, `renameFile()`, `performDelete()`, `revealInExplorer()`
  - WebP: `startWebpConvert()`, `cancelWebpConvert()`
  - 기타: `setBackgroundColor()`, `copyText()`, `refreshCurrentFolder()`, `refreshCurrentImage()` 등
- **QML에서 Connections로 직접 받는 시그널**
  - `ConvertWebPDialog.qml`이 `webpConvertLog/Finished/Canceled/Error`를 `Connections { target: dlg.main }`로 수신

### Main 내부 역할 혼재(핵심 관찰)
- `Main(QObject)`가 다음을 모두 들고 있음
  - **UI 상태**(zoom/rotation/viewMode 등)
  - **탐색기/선택/모델**(imageModel, imageFiles 등)
  - **파일시스템 mutation**(delete/rename/paste 등)
  - **장시간 작업(WebP)** 상태/이벤트
  - **Engine(ImageEngine) 브릿지**(engine signal→Main slot)

---

## 2) 문서 기준으로 본 “현재 구조의 문제/리스크”

- **[주입 타이밍 문제]** `root.main`이 로딩 이후에 세팅되므로 QML 전역에 `null 가드`, `queue` 패턴이 퍼짐  
  - 이 자체가 “통신 구조가 불안정하다”는 신호입니다.
- **[API 표면 폭증 가능성]** 지금은 슬롯 개수가 “관리 가능한 수준”이지만, 기능이 추가될수록 `Main`에 QML-callable 메서드가 계속 늘어나는 구조입니다.
- **[작업(task) 신호 폭발]** WebP가 이미 전형적인 패턴입니다.
  - `RunningChanged`, `ProgressChanged`, `Log`, `Finished`, `Canceled`, `Error`…
  - 작업이 2~3개로 늘면 시그널이 선형이 아니라 “묶음 단위”로 증가합니다.
- **[책임 경계 불명확]** `Main`이 “상태 저장소 + 커맨드 핸들러 + 작업 관리자 + 엔진 브릿지”여서, 테스트/리팩터링 단위가 애매해집니다.
- **[타입/변환 이슈 재발 가능]** QML→Python 변환에서 `QJSValue`/리스트/딕트 처리가 까다로워 이미 `_coerce_paths()` 같은 방어 로직이 존재합니다.  
  - 단일 명령 버스로 가면 이 변환 문제가 **더 자주/더 넓게** 나타날 수 있어, “표준 payload coercion”이 필요합니다.

---

## 3) 목표 구조(도착점) 제안: “하이브리드(추천 구조)”를 코드베이스에 맞게

### 통신 원칙(고정)
- **상태(State)**: QML은 `Property binding`으로 읽고, Python에서는 setter에서 notify만 발생  
- **명령(Command)**: QML→Python은 `dispatch(cmd, payload)` **단일 진입점** 중심(필요 시 일부 고빈도/특수 API는 예외적으로 전용 슬롯 유지)
- **작업(Task)**: Python→QML은 `taskEvent(dict)` **단일 채널**로 통합 (WebP 같은 장시간 작업 전부 여기에 탑재)

### 오브젝트 구성(권장)
- `Main(QObject)`는 “파사드 + 디스패처”로 축소
- 상태는 별도 QObject로 분리 (QML 노출용)
  - 예: `viewerState`, `explorerState`, `settingsState`, `clipboardState`, `taskState`
- 단, **기존 QML을 바로 다 깨지 않기 위해** `Main`에 **호환용 forwarding property**를 한동안 유지하는 방식이 안전합니다.

---

## 4) 단계별 리팩터링 플랜(점진적/안전)

### 1단계: “주입 타이밍” 안정화 (QML 가드/큐 제거 기반)
- **목표**
  - QML이 시작 시점부터 `main`을 신뢰할 수 있게 만들기
- **방식 후보**
  - **(추천)** `QQmlApplicationEngine.rootContext().setContextProperty("main", main)`를 `load()` 이전에 수행
  - 그리고 점진적으로 QML에서 `root.main` 대신 `main`(컨텍스트 프로퍼티)를 사용하도록 변경
- **효과**
  - `qmlDebugSafe` 같은 우회 패턴을 제거할 명분/기반이 생김
  - “통신 구조 개선”의 토대가 됨

### 2단계: 상태(State) 오브젝트 분리 (Signal 폭 감소 + 책임 분리)
- **목표**
  - `Main`에서 순수 상태를 분리해 결합도 낮추기
- **대상 예시**
  - `ViewerState`: `viewMode/zoom/fitMode/rotation/currentIndex/currentPath/imageUrl/statusOverlayText`
  - `ExplorerState`: `currentFolder/imageModel/thumbnailWidth` (+ 필요시 선택 상태)
  - `SettingsState`: `fastViewEnabled/backgroundColor/pressZoomMultiplier` 등
- **호환 전략**
  - 당장 QML을 다 바꾸기 어렵다면:
    - `Main.zoom` 같은 기존 property는 내부적으로 `viewerState.zoom`에 위임(포워딩)
    - QML은 천천히 `main.viewerState.zoom`로 이동

### 3단계: UI→Backend 단일 명령 버스 도입 (슬롯 확장 방지)
- **목표**
  - QML에서 새로운 기능 추가 시 `Main` 슬롯을 늘리지 않고 흡수
- **도입 방식**
  - `dispatch(cmd: str, payload: object)` 같은 단일 슬롯 추가
  - `cmd`는 문자열이되, 오타 방지를 위해:
    - QML에 `const Cmd = {...}` 형태 상수 테이블(또는 별도 js 모듈)
    - Python에 `Enum`/상수 집합(그리고 unknown cmd 로깅)
- **초기 적용 범위(추천)**
  - 단순 UI 제어부터: `setZoom`, `setFitMode`, `rotateBy`, `toggleViewMode`, `openFolder`
  - 파일 작업류는 payload 변환/에러 영향이 크므로 후순위로 단계적 이전

### 4단계: Task 채널 통합 (WebP부터)
- **목표**
  - `webpConvertLog/Finished/Canceled/Error/...`를 `taskEvent(dict)` 하나로 흡수
- **권장 이벤트 스키마(예시)**
  - `{"type": "task", "name": "webpConvert", "state": "progress", "completed": 10, "total": 50, "message": "..."}`
  - `{"type": "task", "name": "webpConvert", "state": "finished", "ok": true, "converted": 120, "total": 123}`
  - `{"type": "task", "name": "webpConvert", "state": "error", "message": "..." }`
- **호환 전략**
  - 초기에 `taskEvent`를 추가하고, 기존 webp 시그널도 계속 emit (QML 양쪽 수신 가능)
  - 다음 단계에서 QML을 `taskEvent`로 옮기고, 기존 시그널 제거

### 5단계: 정리/축소 (Main 슬림화)
- **목표**
  - `Main`은 “디스패치 + 엔진 브릿지 + 상태 객체 노출”만 남기기
- **정리 대상**
  - 더 이상 사용하지 않는 legacy signal/slot 제거
  - QML에서 `root.main.*` 직접 호출 제거 → `dispatch()` 또는 state binding으로 통일

---

## 5) 검증 체크리스트(마이그레이션 시 깨지기 쉬운 포인트)
- **Explorer**
  - 폴더 열기/그리드 표시/선택/더블클릭 View 전환
  - 삭제/이름변경/복사/붙여넣기(특히 QML→Python payload 변환)
- **Viewer**
  - `viewMode` 전환, `zoom/fitMode/rotation` 동작, `imageUrl` 갱신
- **WebP**
  - 진행률/로그/취소/에러/완료가 UI에 정확히 반영되는지
- **초기 구동**
  - `main` 주입 전/후 타이밍 이슈가 사라졌는지(가드 제거 가능 여부)

---

## 6) 결론(지금 당장 “가장 효과 큰” 우선순위)
- **1순위**: `main` 주입을 컨텍스트 프로퍼티 기반으로 바꿔서 QML의 `null 가드/큐` 구조를 없앨 기반 만들기  
- **2순위**: WebP를 `taskEvent(dict)`로 묶어서 “작업 시그널 폭발”을 먼저 차단  
- **3순위**: `dispatch(cmd,payload)` 도입 후 UI 이벤트 슬롯 증가를 중단시키기  
- **4순위**: `ViewerState/ExplorerState/...`로 상태를 분리해 `Main`을 슬림화

---

> **완료 상태**: 문서 내용 반영 + 현재 코드베이스(QML/App.qml, Main/main.py, ConvertWebPDialog.qml, ImageEngine 등) 통신 구조 분석을 기반으로 리팩터링 계획 수립 완료
