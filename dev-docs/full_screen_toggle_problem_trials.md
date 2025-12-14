# 전체화면 전환 문제 해결 과정

## 문제 상황
F11을 눌러 전체화면으로 전환했다가 다시 F11을 눌러 일반 모드로 전환할 때, 중간에 작은 윈도우 상태를 거쳤다가 원래 화면으로 바뀌는 문제 발생.

---

## 시도 1: geometry 복원 순서 변경

### 방법
`exit_fullscreen()` 함수에서 `restoreGeometry()`를 `setWindowState()` 이전에 호출하도록 순서 변경.

### 코드
```python
def exit_fullscreen(self):
    self.setUpdatesEnabled(False)
    prev_state = getattr(self, "_prev_state", Qt.WindowState.WindowMaximized)
    geom = getattr(self, "_prev_geometry", None)

    # Restore geometry first if available (before changing window state)
    if geom and not (prev_state & Qt.WindowState.WindowMaximized):
        with contextlib.suppress(Exception):
            self.restoreGeometry(geom)

    # Then set the window state
    self.setWindowState(prev_state)
    self.menuBar().setVisible(True)
    if hasattr(self, "fullscreen_action"):
        self.fullscreen_action.setChecked(False)
    self.setUpdatesEnabled(True)
    self.canvas.apply_current_view()
```

### 결과
❌ 실패 - 여전히 중간 단계를 거침

### 문제점
- `setWindowState()`와 `restoreGeometry()` 조합이 복잡함
- WindowState를 직접 조작하는 방식의 한계

---

## 시도 2: F11 키 바인딩 문제 해결

### 문제
F11 키 자체가 작동하지 않음.

### 원인
`keyPressEvent`의 첫 줄에서 `if not self.image_files: return`으로 이미지 파일이 없으면 바로 리턴하기 때문에 F11과 F5 키가 작동하지 않음.

### 해결 방법
F5와 F11 키를 이미지 파일 체크 이전에 처리하도록 변경.

### 코드
```python
def keyPressEvent(self, event):
    key = event.key()

    # F5 and F11 work even without images
    if key == Qt.Key.Key_F5:
        was_view_mode = getattr(self.explorer_state, "view_mode", True)
        self.toggle_view_mode()
        if was_view_mode:
            with contextlib.suppress(Exception):
                self.exit_fullscreen()
        return
    elif key == Qt.Key.Key_F11:
        self.toggle_fullscreen()
        return

    # Other keys require images to be loaded
    if not self.image_files:
        super().keyPressEvent(event)
        return
    # ... 나머지 키 처리
```

### 결과
✅ 성공 - F11 키가 작동함

---

## 시도 3: 단순화 - showNormal()/showFullScreen() 사용

### 방법
참고 파일(`scripts/full_screen_toggle.py`)을 보고 복잡한 WindowState 조작 대신 `showNormal()`과 `showFullScreen()` 사용.

### 코드
```python
def enter_fullscreen(self):
    # Save current geometry before entering fullscreen
    self._normal_geometry = self.geometry()
    self.menuBar().setVisible(False)
    self.showFullScreen()
    if hasattr(self, "fullscreen_action"):
        self.fullscreen_action.setChecked(True)
    self.canvas.apply_current_view()

def exit_fullscreen(self):
    # Exit fullscreen and restore previous geometry
    self.showNormal()
    if hasattr(self, "_normal_geometry") and not self._normal_geometry.isNull():
        self.setGeometry(self._normal_geometry)
    self.menuBar().setVisible(True)
    if hasattr(self, "fullscreen_action"):
        self.fullscreen_action.setChecked(False)
    self.canvas.apply_current_view()
```

### 결과
⚠️ 부분 성공 - 대부분의 경우 작동하지만 특정 상황에서 문제 발생

### 문제점
- ViewState 클래스의 불필요한 변수(`_prev_state`, `_prev_geometry`) 제거 필요

---

## 시도 4: 최대화 상태 감지 및 처리

### 문제
프로그램 시작 시 `showMaximized()`로 창을 띄우면, 첫 번째 전체화면 전환 시에만 중간에 작은 창이 나타남.

### 원인
최대화 상태에서 `geometry()`를 저장하면 최대화된 geometry가 저장되는데, 이게 정상 창 크기가 아님.

### 해결 방법
최대화 상태일 때는 geometry를 저장하지 않고, 복원 시 저장된 geometry가 없으면 `showMaximized()` 사용.

### 코드
```python
def enter_fullscreen(self):
    # Save current geometry before entering fullscreen (only if not maximized)
    if not self.isMaximized():
        self._normal_geometry = self.geometry()
    self.menuBar().setVisible(False)
    self.showFullScreen()
    if hasattr(self, "fullscreen_action"):
        self.fullscreen_action.setChecked(True)
    self.canvas.apply_current_view()

def exit_fullscreen(self):
    # Exit fullscreen and restore previous geometry
    if hasattr(self, "_normal_geometry") and not self._normal_geometry.isNull():
        # Restore to saved normal geometry
        self.showNormal()
        self.setGeometry(self._normal_geometry)
    else:
        # No saved geometry, just maximize
        self.showMaximized()
    self.menuBar().setVisible(True)
    if hasattr(self, "fullscreen_action"):
        self.fullscreen_action.setChecked(False)
    self.canvas.apply_current_view()
```

### 결과
✅ 성공 - 첫 번째 전환 시 문제 해결

---

## 시도 5: saveGeometry()/restoreGeometry() 사용

