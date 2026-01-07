#  Signal/Slot 리팩터링 개념 정리
QML–Python 연동이 커질수록 **개별 signal/slot을 계속 늘리는 방식은 유지보수 지옥**으로 간다.
보통은 **“단일 메시지 버스” 패턴**으로 정리한다.

아래는 **Qt/QML + Python(QObject)** 조합에서 가장 현실적으로 쓰이는 방법들이다.

---

## 1️⃣ 단일 Signal + 메시지 디스패처 (가장 많이 씀)

### 핵심 아이디어

* **신호는 하나**
* payload는 `dict / QVariantMap`
* Python에서 **action 기반으로 분기 처리**

### Python (Backend)

```python
from PySide6.QtCore import QObject, Signal, Slot

class Backend(QObject):
    message = Signal(dict)   # QML → Python
    response = Signal(dict)  # Python → QML

    @Slot(dict)
    def on_message(self, msg):
        action = msg.get("action")

        if action == "openFile":
            self.open_file(msg.get("path"))

        elif action == "saveFile":
            self.save_file(msg.get("data"))

        elif action == "exit":
            self.shutdown()

    def open_file(self, path):
        self.response.emit({
            "action": "openFileResult",
            "success": True,
            "content": "..."
        })
```

```python
backend.message.connect(backend.on_message)
```

---

### QML (Frontend)

```qml
Button {
    text: "Open"
    onClicked: backend.message({
        action: "openFile",
        path: "/tmp/a.txt"
    })
}

Connections {
    target: backend
    function onResponse(msg) {
        if (msg.action === "openFileResult") {
            console.log(msg.content)
        }
    }
}
```

### 장점

* signal 2개로 끝
* 기능 추가 시 signal/slot 추가 불필요
* QML이 얇아짐

### 단점

* 문자열 action 오타 → 런타임 오류
* 타입 안정성 낮음

👉 **실무에서 가장 흔한 방식**

---

## 2️⃣ Command / RPC 스타일 (조금 더 정제됨)

### 개념

* **QML은 명령만 보냄**
* Python이 중앙 디스패처 역할
* 거의 API 호출처럼 동작

### Python

```python
class Backend(QObject):
    request = Signal(str, dict)
    reply = Signal(str, dict)

    @Slot(str, dict)
    def dispatch(self, cmd, payload):
        handler = getattr(self, f"cmd_{cmd}", None)
        if handler:
            result = handler(payload)
            self.reply.emit(cmd, result)

    def cmd_openFile(self, payload):
        return {"content": "..."}
```

### QML

```qml
backend.request("openFile", { path: "/tmp/a.txt" })

Connections {
    target: backend
    function onReply(cmd, data) {
        if (cmd === "openFile") {
            console.log(data.content)
        }
    }
}
```

### 장점

* action 문자열 관리가 깔끔
* Python 쪽에서 구조화 쉬움

---

## 3️⃣ Context Object + 상태 바인딩 (UI 상태 중심)

UI가 **이벤트 기반이 아니라 상태 기반**이라면 이게 더 낫다.

### Python

```python
class AppState(QObject):
    fileContentChanged = Signal()

    def __init__(self):
        super().__init__()
        self._fileContent = ""

    @Property(str, notify=fileContentChanged)
    def fileContent(self):
        return self._fileContent

    @Slot(str)
    def openFile(self, path):
        self._fileContent = "..."
        self.fileContentChanged.emit()
```

### QML

```qml
TextArea {
    text: appState.fileContent
}

Button {
    onClicked: appState.openFile("/tmp/a.txt")
}
```

### 장점

* signal 최소화
* QML스럽고 선언적
* UI가 복잡할수록 유리

### 단점

* 이벤트 중심 로직에는 부적합

---

## 4️⃣ 하이브리드 (추천 구조)

실제로 가장 많이 쓰는 형태:

| 용도     | 방식                                  |
| ------ | ----------------------------------- |
| UI 이벤트 | 단일 message / request signal         |
| 앱 상태   | Context Property + Property binding |
| 결과 통지  | response / reply signal             |

```
QML
 ├─ UI Event  ─────▶ backend.message(...)
 ├─ 상태 표시 ◀──── appState.property
 └─ 결과 처리 ◀──── backend.response(...)
```

---

## 언제 단일 통로가 **안 좋은가**

* 고빈도 실시간 데이터 (프레임, 스트리밍)
* 엄격한 타입 안정성이 필요한 경우
* 복잡한 비동기 체인

이 경우는 **전용 signal 유지**가 낫다.

---

## 한 줄 요약

> QML–Python 통신은 **기능별 signal**이 아니라
> **“메시지 하나 + 디스패처”로 만들면 확장성과 유지보수가 급격히 좋아진다.**

---

# 개략적인 계획

지금 구조를 그대로 두고 기능을 더 얹으면, 이후에는 **어디서 무엇이 바뀌는지 추적 자체가 어려워진다.**

