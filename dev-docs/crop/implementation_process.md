크롭 기능을 직접 구현하면서 이해하려면, 작은 단위로 나누어 UI → 상태 → 연산 → 저장/되돌리기 순서로 진행하면 좋습니다. 아래 순서를 추천합니다.

1. 현재 구조 읽기
image_viewer/crop 폴더 파일 구성과 주요 클래스/함수 역할을 빠르게 훑기.
crop_state/crop_overlay/crop_dialog 등 이름별 책임을 메모.

2. 최소 실행 경로 확보
앱을 띄운 뒤, 크롭 진입·완료·취소 플로우를 한 번 실제로 밟아보고, 콘솔 로그(임시)로 흐름을 확인.

3. 상태 관리 파악/정의
크롭 시작 시 필요한 상태(원본 이미지, 선택 영역 좌표/비율, 스케일, 회전 등)를 구조화.
상태를 어디에 보관하는지 확인하고, 없다면 CropState 같은 구조체/데이터클래스로 정리.

4. 선택 영역 입력 구현
마우스 드래그로 사각형 선택: press→move→release 이벤트 처리.
선택 영역 스냅/제한(예: 이미지 경계, 비율 고정) 로직을 분리된 함수로 구현.

5. 시각적 오버레이 구현
선택 영역 박스와 핸들(모서리/변)을 그리고, 리사이즈/이동 시 UI 업데이트.
확대/축소/스크롤 시 좌표 변환(뷰 좌표 ↔ 이미지 좌표) 확인.

6. 크롭 연산 구현
확정된 선택 영역을 이미지 좌표로 변환 후, 실제 크롭 연산 함수 분리(crop_image(image, rect) 형태).
썸네일/미리보기용 다운스케일 버전과 최종 저장용 원본 해상도를 구분.

7. 적용·취소 플로우 연결
“적용” 버튼 → 크롭 결과를 뷰어에 반영하고 캐시에 저장, undo/redo가 있다면 히스토리에 기록.
“취소” → 상태 초기화, 오버레이 제거.

8. 키보드/단축키·UX 보강
Esc로 취소, Enter로 적용, Shift로 비율 고정 등 단축키 연결.
상태 표시(오버레이/상태바 텍스트)로 현재 모드와 선택 영역 정보 제공.

9. 에지 케이스 테스트
매우 큰 이미지, 작은 선택 영역, 회전/줌 상태, 비정상 드래그(역방향), 비율 고정 on/off.
선택 영역이 없는 상태에서 적용 버튼을 눌렀을 때의 처리.

10. 리팩터링/주석
이벤트 핸들러와 순수 로직 분리, 공용 좌표 변환 헬퍼 정리.
테스트 가능하도록 크롭 연산을 UI와 분리.



현재 코드 기준 크롭 기능 흐름과 주요 클래스/함수는 아래와 같습니다.

### 백엔드 (pyvips 기반)
- `validate_crop_bounds(img_width, img_height, crop)` : 크롭 사각형이 이미지 내부인지 검증. @image_viewer/crop/crop.py#28-47
- `apply_crop_to_file(source_path, crop, output_path)` : pyvips로 원본을 열고 bounds 검사 후 `crop()` → 파일 저장. 캐시 제한도 함께 설정. @image_viewer/crop/crop.py#49-101
- `image_viewer.crop.__init__` : 위 함수들을 패키지 공개 API로 export. UI 의존 없음. @image_viewer/crop/__init__.py#1-35

### 워크플로 브리지
- `start_crop_workflow(viewer)` : 현재 표시 중인 이미지 경로/캐시된 pixmap을 가져와 `CropDialog` 실행. 사용자가 저장을 누르면 `save_cropped_file` 호출. @image_viewer/crop/crop_operations.py#23-60
- `save_cropped_file(viewer, source_path, crop_rect, output_path)` : `apply_crop_to_file`로 실제 저장, 성공/실패 메시지 표시, 엔진 prefetch 호출로 캐시 갱신 시도. @image_viewer/crop/crop_operations.py#62-105

### UI 다이얼로그
- `CropDialog(QDialog)` : 선택/프리뷰/저장 UI. 좌우 패널(줌·프리셋 / 행동 버튼)과 중앙 `QGraphicsView` 구성. @image_viewer/crop/ui_crop.py#181-401
  - `_apply_zoom_mode(mode)` : fit vs actual 전환. @image_viewer/crop/ui_crop.py#462-476
  - `_apply_preset(ratio)` : 선택 영역에 비율 고정 적용. @image_viewer/crop/ui_crop.py#477-481
  - `_on_preview()` / `_on_cancel_preview()` : 현재 선택 영역으로 미리보기 교체, 복원. @image_viewer/crop/ui_crop.py#498-537
  - `_on_save()` : 파일 저장 경로 받기만 하고, 사각형/경로를 `get_save_info()`로 전달(실제 저장은 operations가 처리). @image_viewer/crop/ui_crop.py#538-570
  - `keyPressEvent` : ESC로 취소/미리보기 해제, Enter로 프리뷰. @image_viewer/crop/ui_crop.py#572-586

### 선택 영역 그래픽
- `SelectionRectItem(QGraphicsRectItem)` : 드래그/핸들 리사이즈/이동/히트 테스트/커서 관리 담당. 이미지 위에 올라가는 선택 박스. @image_viewer/crop/ui_crop_selection.py#16-524
  - 내부 `_HandleItem` : 8개 핸들의 마우스/hover 이벤트, 커서 전환. @image_viewer/crop/ui_crop_selection.py#37-229
  - `hit_test(pos)` : 현재 포인터가 어느 핸들/내부/외부인지 판별. @image_viewer/crop/ui_crop_selection.py#258-295
  - `_handle_hover_*`, `hoverMoveEvent` : 커서/오버레이 업데이트. @image_viewer/crop/ui_crop_selection.py#392-513
  - `resize_handle_to(...)` 등 크기 변경 로직은 하단부(출력 생략된 영역)에 이어짐.

### 상호작용 흐름 요약
1. 뷰어에서 크롭 명령 → `start_crop_workflow`가 현재 이미지 캐시 픽스맵으로 `CropDialog` 생성/실행.
2. 다이얼로그에서 `SelectionRectItem`으로 영역을 잡고, 필요 시 프리셋/줌을 적용.
3. 저장 버튼 → 다이얼로그는 사각형과 경로만 반환; `save_cropped_file`이 pyvips 크롭/저장 수행, 성공 시 메시지 및 엔진 캐시 갱신.

이 구조를 따라가며 이벤트 흐름(SelectionRectItem drag/hover → CropDialog preview/save → crop_operations → crop.py)을 직접 수정/실험하면 이해가 빠를 것입니다. 궁금한 특정 함수나 미완성/보완하고 싶은 부분이 있으면 알려주세요.