### 방법
`geometry()` 대신 `saveGeometry()`/`restoreGeometry()` 사용. 이 방법은 창의 위치, 크기뿐만 아니라 화면 정보도 함께 저장하므로 더 안정적.

### 코드 (scripts/full_screen_toggle.py)
```python
def toggle_fullscreen(self):
    if self.isFullScreen():
        print("Exiting fullscreen...")
        self.showNormal()
        if self.saved_geometry:
            self.restoreGeometry(self.saved_geometry)
            print("Restored geometry from saved state")
        else:
            print("No saved geometry, using default")
    else:
        if not self.isMaximized():
            self.saved_geometry = self.saveGeometry()
            print(f"Saved geometry before fullscreen")
        else:
            print("Window is maximized, not saving geometry")
        self.showFullScreen()
```

### 결과
✅ 성공 - 더 안정적인 복원

---

## 시도 6: 최대화 상태 기억 및 복원

### 문제
최대화 상태에서 전체화면으로 전환 후 복원 시, `showMaximized()`를 호출하면 내부적으로 먼저 normal 상태로 갔다가 maximize되어 깜빡임 발생.

### 해결 방법
1. 전체화면 진입 전 `isMaximized()` 상태를 별도 변수에 저장
2. 복원 시 저장된 상태에 따라 다르게 처리:
   - Maximized였던 경우: `setWindowState(Qt.WindowState.WindowMaximized)` 직접 사용
   - Normal이었던 경우: `setWindowState(Qt.WindowState.WindowNoState)` + `restoreGeometry()`

### 코드 (최종)
```python
def __init__(self):
    # ...
    self.saved_geometry = None
    self.was_maximized = False

def toggle_fullscreen(self):
    if self.isFullScreen():
        print("Exiting fullscreen...")

        if self.was_maximized:
            # Maximized 상태였던 경우 - setWindowState 직접 사용
            print("  Restoring to maximized state")
            self.setWindowState(Qt.WindowState.WindowMaximized)
        else:
            # Normal 상태였던 경우
            print("  Restoring to normal state")
            self.setWindowState(Qt.WindowState.WindowNoState)
            if self.saved_geometry:
                self.restoreGeometry(self.saved_geometry)
                print("  Restored saved geometry")
    else:
        print("Entering fullscreen...")

        # 현재 상태 저장
        self.was_maximized = self.isMaximized()
        print(f"  Current state - Maximized: {self.was_maximized}")

        # Normal 상태인 경우에만 geometry 저장
        if not self.was_maximized:
            self.saved_geometry = self.saveGeometry()
            print(f"  Saved geometry ({len(self.saved_geometry)} bytes)")
        else:
            print("  Maximized state, not saving geometry")

        self.setWindowState(Qt.WindowState.WindowFullScreen)
```

### 결과
✅ 완전 성공 - 모든 상황에서 깜빡임 없이 전환

---

## 추가 학습: Qt 라이브러리 차이

### PyQt5 vs PyQt6 vs PySide6

**Enum 형식 차이:**
- PyQt5: `Qt.Key_F11`
- PyQt6: `Qt.Key.Key_F11` (더 명확한 네임스페이스)
- PySide6: `Qt.Key.Key_F11`

**exec 함수:**
- PyQt5: `exec_()`
- PyQt6: `exec()` (더 pythonic)
- PySide6: `exec()`

**권장:**
PyQt6 또는 PySide6 사용 (더 최신, 더 나은 타입 힌팅, 더 깔끔한 API)

---

## 핵심 교훈

### 1. showMaximized() vs setWindowState()
- `showMaximized()`: 내부적으로 normal → maximized 전환 과정을 거침 (깜빡임 발생 가능)
- `setWindowState(Qt.WindowState.WindowMaximized)`: 직접 상태 전환 (깜빡임 없음)

### 2. geometry() vs saveGeometry()
- `geometry()`: 현재 창의 위치와 크기만 저장 (QRect)
- `saveGeometry()`: 창의 위치, 크기, 화면 정보 등을 포함한 완전한 상태 저장 (QByteArray)

### 3. 상태 관리의 중요성
- 전체화면 전환 전 상태(maximized/normal)를 명시적으로 저장
- 복원 시 저장된 상태에 따라 다른 복원 방법 사용

### 4. resize()로 maximize 구현
화면의 available geometry를 가져와서 수동으로 크기 조정 가능:
```python
screen = QApplication.primaryScreen()
available_geometry = screen.availableGeometry()  # 작업 표시줄 제외
self.setGeometry(available_geometry)
```

---

## 최종 권장 방법

```python
# 초기화
self.saved_geometry = None
self.was_maximized = False

# 전체화면 진입
def enter_fullscreen(self):
    self.was_maximized = self.isMaximized()
    if not self.was_maximized:
        self.saved_geometry = self.saveGeometry()
    self.setWindowState(Qt.WindowState.WindowFullScreen)

# 전체화면 종료
def exit_fullscreen(self):
    if self.was_maximized:
        self.setWindowState(Qt.WindowState.WindowMaximized)
    else:
        self.setWindowState(Qt.WindowState.WindowNoState)
        if self.saved_geometry:
            self.restoreGeometry(self.saved_geometry)
```

이 방법은:
- ✅ 깜빡임 없음
- ✅ 모든 상태(normal/maximized)에서 정확한 복원
- ✅ 간단하고 명확한 로직
- ✅ 멀티 모니터 환경에서도 안정적
