# QML–Python 경계 제로베이스 설계 (권장 레퍼런스 아키텍처)

> **목표**: 기존 코드에 얽매이지 않고, QML UI와 Python 백엔드 간의 관계와 구조를 제로에서 설계할 때의 권장 아키텍처와 원칙을 제시합니다.

---

## 1) 제로베이스 설계 원칙(강제 규칙)

- **[단일 진입점]** QML→Python은 원칙적으로 `dispatch(cmd, payload)` *한 개*만 둔다.  
  - 예외는 “초고빈도/실시간” (프레임 스트림 등)만 전용 API 허용.
- **[상태는 바인딩]** UI에 보여지는 값은 전부 `State QObject`의 `Property`로 제공한다.  
  - “상태 변경을 JSON 이벤트로 밀기” 금지.
- **[이벤트는 스트림]** Python→QML의 “무언가 일어남”은 `event(dict)`와 `taskEvent(dict)`로만 보낸다.  
  - 화면 전환/토스트/모달/로그/진행률 등은 이벤트로.
- **[QML은 Dumb View]** QML은 “표시 + 입력 수집 + 바인딩 + 라우팅”만.  
  - 파일 시스템 변경, 비즈니스 규칙, 캐시/DB 정책은 Python에서만.
- **[스키마 고정]** dict를 쓰더라도 최소 키는 고정하고, unknown/invalid는 즉시 로깅+거절.

---

## 2) 권장 아키텍처(구성 요소)

### 2.1 Backend Facade (QML에 노출되는 유일 객체)
QML에 노출되는 것은 **딱 1개**: `backend`(혹은 `app`).

- `backend.dispatch(cmd: str, payload: object) -> None`
- `backend.event(dict)` (일반 이벤트: 네비게이션/알림/에러/로그 등)
- `backend.taskEvent(dict)` (장시간 작업 이벤트: progress/finished/canceled/error)
- `backend.state` 하위에 상태 객체들을 보관

즉 QML은 이렇게만 씁니다.
- 상태: `backend.viewer.zoom`, `backend.explorer.currentFolder` …
- 명령: `backend.dispatch("openFolder", {path: ...})`
- 이벤트: `Connections { target: backend; function onEvent(e) { ... } }`

### 2.2 State Objects (QML 바인딩용 상태 모델)
상태는 목적별로 쪼갭니다. 예:

- **`ViewerState`**
  - `viewMode`, `currentPath`, `imageUrl`, `zoom`, `fitMode`, `rotation`, `statusText` …
- **`ExplorerState`**
  - `currentFolder`, `currentIndex`, `imageModel`, `selection`(필요시) …
- **`SettingsState`**
  - `backgroundColor`, `fastViewEnabled`, `thumbnailWidth` …
- **`ClipboardState`**
  - `hasFiles`, `mode`, `count` 등(필요시)

중요 포인트:
- 상태 객체는 “순수 상태 + 최소 setter”만.
- 상태 변경은 **Python 내부 로직이 결정**. QML이 직접 상태를 조작하는 것을 최소화(가능하면 `dispatch`로 요청).

### 2.3 Services (도메인/유즈케이스 계층)
Facade/State 아래에 실제 일을 하는 서비스 계층을 둡니다.

- `FolderService` (폴더 열기, 목록 스캔, 모델 스냅샷 생성)
- `DecodeService` (디코딩 요청/취소/캐시)
- `FileOpsService` (rename/delete/copy/paste)
- `TaskService` (장시간 작업 실행/취소/상태 관리; taskEvent 발생)

이렇게 하면 `backend.dispatch()`는 사실상 라우터/검증기 역할이 되고,
실제 정책은 서비스에 모입니다.

---

## 3) 메시지/이벤트 스키마(최소 고정안)

### Command (QML → Python)
- 형태 A (가장 단순)
```json
{ "cmd": "openFolder", "payload": { "path": "C:/..." }, "rid": "optional" }
```

