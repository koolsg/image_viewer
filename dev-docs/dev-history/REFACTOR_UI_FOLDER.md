# UI 폴더 분리 리팩토링 계획

## 현재 구조 분석

### image_viewer/ 파일 분류

**UI 컴포넌트 (ui/ 폴더로 이동 대상):**
```
ui_canvas.py          # 메인 이미지 캔버스 (ImageCanvas)
ui_explorer_grid.py   # 썸네일 그리드 위젯 (ThumbnailGridWidget)
ui_explorer_tree.py   # 폴더 트리 위젯 (FolderTreeWidget)
ui_menus.py           # 메뉴바 빌더 (build_menus)
ui_settings.py        # 설정 다이얼로그 (SettingsDialog)
ui_trim.py            # 트림 UI (TrimProgressDialog, TrimBatchWorker)
ui_convert_webp.py    # WebP 변환 다이얼로그 (WebPConvertDialog)
status_overlay.py     # 상태 오버레이 (StatusOverlayBuilder)
styles.py             # 테마/스타일 (apply_theme)
busy_cursor.py        # 바쁨 커서 컨텍스트 매니저
```

**비즈니스 로직 (현재 위치 유지):**
```
main.py               # 메인 애플리케이션 (ImageViewer)
explorer_mode_operations.py  # Explorer 모드 로직
file_operations.py    # 파일 작업 로직
trim_operations.py    # 트림 워크플로우 로직
trim.py               # 트림 알고리즘 (pyvips)
webp_converter.py     # WebP 변환 로직
```

**유틸리티/설정 (현재 위치 유지):**
```
logger.py             # 로깅
settings_manager.py   # 설정 관리
__init__.py           # 패키지 초기화
__main__.py           # 엔트리포인트
```

**데이터/처리 (image_engine/ 이미 분리됨):**
```
image_engine/         # 이미지 처리 엔진
```

---

## 제안 구조

```
image_viewer/
├── __init__.py
├── __main__.py
├── main.py                    # 메인 애플리케이션
├── logger.py
├── settings_manager.py
├── settings.json
│
├── ui/                        # UI 컴포넌트 패키지 (NEW)
│   ├── __init__.py            # UI 모듈 re-export
│   ├── canvas.py              # ImageCanvas (ui_canvas.py에서)
│   ├── explorer_grid.py       # ThumbnailGridWidget
│   ├── explorer_tree.py       # FolderTreeWidget
│   ├── menus.py               # build_menus
│   ├── settings_dialog.py     # SettingsDialog
│   ├── trim_dialog.py         # TrimProgressDialog, TrimBatchWorker
│   ├── convert_dialog.py      # WebPConvertDialog
│   ├── status_overlay.py      # StatusOverlayBuilder
│   ├── styles.py              # apply_theme
│   └── busy_cursor.py         # busy_cursor context manager
│
├── operations/                # 비즈니스 로직 (선택적)
│   ├── __init__.py
│   ├── explorer.py            # explorer_mode_operations.py
│   ├── file.py                # file_operations.py
│   └── trim.py                # trim_operations.py
│
├── image_engine/              # 데이터/처리 (이미 분리됨)
│   └── ...
│
└── libvips/                   # 외부 라이브러리
```

---

## 영향 분석

### 수정이 필요한 Import 경로

| 현재 경로 | 새 경로 | 사용처 |
|-----------|---------|--------|
| `from .ui_canvas import ImageCanvas` | `from .ui.canvas import ImageCanvas` | main.py, explorer_mode_operations.py |
| `from image_viewer.ui_canvas import ImageCanvas` | `from image_viewer.ui.canvas import ImageCanvas` | main.py |
| `from image_viewer.ui_explorer_grid import ThumbnailGridWidget` | `from image_viewer.ui.explorer_grid import ThumbnailGridWidget` | explorer_mode_operations.py |
| `from image_viewer.ui_explorer_tree import FolderTreeWidget` | `from image_viewer.ui.explorer_tree import FolderTreeWidget` | explorer_mode_operations.py |
| `from image_viewer.ui_menus import build_menus` | `from image_viewer.ui.menus import build_menus` | main.py |
| `from image_viewer.ui_settings import SettingsDialog` | `from image_viewer.ui.settings_dialog import SettingsDialog` | main.py |
| `from image_viewer.ui_convert_webp import WebPConvertDialog` | `from image_viewer.ui.convert_dialog import WebPConvertDialog` | main.py |
| `from .ui_trim import TrimBatchWorker, TrimProgressDialog` | `from .ui.trim_dialog import ...` | trim_operations.py |
| `from image_viewer.status_overlay import StatusOverlayBuilder` | `from image_viewer.ui.status_overlay import ...` | main.py |
| `from image_viewer.styles import apply_theme` | `from image_viewer.ui.styles import apply_theme` | main.py, trim_operations.py |
| `from .busy_cursor import busy_cursor` | `from .ui.busy_cursor import busy_cursor` | main.py, file_operations.py, ui_explorer_grid.py |

