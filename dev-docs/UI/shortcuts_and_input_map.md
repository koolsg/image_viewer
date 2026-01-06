# 단축키 및 입력 맵 (QML)

이 문서는 QML UI에서 사용되는 키보드 단축키, Keys 핸들러, 마우스 휠 동작, 마우스 클릭/호버 처리에 대한 최신 요약입니다. 각 동작이 어느 파일에 정의되어 있고, 어떤 전제(포커스/모드)를 필요로 하는지 명확히 적었습니다.

---

## 한눈에 보기 ✅
- 주 파일: `App.qml`, `ViewerPage.qml`, `ConvertWebPDialog.qml`, `DeleteConfirmationDialog.qml`
- 사용되는 입력 메커니즘:
  - `Shortcut {}` (context: `Qt.ApplicationShortcut` / `Qt.WindowShortcut`)
  - `Keys` 부착 속성 (`onPressed`, `onEscapePressed`, `onShortcutOverride` 등)
  - `WheelHandler` (Ctrl+휠: 썸네일 UI 크기 변경, 뷰어에서는 Ctrl+휠 = 줌)
  - `MouseArea` (클릭/더블클릭, 컨텍스트 메뉴)
  - `HoverHandler` + `ToolTip` (썸네일 호버 정보)
- 포커스/모드 관련 규칙: `Keys`는 `activeFocus`가 필요, `Shortcut`는 윈도우/앱 범위에서 동작합니다. `viewMode`(뷰어 전환 상태)에 따라 App 수준 단축키는 비활성화됩니다.

---

## 파일별 맵핑 (무엇을 어디에 정의했는가)

### image_viewer/qml/App.qml
- 역할: 메인 탐색(썸네일) UI, `viewWindow`(풀스크린 뷰어) 보유
- 주요 단축키/동작
  - Application-level (Explorer 전용, `Qt.ApplicationShortcut`, 작동 조건: `!root.main.viewMode`):
    - Open (StdOpen) → 폴더 열기
    - Copy / Cut / Paste → 파일 복사/이동
    - F2 → Rename
    - Delete → 파일 삭제(확인 다이얼로그)
  - View (Window-level): **No window-level fallback shortcuts.** Escape/Return **must** be handled by `ViewerPage.qml` via `Keys` (use `Keys.priority = Keys.BeforeItem` and `onShortcutOverride` to ensure the viewer consumes these keys). Window `Shortcut` fallbacks are disallowed unless explicitly documented and approved.
  - GridView (delegate) 동작:
    - Ctrl+휠 (Grid WheelHandler) → `root.main.thumbnailWidth` (UI 전용, 엔진 재생성 없음)
    - Keys.onPressed → ←/→/↑/↓/Home/End/Enter: `root.main.currentIndex`를 변경(바인딩 파괴 방지)
    - MouseArea: 클릭(선택), 더블클릭(뷰 모드로 전환)
    - HoverHandler + ToolTip: 파일명/메타데이터 표시
- 포커스/시야 처리
  - `viewWindow.visibility`는 `viewMode` 바인딩으로만 제어합니다 (핸들러에서 직접 할당 금지)
  - `onVisibleChanged`/`onActiveChanged`에서 `forceActiveFocus()`로 포커스 복원

### image_viewer/qml/ViewerPage.qml
- 역할: 풀스크린 뷰어의 핵심 로직 (이미지 표시 + 뷰어 전용 입력)
- 주요 Key 규칙
  - `Keys.priority = Keys.BeforeItem` + `Keys.onShortcutOverride` 사용: Escape/Enter를 `event.accepted = true`로 처리해 Shortcut이 가로채지 못하게 함
  - `Keys.onEscapePressed`, `Keys.onReturnPressed`, `Keys.onEnterPressed` → `root.main.closeView()` (즉시 반응)
  - `Keys.onPressed`에서 A/D 회전, Ctrl+Shift+Left/Right 회전, 그리고 뷰어 전용 ←/→/Home/End/Space/Up/Down/F/1 처리 (뷰어가 전담)
- Wheel/Mouse
  - WheelHandler: Ctrl+휠 = 줌, 일반 휠 = 이미지 이전/다음
  - Image MouseArea: press-to-zoom, 우클릭 드래그 팬, 중간 클릭으로 fit
- 우선순위: 포커스 있는 경우 Viewer Keys가 우선적으로 작업 처리함

### image_viewer/qml/ConvertWebPDialog.qml
- 배치 WebP 변환 다이얼로그
  - Browse 버튼 → `FolderDialog`
  - Start / Cancel / Close 버튼 연결 (`main.startWebpConvert`, `main.cancelWebpConvert`)
  - 변환 로그는 dialog의 TextArea에 append

### image_viewer/qml/DeleteConfirmationDialog.qml
- 간단한 Y/N 단축키
  - `Shortcut { sequences: ["Y"] ; onActivated: yesButton.clicked() }`
  - `Shortcut { sequences: ["N"] ; onActivated: noButton.clicked() }`

---

## 발견된 Shortcut / 시퀀스 (파일별, 전체 목록)
아래는 코드베이스에서 직접 확인한 모든 `Shortcut {}` 시퀀스와 `Keys`로 처리되는 주요 키들의 요약입니다. **F5는 `Refresh Explorer`(폴더 새로고침)** 용도로 `App.qml`에서 정의되어 있으며 문서에 추가했습니다.

