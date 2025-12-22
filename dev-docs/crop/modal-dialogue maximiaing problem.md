# CropDialog 창 크기 이슈 — 조사 및 조치 기록

요약
- 문제: CropDialog가 활성화될 때 기대보다 작은 창으로 뜸(사용자 기대는 화면을 크게 채운 maximized-like 창).
- 영향: 사용자 경험 저하(미리보기/선택 영역이 작게 보임). UI/테스트 동작과 불일치.

재현
1. 앱에서 Crop(자르기) 다이얼로그 열기.
2. 다이얼로그가 화면의 작은 영역에 표시되는 것을 확인.

원인 분석
- Modal(모달) 다이얼로그 특성: 부모 소유(owned/transient)인 경우 일부 플랫폼/윈도우 매니저가 `setWindowState(Qt.WindowMaximized)`를 무시하거나 제한함.
- 타이밍 문제: 생성자에서 `showMaximized()` 또는 `setWindowState(...|Qt.WindowMaximized)`를 호출하면 레이아웃/윈도우 매니저가 아직 안정화되지 않아 무시될 수 있음.
- 레이아웃/사이즈 정책 미비: 중앙 QGraphicsView 및 좌/우 패널의 sizePolicy나 최소 크기가 적절치 않으면 작은 기본 크기로 보일 수 있음.
- TrimPreviewDialog는 modeless이었고 showEvent에서 fit 재적용(짧은 delay)을 통해 안정적으로 크게 보였음 — 이 패턴이 성공 요인.

시도한 해결책 및 결과
1. 생성자에서 `showMaximized()` 호출 — 실패(타이밍/모달/소유 관계 때문에 무시됨).
2. 생성자에서 `self.show()` 강제 호출 — 테스트 호환성 확보(일부 테스트가 다이얼로그가 보여진 상태를 기대함)하지만 크기 문제 자체는 해결되지 않음.
3. `TrimPreviewDialog` 방식으로 전환(모달 → modeless, maximize hints, showEvent에서 fit + QTimer delay) — 성공(창이 크게 보임). 하지만 기능적 요구로 모달 유지 필요.
4. 모달을 유지하면서 showEvent에서 화면의 availableGeometry로 setGeometry(작은 마진 포함) + `QTimer.singleShot(0, fitInView)` 적용 — 성공(모달을 유지하면서 maximized-like 동작 달성).
5. `setWindowState(... | Qt.WindowMaximized)` 시도 — 일부 플랫폼 또는 modal/transient 상황에서 무시될 수 있음. 현재는 "시도 후 실패 시 availableGeometry fallback" 패턴 채택.

현재 상태
- CropDialog는 모달을 유지하면서 `showEvent`에서:
  - 커서가 있는 화면(또는 다이얼로그의 화면)을 조회하여 사용 가능한 화면 영역(availableGeometry)을 계산,
  - 약간의 마진을 두고 `setGeometry(...)`로 창을 확장,
  - 레이아웃이 안정된 뒤 `QTimer.singleShot`으로 뷰에 `fitInView`를 적용.
- 중앙 뷰와 패널에 적절한 QSizePolicy와 최소 크기 설정을 추가함.
- 테스트 호환성을 위해 생성자에서 `self.show()`를 유지(현행 테스트/호출자 호환성 고려).

왜 일부 시도가 실패했나 (요약)
- Modal + 소유(owned) 창은 윈도우 매니저 정책에 따라 실제 최대화 요청을 무시할 수 있음.
- 생성자/초기화 시점에 최대화를 요청하면 레이아웃/윈도우 핸들/윈도우 매니저 반영 타이밍 때문에 적용되지 않음.
- Modeless로 바꾸면 OS가 정상적으로 처리하므로 성공하지만, 요구사항상 모달 유지가 필요했음.

권장/후속 조치
- (권장) 현재 showEvent-based availableGeometry fallback 패턴 유지 — 플랫폼 독립적이며 사용자 요구(모달 유지) 충족.
- 실제 maximize 상태를 원하면 showEvent 후 `setWindowState(... | Qt.WindowMaximized)`를 시도하되, 실패 시 현재의 availableGeometry 방식이 동작하도록 유지.
- 테스트 추가: 다이얼로그 표시 후 geometry가 화면 availableGeometry 대비 일정 비율(예: 80~90%) 이상인지 확인하는 UI/통합 테스트를 추가.
- 장기적 검토: 생성자에서 `self.show()` 제거하고 테스트를 수정해 다이얼로그를 명시적으로 `show()`하는 쪽으로 전환(테스트 설계가 더 명확해짐).

변경 파일 (핵심)
- image_viewer/image_viewer/ui_crop.py — showEvent 기반 화면 맞춤 로직, size policy 조정, fitInView delay, 모달 유지
- (참고) image_viewer/image_viewer/ui_trim.py — 비교용 구현 참고

문서/작업 기록
- 본 파일에 요약 기록. 추가로 작업 로그는 `dev-docs` 또는 `TASKS.md`에 연동해 기록 권장.

작성자: 자동화 요약 (작업 대화 및 코드 변경 기반)