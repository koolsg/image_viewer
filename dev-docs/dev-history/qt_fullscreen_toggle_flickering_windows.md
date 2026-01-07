# Qt/PySide6 Fullscreen Toggle Flickering Issue on Windows

윈도우 환경에서 Qt/PySide6 애플리케이션의 전체 화면 토글 시 발생하는 깜박임 현상에 대한 조사 결과입니다.

## 현상 설명
전체 화면 모드에서 일반 화면으로 돌아갈 때, 중간에 작은 화면이 잠시 나타나면서 깜박이는 현상이 발생합니다. 이는 윈도우 매니저의 애니메이션 효과나 Qt의 window state 전환 메커니즘과 관련이 있습니다.

## Qt 공식 문서 분석
- `QWidget.showFullScreen()`: 플랫폼 특정 고려사항이 있지만 공식 문서에서 flickering 문제 직접 언급 없음
- `QWindow` fullscreen 상태: `setWindowStates(Qt::WindowFullScreen)` + `show()` 조합
- 윈도우 매니저의 기본 동작에 따라 fullscreen ↔ normal 전환 시 애니메이션 적용 가능

## 커뮤니티 보고된 이슈 및 해결 방안

### 1. QApplication.setAttribute(Qt.AA_NativeWindows)
**출처**: Qt Forum - Borderless Window Flickering while resizing

- **문제**: Frameless/borderless window의 resizing 시 flickering
- **해결**: `QApplication.setAttribute(Qt.AA_NativeWindows, True)` 사용
- **설명**: Alien widget 대신 native window 강제하여 painting flickering 감소
- **주의**: 다른 컴포넌트에 부작용 가능성 있음

```python
from PySide6.QtWidgets import QApplication
app = QApplication([])
app.setAttribute(Qt.AA_NativeWindows, True)
```

### 2. Visibility 변경 지연시키기
**출처**: QtCentre Forum - Flickering when change QWidget window state

- **문제**: `showMaximized()` ↔ `showFullScreen()` 전환 시 flickering
- **해결**: QTimer를 사용해 visibility 변경을 이벤트 루프 다음으로 지연
- **예시**: `QTimer.singleShot(0, lambda: widget.setVisible(False))`

### 3. OpenGL 위젯 관련 이슈
**출처**: Qt Bug QTBUG-51093

- **문제**: QMainWindow에 OpenGL 자식 위젯이 있을 때 `showFullScreen()` 호출 시 flickering
- **특징**:
  - 멀티스크린 환경에서 모든 화면 깜박임
  - 주 화면이 아닌 보조 화면에서는 발생하지 않음
- **영향**: OpenGL 기반 애플리케이션에서 특히 문제

### 4. 기타 보고된 사례
- **napari 프로젝트**: Windows에서 Toggle Full Screen 시 window Maximize와 충돌
- **pyqtgraph**: GLViewWidget 사용 시 `showFullScreen()`에서 UI flickering

## 플랫폼 특정 동작
- Windows fullscreen 전환 시 윈도우 매니저 자동 애니메이션 효과 적용 가능
- `setWindowState()` 대신 `setGeometry()` 직접 사용 대안 제시되나 표준 방식 아님

## 권장 베스트 프랙티스

### 1. AA_NativeWindows 속성 적용
```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
app.setAttribute(Qt.AA_NativeWindows, True)
```

### 2. 이벤트 기반 UI 변경
```python
def showEvent(self, event):
    super().showEvent(event)
    # UI 요소 visibility 변경을 여기서 처리

def hideEvent(self, event):
    super().hideEvent(event)
    # 필요한 정리 작업
```

### 3. QTimer를 활용한 지연 실행
```python
from PySide6.QtCore import QTimer

# flickering 방지를 위한 지연
QTimer.singleShot(0, self.adjust_ui_elements)
```

### 4. OpenGL 사용 시 고려사항
- Fullscreen 전환 전 OpenGL 위젯 숨기기/제거 고려
- 멀티모니터 환경에서 테스트 필수

### 5. 환경 설정 검토
- Windows "시각 효과" 설정이 fullscreen 전환에 영향
- 애플리케이션 실행 시 `--platform windows:darkmode=0` 등의 옵션 테스트

## 결론
이 이슈는 Qt의 윈도우 매니저 상호작용과 밀접한 관련이 있어 완벽한 해결보다는 완화 방안 적용이 현실적입니다. 애플리케이션의 구체적인 구현 패턴과 사용된 위젯 타입에 따라 다른 접근 방식이 필요할 수 있습니다.

## 참고 자료
- Qt Forum: Borderless Window Flickering
- QtCentre: QWidget window state flickering
- Qt Bug Reports: QTBUG-51093
- GitHub Issues: napari, pyqtgraph 관련 flickering 이슈
