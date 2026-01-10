# QML Performance Guide

## 1. 핵심 결론

| 구분 | 설명 |
|------|------|
| **주 원인** | QML 엔진 + Qt Quick 초기화 비용 (Python이 아님) |
| **정상 패턴** | 첫 실행 0.5~1.5초, 이후 빠름 |
| **문제 패턴** | 창 뜨기 전 이미지 디코딩, Python↔QML 왕복 남발 |

---

## 2. QML 초기화 비용의 4대 원인

### 2.1 QML 엔진 초기화
- `QQmlEngine` 생성 → QML 파서 실행 → 바인딩 트리 구성 → JS 엔진 초기화
- 위젯(Qt Widgets)은 C++에 정적 준비되어 있어 가벼움

### 2.2 Qt Quick Controls 로딩
- 스타일(Material, Fusion) 초기화, 폰트 로딩, 테마 계산
- **Material 스타일은 생각보다 무거움**

### 2.3 QML ↔ Python 브리지 비용
- `setContextProperty`, `qmlRegisterType` 사용 시
- GIL + C++ ↔ Python 왕복 발생

### 2.4 이미지 뷰어 특유 비용
- 이미지 디코더 로딩 (PNG, JPEG 플러그인)
- OpenGL / RHI 초기화, GPU 컨텍스트 생성
- 씬 그래프 + 렌더러 초기화

---

## 3. 이미지 뷰어에서 유독 느려지는 패턴

### 3.1 시작하자마자 큰 이미지 처리
```qml
// ❌ 느린 패턴 - 초기화 타이밍과 겹침
Image {
    source: bigImagePath
    fillMode: Image.PreserveAspectFit
}

// ✅ 개선 - 창 뜬 뒤 로딩
Component.onCompleted: image.source = realPath
```

### 3.2 `Image` vs `QQuickImageProvider` 남용
- Python에서 매번 가공한 이미지 전달 시 픽셀 데이터 복사 발생
- 초기 화면에는 정적 QML Image 사용

### 3.3 Binding 폭탄
```qml
// ❌ 병목 - 재계산 연쇄 발생
scale: Math.min(parent.width / image.width, parent.height / image.height)

// ✅ 개선 - Python에서 계산 후 고정 값 전달
```

### 3.4 Controls + 애니메이션 동시 초기화
- `QtQuick.Controls`, `Behavior`, `NumberAnimation`, `States` 동시 사용 시 프레임 밀림

---

## 4. 체감 개선 체크포인트

| 방법 | 내용 |
|------|------|
| **QML 미리 로드** | 초기화 전에 필요한 타입 한 번에 로드 |
| **Python 접근 최소화** | 첫 화면은 순수 QML만 사용 |
| **Controls 줄이기** | `QT_QUICK_CONTROLS_STYLE=Basic` 활용 |
| **Splash 전략** | 가벼운 QML 먼저 띄우고, 백그라운드에서 준비 |

---

## 5. 첫 실행 프로파일링 방법

### 5.1 Qt 로깅 (가장 먼저)
```powershell
set QT_LOGGING_RULES=qt.scenegraph.general=true
```
- `scenegraph initialized`, `shader compilation` 로그 확인

### 5.2 QML Profiler (Qt Creator)
- Analyze → QML Profiler
- Startup Time, Binding Evaluation, First Frame 타이밍 확인

### 5.3 Python 타이밍 로그
```python
import time
t0 = time.perf_counter()

engine = QQmlApplicationEngine()
print("engine:", time.perf_counter() - t0)

engine.load(url)
print("load:", time.perf_counter() - t0)
```

### 5.4 씬 그래프 상태 확인
```bash
QSG_INFO=1  # 셰이더 캐시 생성 여부 확인
```

### 5.5 "첫 실행만 느린지" 확인
- 앱 종료 후 다시 실행
- 두 번째 실행이 빠르면 → 정상 (초기화 비용)
- 매번 느리면 → 구조 문제

---

## 6. 추천 구조 (체감 최적화)

```
1. 가벼운 QML 루트 표시
2. GPU 초기화 완료 대기
3. 이미지 로딩 시작
4. 부가 UI 활성화
```

이 순서만 지켜도 체감 속도가 크게 달라집니다.

---

## 7. 정상 vs 문제 패턴 구분

### ✅ 정상적인 느림
- 첫 실행 0.5~1.5초
- 두 번째부터 빠름
- 창 뜬 뒤 이미지 로딩

### ❌ 구조적 문제
- 창이 안 뜬 상태에서 이미지 디코딩
- Python ↔ QML 왕복 남발
- 바인딩 폭탄
- Controls + 애니메이션 + 이미지 동시 초기화