아래는 **지금 가진 신호들을 유지하면서도** 단일 통로 구조로 **점진적으로 정리하는 현실적인 방법**이다.

---

## 1️⃣ 신호를 성격별로 나누어 보면 문제의 본질이 보인다

지금 나열한 것들을 분류하면 사실 4종류뿐이다.

### A. 상태 변경 통지 (state)

```python
currentFolderChanged
currentIndexChanged
viewModeChanged
zoomChanged
rotationChanged
backgroundColorChanged
fastViewEnabledChanged
thumbnailWidthChanged
```

→ **Property + notify**로 가야 할 대상

---

### B. 파생 데이터 / 결과

```python
imageFilesChanged
imageUrlChanged
imageModelChanged
clipboardChanged
statusOverlayChanged
```

→ 상태 변경의 **결과물**

---

### C. 장시간 작업(Task)

```python
webpConvertRunningChanged
webpConvertProgressChanged
webpConvertLog
webpConvertFinished
webpConvertCanceled
webpConvertError
```

→ **하나의 작업 채널**로 묶어야 할 대상

---

### D. UI 제어 이벤트

```python
fitModeChanged
pressZoomMultiplierChanged
```

→ **단일 명령 통로**로 흡수 가능

---

## 2️⃣ 1차 정리: “상태 신호”를 통째로 없앤다

### ❌ 지금 방식

```python
zoomChanged = Signal(float)
rotationChanged = Signal(float)
```

### ✅ 바꿔야 할 방식

```python
class ViewerState(QObject):
    zoomChanged = Signal()
    rotationChanged = Signal()

    @Property(float, notify=zoomChanged)
    def zoom(self): ...

    @Property(float, notify=rotationChanged)
    def rotation(self): ...
```

QML:

```qml
Scale {
    scale: viewerState.zoom
}
```

📌 **결과**

* `zoomChanged`, `rotationChanged` 같은 신호는 유지되지만
* **직접 emit할 일이 사라진다**
* Python 내부 로직이 훨씬 단순해진다

👉 이 단계만 해도 신호 체감량이 절반 이하로 줄어든다.

---

## 3️⃣ 2차 정리: UI → Backend는 단일 명령 버스로

### 하나의 진입점만 둔다

```python
uiCommand = Signal(str, dict)

@Slot(str, dict)
def dispatch(self, cmd, payload):
    match cmd:
        case "openFolder":
            self.open_folder(payload["path"])
        case "setZoom":
            self.viewerState.zoom = payload["value"]
        case "rotate":
            self.viewerState.rotation += payload["delta"]
```

QML:

```qml
backend.uiCommand("setZoom", { value: 1.25 })
```

📌 이렇게 하면:

* `fitModeChanged`
* `pressZoomMultiplierChanged`
* 향후 추가될 모든 UI 이벤트

→ **신호 추가 없이 흡수 가능**

---

## 4️⃣ 3차 정리: WebP 변환은 “작업 채널” 하나로 묶는다

지금 구조는 전형적인 **task 상태 폭발** 패턴이다.

### ❌ 현재

```python
webpConvertRunningChanged
webpConvertProgressChanged
webpConvertLog
webpConvertFinished
webpConvertCanceled
webpConvertError
```

### ✅ 추천

```python
taskEvent = Signal(dict)
```

emit 예시:

```python
self.taskEvent.emit({
    "task": "webpConvert",
    "type": "progress",
    "value": 42
})
```

```python
self.taskEvent.emit({
    "task": "webpConvert",
    "type": "finished",
    "ok": True,
    "success": 120,
    "failed": 3
})
```

QML:

```qml
Connections {
    target: backend
    function onTaskEvent(e) {
        if (e.task !== "webpConvert") return

        switch (e.type) {
        case "progress":
            progressBar.value = e.value
            break
        case "finished":
            console.log("done")
            break
        }
    }
}
```

📌 **작업이 10개로 늘어도 signal은 1개**

---

## 5️⃣ 최종 구조 (현실적인 도착점)

```text
QML
 ├─ uiCommand(cmd, payload) ─────▶ Backend
 │
 ├─ viewerState.xxx (Property binding)
 │
 └─ taskEvent(event) ◀──────────── Backend
```

Python(QObject):

* `ViewerState` (순수 상태)
* `Backend.dispatch()` (명령 처리)
* `taskEvent` (모든 장시간 작업 공용)

---

## 6️⃣ 중요한 기준 하나

> **“이 신호는 직접 emit해야 하는가?”**

* ❌ Yes → 구조가 잘못되었을 확률 높음
* ✅ No (Property 변경으로 자동 발생) → 정상

---

## 정리 문장

지금 구조는 기능이 늘어날수록 **선형이 아니라 지수적으로 복잡해진다.**
상태는 Property로,
UI 이벤트는 단일 명령 버스로,
장시간 작업은 하나의 task 채널로 묶으면
**신호 개수는 거의 더 이상 늘지 않는다.**

원하면

