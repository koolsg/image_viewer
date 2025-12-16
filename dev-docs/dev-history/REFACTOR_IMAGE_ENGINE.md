# Refactoring Plan: Image Engine Architecture

## 상태: ✅ 완료 (2025-12-07)

모든 Phase가 성공적으로 완료되었습니다.

## 목표

UI와 데이터/처리 로직을 완전히 분리하여 **Image Engine**을 서버/백엔드로, **UI**를 클라이언트/프론트엔드로 구성

## 현재 문제점

### main.py의 과도한 책임 (800+ lines)
```
ImageViewer (main.py)
├─ 파일 시스템 관리 (fs_model)
├─ 이미지 디코딩 (loader, decoder)
├─ 캐시 관리 (pixmap_cache)
├─ UI 상태 (ViewState, TrimState, ExplorerState)
├─ 메뉴/액션
├─ 캔버스 제어
├─ 네비게이션 로직
├─ 설정 관리
└─ 모드 전환 로직
```

### 문제:
- 단일 클래스가 너무 많은 책임
- 디코딩/캐싱 로직이 UI와 혼재
- Trim/Converter가 viewer 내부에 직접 접근
- 테스트 어려움
- 코드 재사용 불가

## 목표 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    ImageEngine (서버/백엔드)                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │  fs_model   │ │   loader    │ │     pixmap_cache        ││
│  │ (파일시스템) │ │  (디코딩)   │ │       (캐시)            ││
│  └─────────────┘ └─────────────┘ └─────────────────────────┘│
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │   decoder   │ │ thumb_cache │ │    decoding_strategy    ││
│  │  (pyvips)   │ │ (썸네일DB)  │ │      (전략 패턴)        ││
│  └─────────────┘ └─────────────┘ └─────────────────────────┘│
│                                                             │
│  시그널: image_ready, folder_changed, thumbnail_ready       │
│  API: open_folder(), request_decode(), get_images(), etc.   │
└────────────────────────────┬────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
        │  main.py  │  │   trim    │  │ converter │
        │ (View UI) │  │ (Trim UI) │  │(Convert UI│
        └───────────┘  └───────────┘  └───────────┘
              │
    ┌─────────┼─────────┐
    │         │         │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐
│canvas │ │ menus │ │explorer│
│  (UI) │ │ (UI)  │ │  (UI)  │
└───────┘ └───────┘ └────────┘
```

## ImageEngine API 설계

```python
class ImageEngine(QObject):
    """이미지 처리 엔진 - 모든 데이터/처리 로직의 단일 진입점"""

    # ═══════════════════════════════════════════════════════════
    # 시그널 (UI에 알림)
    # ═══════════════════════════════════════════════════════════
    image_ready = Signal(str, QPixmap, object)      # path, pixmap, error
    folder_changed = Signal(str, list)              # folder_path, file_list
    thumbnail_ready = Signal(str, QIcon)            # path, icon
    file_list_updated = Signal(list)                # new file list
    decode_progress = Signal(str, int, int)         # path, current, total

    # ═══════════════════════════════════════════════════════════
    # 파일 시스템 API
    # ═══════════════════════════════════════════════════════════
    def open_folder(self, path: str) -> bool
        """폴더 열기. 성공 시 folder_changed 시그널 발생"""

    def get_current_folder(self) -> str
        """현재 열린 폴더 경로"""

    def get_image_files(self) -> list[str]
        """현재 폴더의 이미지 파일 목록 (정렬됨)"""

    def get_file_at_index(self, idx: int) -> str | None
        """인덱스로 파일 경로 반환"""

    def get_file_index(self, path: str) -> int
        """파일 경로로 인덱스 반환"""

    def get_file_count(self) -> int
        """이미지 파일 개수"""

    # ═══════════════════════════════════════════════════════════
    # 이미지 디코딩 API
    # ═══════════════════════════════════════════════════════════
    def request_decode(self, path: str,
                       target_size: tuple[int, int] | None = None,
                       priority: bool = False) -> None
        """이미지 디코딩 요청. 완료 시 image_ready 시그널 발생"""

    def get_cached_pixmap(self, path: str) -> QPixmap | None
        """캐시된 pixmap 반환 (없으면 None)"""

    def is_cached(self, path: str) -> bool
        """캐시 여부 확인"""

    def prefetch(self, paths: list[str],
                 target_size: tuple[int, int] | None = None) -> None
        """여러 이미지 미리 로드"""

    def cancel_pending(self, path: str | None = None) -> None
        """대기 중인 디코딩 취소 (path=None이면 전체)"""

    def clear_cache(self) -> None
        """캐시 비우기"""

    # ═══════════════════════════════════════════════════════════
    # 썸네일 API
    # ═══════════════════════════════════════════════════════════
    def request_thumbnail(self, path: str,
                          size: tuple[int, int] = (256, 195)) -> None
        """썸네일 요청. 완료 시 thumbnail_ready 시그널 발생"""

    def get_cached_thumbnail(self, path: str) -> QIcon | None
        """캐시된 썸네일 반환"""

    # ═══════════════════════════════════════════════════════════
    # 메타데이터 API
    # ═══════════════════════════════════════════════════════════
    def get_file_info(self, path: str) -> dict
        """파일 정보 반환 (resolution, size, mtime, etc.)"""

    def get_resolution(self, path: str) -> tuple[int, int] | None
        """이미지 해상도 반환"""

    # ═══════════════════════════════════════════════════════════
    # 설정 API
    # ═══════════════════════════════════════════════════════════
    def set_decoding_strategy(self, strategy: DecodingStrategy) -> None
        """디코딩 전략 설정 (Full/FastView)"""

    def set_cache_size(self, size: int) -> None
        """캐시 크기 설정"""

    def set_thumbnail_size(self, width: int, height: int) -> None
        """기본 썸네일 크기 설정"""

    # ═══════════════════════════════════════════════════════════
    # 생명주기
    # ═══════════════════════════════════════════════════════════
    def shutdown(self) -> None
        """리소스 정리 및 종료"""
```

## 리팩토링 단계

### Phase 1: image_engine 패키지 기본 구조 생성

**디렉토리:** `image_viewer/image_engine/` (신규 패키지)

**작업:**
1. `image_engine/` 디렉토리 생성
2. `__init__.py` 생성 (ImageEngine export)
3. `engine.py` 생성 (메인 엔진 클래스)
4. 기존 모듈 이동:
   - `fs_model.py` → `image_engine/fs_model.py`
   - `loader.py` → `image_engine/loader.py`
   - `decoder.py` → `image_engine/decoder.py`
   - `strategy.py` → `image_engine/strategy.py`
   - `thumbnail_cache.py` → `image_engine/thumbnail_cache.py`
5. `cache.py` 생성 (pixmap 캐시 관리)

```python
# image_viewer/image_engine/__init__.py
from .engine import ImageEngine

__all__ = ["ImageEngine"]

# image_viewer/image_engine/engine.py
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap, QIcon

class ImageEngine(QObject):
    """이미지 처리 엔진 - 모든 데이터/처리 로직의 단일 진입점"""

    image_ready = Signal(str, QPixmap, object)
    folder_changed = Signal(str, list)
    thumbnail_ready = Signal(str, QIcon)

    def __init__(self, parent=None):
        super().__init__(parent)
        from .fs_model import ImageFileSystemModel
        from .loader import Loader
        from .decoder import decode_image

        self._fs_model = ImageFileSystemModel(self)
        self._loader = Loader(decode_image)
        self._pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._cache_size = 20

        # 내부 시그널 연결
        self._loader.image_decoded.connect(self._on_image_decoded)
        self._fs_model.directoryLoaded.connect(self._on_directory_loaded)
```

### Phase 2: 파일 시스템 API 구현

**작업:**
1. `open_folder()` 구현
2. `get_image_files()` 등 파일 접근 메서드 위임
3. `folder_changed` 시그널 발생 로직

```python
def open_folder(self, path: str) -> bool:
    if not Path(path).is_dir():
        return False
    self._fs_model.setRootPath(path)
    return True

def _on_directory_loaded(self, path: str):
    files = self._fs_model.get_image_files()
    self.folder_changed.emit(path, files)
```

### Phase 3: 디코딩 API 구현

**작업:**
1. `request_decode()` 구현
2. `get_cached_pixmap()` 구현
3. `prefetch()` 구현
4. `image_ready` 시그널 발생 로직

```python
def request_decode(self, path: str,
                   target_size: tuple[int, int] | None = None,
                   priority: bool = False) -> None:
    # 캐시 확인
    if path in self._pixmap_cache:
        pix = self._pixmap_cache[path]
        self.image_ready.emit(path, pix, None)
        return

    # 디코딩 요청
    tw, th = target_size or (None, None)
    self._loader.request_load(path, tw, th, "both")

def _on_image_decoded(self, path: str, image_data, error):
    if error or image_data is None:
        self.image_ready.emit(path, QPixmap(), error)
        return

    # numpy → QPixmap 변환
    pixmap = self._array_to_pixmap(image_data)

    # 캐시 저장
    self._pixmap_cache[path] = pixmap
    if len(self._pixmap_cache) > self._cache_size:
        self._pixmap_cache.popitem(last=False)

    self.image_ready.emit(path, pixmap, None)
```

### Phase 4: main.py 리팩토링

**작업:**
1. `ImageViewer`에서 `ImageEngine` 사용
2. `loader`, `pixmap_cache` 제거
3. 시그널 연결로 UI 업데이트

```python
class ImageViewer(QMainWindow):
    def __init__(self):
        super().__init__()

        # Engine 생성 (모든 데이터/처리 담당)
        self.engine = ImageEngine(self)
        self.engine.image_ready.connect(self._on_image_ready)
        self.engine.folder_changed.connect(self._on_folder_changed)

        # UI만 관리
        self.canvas = ImageCanvas(self)
        self.current_index = -1
        # ... UI 상태만

    def display_image(self):
        path = self.engine.get_file_at_index(self.current_index)
        if path:
            self.engine.request_decode(path, self._get_target_size())

    def _on_image_ready(self, path: str, pixmap: QPixmap, error):
        if error:
            self._update_status(f"Load failed: {error}")
            return
        if path == self.engine.get_file_at_index(self.current_index):
            self.canvas.set_pixmap(pixmap)
            self._update_status()
```

### Phase 5: DisplayController 통합/제거

**작업:**
1. `DisplayController` 로직을 `ImageEngine`과 `ImageViewer`로 분배
2. 디코딩 관련 → `ImageEngine`
3. UI 업데이트 관련 → `ImageViewer`
4. `display_controller.py` 제거 또는 최소화

### Phase 6: Trim/Converter 리팩토링

**작업:**
1. `trim_operations.py`가 `ImageEngine` API 사용
2. `ui_convert_webp.py`가 `ImageEngine` API 사용
3. viewer 내부 접근 제거

```python
# trim_operations.py
def start_trim_workflow(viewer) -> None:
    engine = viewer.engine
    files = engine.get_image_files()
    current_folder = engine.get_current_folder()
    # ... engine API만 사용
```

### Phase 7: Explorer Mode 통합

**작업:**
1. `ThumbnailGridWidget`이 `ImageEngine` 사용
2. 썸네일 요청/캐시를 Engine 통해 처리
3. `fs_model` 직접 접근 제거

### Phase 8: 정리 및 최적화

**작업:**
1. 불필요한 코드 제거
2. 중복 로직 통합
3. 타입 힌트 정리
4. 문서화

## 파일 구조 변경

### Before
```
image_viewer/
├─ main.py              (800+ lines, 모든 것)
├─ fs_model.py          (파일 시스템)
├─ loader.py            (디코딩 스케줄링)
├─ decoder.py           (pyvips)
├─ display_controller.py (표시 로직)
├─ thumbnail_cache.py   (썸네일 DB)
├─ strategy.py          (디코딩 전략)
├─ ui_canvas.py
├─ ui_menus.py
├─ ui_explorer_grid.py
├─ ui_explorer_tree.py
├─ ui_settings.py
├─ ui_convert_webp.py
└─ ...
```

### After
```
image_viewer/
├─ image_engine/              # 백엔드/서버 패키지 (신규)
│   ├─ __init__.py            # ImageEngine export
│   ├─ engine.py              # 메인 엔진 클래스
│   ├─ fs_model.py            # 파일 시스템 모델 (이동)
│   ├─ loader.py              # 디코딩 스케줄러 (이동)
│   ├─ decoder.py             # pyvips 래퍼 (이동)
│   ├─ cache.py               # pixmap + thumbnail 캐시 통합
│   └─ strategy.py            # 디코딩 전략 (이동)
│
├─ ui/                        # 프론트엔드/클라이언트 패키지 (정리)
│   ├─ __init__.py
│   ├─ canvas.py              # ui_canvas.py → 이동
│   ├─ menus.py               # ui_menus.py → 이동
│   ├─ explorer_grid.py       # ui_explorer_grid.py → 이동
│   ├─ explorer_tree.py       # ui_explorer_tree.py → 이동
│   ├─ settings_dialog.py     # ui_settings.py → 이동
│   └─ convert_dialog.py      # ui_convert_webp.py → 이동
│
├─ main.py                    # 앱 진입점 (축소: ~400 lines)
├─ styles.py                  # 테마/스타일
├─ settings_manager.py        # 설정 관리
├─ file_operations.py         # 파일 작업 (복사/삭제 등)
├─ trim_operations.py         # 트림 워크플로우
├─ explorer_mode_operations.py # 모드 전환 로직
└─ ...
```

### Import 변경 예시
```python
# Before
from image_viewer.fs_model import ImageFileSystemModel
from image_viewer.loader import Loader
from image_viewer.ui_canvas import ImageCanvas

# After
from image_viewer.image_engine import ImageEngine
from image_viewer.ui.canvas import ImageCanvas
```

## 예상 효과

### 긍정적 효과
- **명확한 책임 분리**: Engine = 데이터/처리, UI = 표시
- **테스트 용이**: Engine을 독립적으로 테스트 가능
- **재사용성**: CLI, 웹 등 다른 UI에서 Engine 재사용
- **유지보수**: 각 레이어 독립적 수정
- **확장성**: 새 기능은 Engine API 확장으로 해결
- **코드 감소**: main.py 800+ → 400 lines 예상

### 위험 요소
- **대규모 리팩토링**: 여러 파일 수정 필요
- **시그널 복잡도**: 시그널 연결 관리 필요
- **성능**: 추가 레이어로 인한 오버헤드 (미미할 것으로 예상)

## 테스트 계획

### 단위 테스트
1. `ImageEngine.open_folder()` 정확성
2. `ImageEngine.request_decode()` 시그널 발생
3. 캐시 동작 (LRU, 크기 제한)
4. 파일 목록 동기화

### 통합 테스트
1. 폴더 열기 → 이미지 표시 플로우
2. 네비게이션 (next/prev)
3. Trim 워크플로우
4. Converter 워크플로우
5. Explorer 모드 전환

## 타임라인 (예상)

- Phase 1: 2-3 hours (Engine 기본 구조)
- Phase 2: 1-2 hours (파일 시스템 API)
- Phase 3: 2-3 hours (디코딩 API)
- Phase 4: 3-4 hours (main.py 리팩토링)
- Phase 5: 1-2 hours (DisplayController 통합)
- Phase 6: 2-3 hours (Trim/Converter)
- Phase 7: 2-3 hours (Explorer Mode)
- Phase 8: 1-2 hours (정리)

**총 예상 시간: 15-22 hours**

## 다음 단계

1. 이 계획 검토 및 승인
2. Phase 1부터 순차적으로 진행
3. 각 Phase 완료 후 테스트 및 커밋
4. 문제 발생 시 즉시 롤백 및 재검토