권장 규칙:
- **`cmd`**: 필수, 문자열
- **`payload`**: optional dict
- **`rid`**: 요청-응답 매칭이 필요하면 사용(비동기 결과를 특정 UI 액션과 연결)

### Event (Python → QML)
```json
{ "type": "event", "name": "toast", "level": "info", "message": "..." }
```

### TaskEvent (Python → QML)
```json
{ "type": "task", "name": "webpConvert", "state": "progress", "completed": 3, "total": 10 }
```

- `state`: `started | progress | finished | canceled | error`
- `name`: 작업 종류(문자열 고정)
- 에러는 항상 `message` 포함

---

## 4) 에러 처리 철학(중요)
- **QML에서 try/catch로 “로직”을 처리하지 않는다.**  
  QML은 이벤트를 받아서 UI로 표현만 한다.
- Python은 `dispatch` 단계에서:
  - payload validation 실패 → `event({type:"event", name:"error", ...})` 또는 `taskEvent(...error...)`로 통일
  - unknown cmd → warning 로그 + error event
- UI에 보여줄 문구/레벨은 Python에서 결정(일관성 확보)

---

## 5) 파일/모듈 구조 제안(현 프로젝트에 맞춘 형태)
예시(컨셉):
- `image_viewer/app/backend.py` : `BackendFacade(QObject)`
- `image_viewer/app/state/viewer_state.py`
- `image_viewer/app/state/explorer_state.py`
- `image_viewer/app/dispatch/commands.py` : cmd 상수/검증
- `image_viewer/app/services/*.py` : 서비스 계층
- `image_viewer/main.py` : 부트스트랩(컨텍스트 프로퍼티로 `backend` 주입)

그리고 QML은:
- `App.qml`은 “화면/라우팅/전역 Connections”만
- 기능별 QML 컴포넌트는 `backend.dispatch`만 호출

---

## 6) “이 설계가 좋은지” 판별하는 기준
- **새 기능이 추가될 때**
  - QML: 버튼/메뉴에서 `dispatch("newCmd", {...})` 1줄 추가
  - Python: `dispatch` 라우팅 1곳 + 서비스 1곳 추가
  - Signal/Slot은 **추가되지 않음**
- **상태 변화는 항상 Property 바인딩으로 UI에 자연스럽게 반영**
- **Task가 10개가 되어도 task signal은 1개(taskEvent) 유지**

---

## 7) QML 사용 패턴 예시

### 상태 바인딩
```qml
Text { text: backend.viewer.statusText }
Slider { value: backend.viewer.zoom; onMoved: backend.dispatch("setZoom", {value: value}) }
```

### 명령 발행
```qml
Button {
    text: "Open"
    onClicked: backend.dispatch("openFolder", {path: folderDialog.selectedUrl})
}
```

### 이벤트 수신
```qml
Connections {
    target: backend
    function onEvent(e) {
        if (e.name === "toast") toast.show(e.message)
    }
    function onTaskEvent(e) {
        if (e.name === "webpConvert") progressDialog.update(e)
    }
}
```

---

## 8) 운영 가이드(테스트/로깅)

### 테스트
- **State 객체**: 단위 테스트로 Property 변경/notify 검증
- **Services**: Mock Engine으로 각 서비스의 command→state/event 흐름 검증
- **Dispatch/Event**: End-to-end 테스트로 QML→Backend→QML 루프 검증

### 로깅
- `dispatch` 진입 시 `cmd`와 `payload` 항상 로그
- `event`/`taskEvent` 발생 시 전체 dict 로그
- unknown cmd 또는 validation 실패는 warning/error 레벨로 즉시 기록

---

> **완료 상태**: 기존 코드에 얽매이지 않는 제로베이스 설계 기준으로, QML↔Python 경계를 위한 권장 아키텍처, 메시지 스키마, 모듈 구조, 운영 가이드를 제안했습니다.