* 지금 클래스 기준으로 **실제 리팩터링 순서**
* 기존 QML 깨지지 않게 옮기는 방법
  도 단계별로 같이 정리해줄 수 있다.

---

# JSON 방식

**지금 상황에는 JSON 방식이 잘 맞는다.**
이미 신호가 많고, 앞으로 더 늘어날 게 보이기 때문에 **“구조화된 메시지”**로 가는 게 자연스럽다.

아래는 **QML ↔ Python(QObject)** 에서 JSON을 **실제로 안정적으로 쓰는 방법**이다.

---

## 1️⃣ 기본 전제 (중요)

Qt에서 말하는 “JSON”은 보통 두 층이다.

* **QML ↔ Python 신호 전달**: `dict / list` (QVariantMap)
* **경계 내부 표현**: JSON 구조를 따르는 객체

👉 즉, **문자열 JSON을 매번 dumps/loads 할 필요는 없다.**
구조만 JSON처럼 가져가면 된다.

---

## 2️⃣ 단일 JSON 메시지 채널 (권장 기본형)

### Python (Backend)

```python
from PySide6.QtCore import QObject, Signal, Slot

class Backend(QObject):
    message = Signal(dict)   # QML → Python
    event = Signal(dict)     # Python → QML

    @Slot(dict)
    def on_message(self, msg):
        try:
            msg_type = msg["type"]
        except KeyError:
            return

        if msg_type == "command":
            self._handle_command(msg)
        elif msg_type == "task":
            self._handle_task(msg)

    def _handle_command(self, msg):
        match msg["name"]:
            case "setZoom":
                self.viewerState.zoom = msg["value"]

            case "rotate":
                self.viewerState.rotation += msg.get("delta", 0)

    def _handle_task(self, msg):
        if msg["name"] == "webpConvert":
            self.start_webp_convert(msg["options"])
```

---

### QML

```qml
backend.message({
    type: "command",
    name: "setZoom",
    value: 1.25
})
```

이 시점부터 **UI 이벤트가 늘어나도 signal 추가는 없다.**

---

## 3️⃣ 작업(Task) 이벤트도 JSON으로 통일

### Python → QML

```python
self.event.emit({
    "type": "task",
    "name": "webpConvert",
    "state": "progress",
    "value": 37
})
```

```python
self.event.emit({
    "type": "task",
    "name": "webpConvert",
    "state": "finished",
    "success": 120,
    "failed": 3
})
```

### QML

```qml
Connections {
    target: backend
    function onEvent(e) {
        if (e.type !== "task") return
        if (e.name !== "webpConvert") return

        switch (e.state) {
        case "progress":
            progressBar.value = e.value
            break
        case "finished":
            console.log("done")
            break
        }
    }
}
```

---

## 4️⃣ 상태(State)는 JSON으로 “밀지 말고” 바인딩

여기서 흔히 하는 실수:

❌ 상태 변경도 전부 JSON으로 보내기
⭕ 상태는 Property, **이벤트만 JSON**

### 이유

* QML의 강점은 선언적 바인딩
* JSON은 **이벤트/명령 전달용**

> JSON = “무언가 일어나게 한다”
> Property = “지금 상태가 무엇인가”

---

## 5️⃣ 문자열 JSON을 써야 하는 경우 (예외)

다음 경우에만 `json.dumps()` / `loads()`를 고려한다.

* 외부 프로세스 / 네트워크와 통신
* 로그를 그대로 파일에 남기고 싶을 때
* IPC / WebSocket 연동

### 예시

```python
jsonMessage = Signal(str)

self.jsonMessage.emit(json.dumps({
    "type": "task",
    "name": "webpConvert",
    "state": "error",
    "message": "invalid format"
}))
```

QML:

```qml
var msg = JSON.parse(message)
```

📌 **내부 통신에는 추천하지 않는다.**

---

## 6️⃣ JSON 스키마를 느슨하게라도 정해라

최소한 이 정도는 고정하는 게 좋다.

```json
{
  "type": "command | event | task",
  "name": "string",
  "payload": { }
}
```

또는

```json
{
  "type": "task",
  "name": "webpConvert",
  "state": "progress | finished | error",
  "data": { }
}
```

👉 이 규칙 하나만 있어도 **확장성 차원이 달라진다.**

---

## 7️⃣ 지금 코드에 적용했을 때 얻는 것

* 신호 개수 증가 **완전 차단**
* webp 같은 작업 계열 **무한 확장 가능**
* QML–Python 경계가 **API처럼 명확해짐**
* 테스트 / 로깅 / 리플레이 쉬워짐

---

## 결론 문장

> 가능하냐가 아니라, **지금 구조에서는 JSON 메시지 버스가 가장 덜 아프다.**
> 단, 상태까지 JSON으로 밀지 말고
> **명령과 이벤트만 JSON으로 통합**하는 게 핵심이다.

원하면

* 지금 나열한 signal들을 **JSON/Property로 실제 분해해서 재배치**
* JSON 스키마 초안 작성
  까지 같이 해줄 수 있다.
