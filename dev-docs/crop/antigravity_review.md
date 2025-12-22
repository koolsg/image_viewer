1. 커서 제어 권한의 분산 (Authority of Cursor Control)
가장 눈에 띄는 문제는 **"누가 커서를 결정하는가?"**에 대한 권한이 여러 곳에 흩어져 있다는 점입니다.

현상:
_HandleItem: 핸들 위에 있을 때 커서를 변경합니다.
SelectionRectItem: 본체 위에 있을 때 hit_test를 통해 가장자리 커서를 변경하거나 이동(OpenHand) 커서로 변경합니다.
CropDialog: _CropCursorResetFilter라는 별도의 이벤트 필터를 뷰포트에 설치하여, 마우스가 영역을 벗어날 때 강제로 커서를 초기화(unset)하려고 시도합니다.
문제점:
Band-aid Fix: _CropCursorResetFilter의 존재 자체가 문제입니다. 이는 내부 아이템들(SelectionRectItem, _HandleItem)이 자신의 영역을 벗어났을 때 커서 상태를 올바르게 복구하지 못한다는 것을 전제로 한 "땜질식 처방"입니다.
Race Condition: 뷰의 이벤트 처리와 아이템의 hoverLeave 간에 커서 설정이 경합할 수 있습니다. 예를 들어, 아이템은 커서를 끄려는데 필터가 먼저 개입하거나 그 반대의 경우가 생길 수 있습니다.
개선 방향:
_CropCursorResetFilter를 제거하고, SelectionRectItem과 _HandleItem의 hoverLeaveEvent가 확실하게 책임을 지도록 해야 합니다. 커서 제어의 권한은 해당 UI 요소(Item)에게 일임하는 것이 Qt의 구조와 맞습니다.
2. Hit Test와 실제 동작의 불일치 (Structure & Consistency)
SelectionRectItem의 구조를 보면, 리사이즈 기능을 수행하는 **실제 객체(_HandleItem)**와 이를 흉내 내는 **가상 로직(hit_test)**이 공존하고 있습니다.

현상:
_HandleItem은 실제 QGraphicsRectItem으로 존재하며, 클릭 시 리사이즈 동작(resize_handle_to)을 수행합니다.
반면 SelectionRectItem의 hoverMoveEvent는 별도의 hit_test 메서드를 호출하여 수학적으로 가장자리 여부를 판단하고 커서를 바꿉니다.
위험 요소 (The Lie):
만약 hit_test가 "여기는 모서리야(TopLeft)"라고 판단해서 커서를 대각선 화살표로 바꿨는데, 마우스 위치가 실제 _HandleItem의 영역 위가 아니라면 어떻게 될까요?
사용자는 "리사이즈가 되겠구나" 생각하고 클릭하지만, 실제로는 SelectionRectItem의 mousePressEvent가 호출되어 **"이동(Move)"**이 시작될 것입니다. (클릭 이벤트는 _HandleItem이 받아야 리사이즈가 되기 때문입니다)
즉, UI(커서)가 사용자에게 거짓말을 하는 상황이 발생할 수 있습니다.
구조적 제안:
SelectionRectItem의 hit_test 로직을 제거하거나, hit_test가 참인 영역은 반드시 _HandleItem의 영역과 정확히 일치하도록(혹은 _HandleItem이 그 영역을 완전히 덮도록) 해야 합니다.
가장 깔끔한 것은 SelectionRectItem은 "이동"만 담당하고, 가장자리 감지 및 리사이즈는 전적으로 자식 아이템인 핸들에게 위임하는 것입니다.
3. 좌표계의 이중 관리 (Shared Truth Problem)
SelectionRectItem이 _view_rect(뷰포트 기준 좌표)와 _parent_rect(이미지 기준 좌표)를 동시에 관리하며 동기화하려 노력하고 있습니다.

관점:
이는 줌(Zoom) 상태에서도 핸들의 크기나 선 두께를 일정하게 유지하거나, 픽셀 퍼펙트한 렌더링을 위한 의도로 보입니다.
하지만 _updating_parent_from_view 같은 플래그를 써서 루프를 막는 방식은 코드를 복잡하게 하고 버그를 유발하기 쉽습니다.
가능하면 Qt의 ItemIgnoresTransformations 플래그를 활용하거나, paint 메서드에서만 뷰 스케일을 참조하여 그리는 방식(Cosmetic Pen 등)으로 단순화할 수 있는지 검토가 필요합니다.

---

GPT's respeonse:

1. 커서 권한 단일화 및 뷰포트 리셋 필터 제거 준비
- ui_crop.py CropDialog(뷰포트 필터 설치부), _CropCursorResetFilter
- image_viewer/ui_crop.py → SelectionRectItem/_HandleItem hoverEnter/Move/Leave, mouseRelease 경로 재점검
- 테스트: test_cursor_behavior.py 일체

2. hit-test를 실제 핸들 동작과 정합화
- ui_crop.py SelectionRectItem.hit_test, hoverMoveEvent, _HandleItem
- 옵션 A: 엣지/코너 리사이즈 커서는 핸들에만 위임(아이템은 MOVE/NONE만)
- 옵션 B: 핸들의 히트 영역(보이지 않는 확장)을 엣지 존까지 넓혀 커서/클릭 일치
- 테스트: test_cursor_behavior.py, test_selection_handles.py

3. 단일 좌표계로 간소화(부모/원본 좌표를 진실원)
ui_crop.py _view_rect/_parent_rect 동기화 로직 제거/축소, setRect, resize_handle_to, 드래그 offset 매핑 정리
상호 변환은 필요 시 계산(캐시 최소화), 가드 플래그 패턴 축소
테스트: test_selection_box_ui.py, test_crop_dialog.py

4. 확대/축소에서도 일관된 조작성 확보
ui_crop.py _HandleItem(크기/플래그), 테두리 펜/그리드
핸들에 ItemIgnoresTransformations 고려, 선택선은 cosmetic pen 사용 검토
부작용(히트·좌표 매핑) 점검 후 미세조정
테스트 영향 없음(수동 검증 위주)

5. 모달 최대화 폴백 유지·단순화
ui_crop.py showEvent 내 try_maximize/fallback_if_not_maximized 정리
현재 폴백 전략 유지하되 분기 가볍게(가용 geometry 기반)
테스트: test_crop_fullscreen.py

6. 로깅 소음 관리와 전이 로그 안정화
ui_crop.py 드래그/전이 로그 게이트(디버그 시에만), 중복 로그 억제
테스트: test_selection_box_ui.py(전이 로그 기대치)