### 내부 의존성 (ui/ 내부)

- `ui/explorer_grid.py` → `ui/busy_cursor.py` (busy_cursor)
- `ui/explorer_grid.py` → `file_operations.py` (delete_files_to_recycle_bin)
- `ui/explorer_grid.py` → `image_engine/fs_model.py` (ImageFileSystemModel)

---

## 장단점 분석

### 장점
1. **명확한 구조**: UI 컴포넌트가 한 폴더에 모여 있어 찾기 쉬움
2. **관심사 분리**: UI / 비즈니스 로직 / 데이터 처리 명확히 구분
3. **확장성**: 새 UI 컴포넌트 추가 시 위치가 명확
4. **일관성**: image_engine/ 패턴과 동일한 구조

### 단점
1. **작업량**: 10개 파일 이동 + 다수의 import 수정
2. **위험성**: import 경로 실수 시 런타임 에러
3. **하위 호환성**: 외부에서 import하는 코드가 있다면 깨짐
4. **복잡도 증가**: 상대 import 경로가 길어짐 (`from ..ui.canvas`)

---

## 권장 사항

### Option A: 전체 UI 폴더 분리 (권장하지 않음)
- 작업량 대비 효과가 크지 않음
- 현재 `ui_` prefix로 충분히 구분됨
- 순환 import 위험 증가

### Option B: 점진적 분리 (권장)
1. **Phase 1**: `ui/` 폴더 생성, re-export 파일만 추가
   - 기존 파일 위치 유지
   - `ui/__init__.py`에서 re-export
   - 새 코드는 `from image_viewer.ui import ...` 사용 가능

2. **Phase 2**: 필요 시 개별 파일 이동
   - 리팩토링 필요한 파일만 선택적으로 이동
   - 하위 호환성 유지 (기존 경로에 re-export)

### Option C: 현재 구조 유지 (가장 안전)
- `ui_` prefix가 이미 명확한 네이밍 컨벤션
- image_engine/ 분리로 주요 아키텍처 개선 완료
- 추가 분리는 실제 필요성 발생 시 진행

---

## 결론

**현재 구조 유지를 권장합니다.**

이유:
1. `ui_` prefix로 UI 파일이 이미 명확히 구분됨
2. image_engine/ 분리로 핵심 아키텍처 개선 완료
3. 작업량 대비 실질적 이점이 적음
4. import 경로 변경으로 인한 버그 위험

만약 진행한다면 **Option B (점진적 분리)**를 권장:
- 먼저 `ui/__init__.py` re-export만 추가
- 실제 파일 이동은 나중에 필요 시 진행

---

## 실행 계획 (Option B 선택 시)

### Phase 1: Re-export 레이어 추가 (안전)
```python
# image_viewer/ui/__init__.py
from image_viewer.ui_canvas import ImageCanvas
from image_viewer.ui_explorer_grid import ThumbnailGridWidget
from image_viewer.ui_explorer_tree import FolderTreeWidget
from image_viewer.ui_menus import build_menus
from image_viewer.ui_settings import SettingsDialog
from image_viewer.ui_trim import TrimBatchWorker, TrimProgressDialog
from image_viewer.ui_convert_webp import WebPConvertDialog
from image_viewer.status_overlay import StatusOverlayBuilder
from image_viewer.styles import apply_theme
from image_viewer.busy_cursor import busy_cursor

__all__ = [
    "ImageCanvas",
    "ThumbnailGridWidget",
    "FolderTreeWidget",
    "build_menus",
    "SettingsDialog",
    "TrimBatchWorker",
    "TrimProgressDialog",
    "WebPConvertDialog",
    "StatusOverlayBuilder",
    "apply_theme",
    "busy_cursor",
]
```

### Phase 2: 점진적 파일 이동 (선택적)
- 각 파일 이동 시 기존 위치에 re-export 유지
- 모든 import가 새 경로로 전환된 후 re-export 제거

---

## 예상 작업량

| Phase | 작업 | 예상 시간 | 위험도 |
|-------|------|-----------|--------|
| Phase 1 | ui/__init__.py 생성 | 10분 | 낮음 |
| Phase 2 | 파일 이동 + import 수정 | 1-2시간 | 중간 |
| 테스트 | pyright + ruff + 수동 테스트 | 30분 | - |

**총 예상 시간**: 2-3시간 (Phase 2 포함 시)