- `image_viewer/qml/App.qml` (Action / Application / Window level)
  - `StandardKey.Open` (예: Ctrl+O) → Open Folder... (Action `actionOpenFolder`)
  - `Alt+F4` → Exit (Action `actionExit`)
  - `StandardKey.ZoomIn` → Zoom In (Action `actionZoomIn`)
  - `StandardKey.ZoomOut` → Zoom Out (Action `actionZoomOut`)
  - `"F5"` → Refresh Explorer → `root.main.refreshCurrentFolder()` (Action `actionRefreshExplorer`)
  - `"Ctrl+,"` → Open Preferences (placeholder dialog)
  - `StandardKey.Copy` → Copy selected files (Application-level)
  - `StandardKey.Cut` → Cut selected files (Application-level)
  - `StandardKey.Paste` → Paste files (Application-level)
  - `"Delete"` → Show delete confirmation for selected file (Application-level)
  - `"F2"` → Rename selected file

- `image_viewer/qml/App.qml` (viewWindow)
  - No window-level Escape/Return fallbacks; `ViewerPage.qml` handles viewer close actions via `Keys` when focused. Avoid adding window-level shortcuts in viewMode to prevent routing conflicts.

- `image_viewer/qml/DeleteConfirmationDialog.qml`
  - `"Y"` → confirm (yes)
  - `"N"` → cancel (no)

- `Keys`로 직접 처리되는 주요 키 (파일: `ViewerPage.qml`, `App.qml` Grid Keys)
  - `image_viewer/qml/ViewerPage.qml` (viewer Keys)
    - Shortcut override / immediate-response keys: `Escape`, `Return`, `Enter`
    - Viewer `onPressed` keys: `A`, `D`, `Ctrl+Shift+Left`, `Ctrl+Shift+Right`, `Ctrl+Shift+0`, `Left`, `Right`, `Home`, `End`, `Space`, `Up`, `Down`, `F`, `1` (각 키는 회전/이동/줌/fit 등 뷰어 동작을 수행)
  - `image_viewer/qml/App.qml` (Grid Keys)
    - Grid navigation: `Left`, `Right`, `Up`, `Down`, `Home`, `End`, `Return`/`Enter` (선택/뷰 모드 전환)

- Wheel / Mouse bindings
  - Grid `WheelHandler` (Ctrl+Wheel) → `root.main.thumbnailWidth` 조정 (UI 전용, 엔진 재생성 없음)
  - Viewer `WheelHandler`:
    - `Ctrl+Wheel` → 줌
    - 일반 휠 → 이미지 이전/다음
  - Viewer `MouseArea`:
    - Left-button: press-to-zoom (temporary)
    - Right-button: drag pan
    - Middle-button: snap-to-fit
    - Back/Forward (aux buttons): zoom out/in

> 요약: F5는 App.qml의 `actionRefreshExplorer`에 정의되어 있으며 `root.main.refreshCurrentFolder()`를 호출합니다. 요청하신 대로 문서에 **모든** 발견된 시퀀스를 파일별로 추가했습니다.

---

## 개발/디버깅 팁
- QML → Python 디버그 훅: `root.main.qmlDebug("msg")` — stderr로 즉시 flush되어 로그 캡처가 확실합니다.
- 입력 라우팅 확인 체크리스트:
  1. 어떤 `Shortcut`/`Keys`가 존재하는가? (파일 검색)
  2. 해당 핸들러가 `enabled`나 `viewMode` 가드로 제한되는가?
  3. 처리 우선순위: `Keys`(activeFocus) vs `Shortcut`(window/application)
  4. 포커스 복원 시점과 대상( `forceActiveFocus()` 호출 위치 검증 )

---

## 권장 패턴 (중복 허용 시 규칙)
- 중복 정의(예: Enter)는 허용하되 다음 규칙을 따르라:
  - Viewer primary: `ViewerPage.qml`에서 `Keys`로 처리 (포커스 있을 때 즉시 실행)
  - Window fallback: **Disallowed.** Do not use window-level fallbacks for Escape/Return; these keys must be handled in `ViewerPage.qml` using `Keys` (priority BeforeItem + onShortcutOverride). If a fallback is ever introduced, it must be explicitly justified, documented, and covered by automated tests.  - App-level shortcuts는 `enabled: !!root.main && !root.main.viewMode`로 뷰 모드에서 자동 비활성화

---

## QA 체크리스트 (빠른 수동 검증)
- [ ] 썸네일에서 Enter → Viewer 오픈
- [ ] Viewer에서 Escape / Enter → Viewer 닫힘 (Viewer Keys 로그 확인)
- [ ] Viewer 포커스가 없을 때 Return → viewWindow fallback 작동
- [ ] Viewer → 메인으로 돌아올 때 Grid에 포커스 복원되어 화살표로 아이템 이동 가능
- [ ] Ctrl+휠은 **UI-only** 썸네일 크기 변경 (엔진 재생성 없음)

---

원하면 이 문서에 **자동화된 체크 스크립트**(간단한 list of steps + expected logs)나, 각 핸들러별 `qmlDebug` 트레이스를 추가하는 방법(임시)을 더 적어둘게요.
