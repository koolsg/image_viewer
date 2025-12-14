# Refactoring Plan: Unified QFileSystemModel Architecture

## 목표

모든 기능(View Mode, Explorer Mode, Trim, Converter)이 단일 `QFileSystemModel`을 공유하도록 아키텍처 개선

## 현재 문제점

### 데이터 소스 분산
```
View Mode        → image_files: list[str]  (수동 스캔)
Explorer Mode    → ImageFileSystemModel    (자동 감시)
Trim             → image_files 순회
Converter        → 독립적인 폴더 선택
```

### 문제:
- 파일 목록이 여러 곳에 중복 저장
- 파일 시스템 변경 시 일부만 업데이트
- 파일 필터링/정렬 로직 중복
- 메모리 낭비 (같은 폴더를 여러 모델이 감시)

## 목표 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│           ImageFileSystemModel (단일 진실의 원천)          │
│  - 파일 목록 관리                                          │
│  - 파일 시스템 감시 (자동 업데이트)                         │
│  - 메타데이터 제공 (해상도, 크기, 수정일)                   │
└────────────┬────────────────────────────────────────────┘
             │
    ┌────────┼────────┬──────────┬──────────┐
    │        │        │          │          │
┌───▼───┐ ┌─▼──┐ ┌───▼────┐ ┌───▼────┐ ┌──▼──┐
│Decoder│ │Thumb│ │  Trim  │ │Convert │ │ ... │
│       │ │Cache│ │  Logic │ │  Logic │ │     │
└───┬───┘ └─┬──┘ └───┬────┘ └───┬────┘ └──┬──┘
    │       │        │          │          │
    └───────┴────────┴──────────┴──────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
    ┌───▼────┐  ┌───▼────┐  ┌───▼────┐
    │  View  │  │Explorer│  │ Dialogs│
    │  Mode  │  │  Mode  │  │        │
    └────────┘  └────────┘  └────────┘
```

## 리팩토링 단계

### Phase 1: 모델 통합 준비 (기반 작업)

#### 1.1 ImageFileSystemModel 개선
**파일:** `image_viewer/ui_explorer_grid.py`

**작업:**
- `get_image_files()` 메서드 추가: 현재 폴더의 이미지 파일 목록 반환
- `get_current_folder()` 메서드 추가: 현재 rootPath 반환
- `get_file_at_index(idx)` 메서드 추가: 인덱스로 파일 경로 반환
- `get_file_count()` 메서드 추가: 이미지 파일 개수 반환

```python
class ImageFileSystemModel(QFileSystemModel):
    def get_image_files(self) -> list[str]:
        """현재 폴더의 모든 이미지 파일 경로 반환 (정렬됨)"""
        root_index = self.index(self.rootPath())
        files = []
        for row in range(self.rowCount(root_index)):
            index = self.index(row, 0, root_index)
            if self.isDir(index):
                continue
            path = self.filePath(index)
            if self._is_image_file(path):
                files.append(path)
        return sorted(files)

    def get_file_at_index(self, idx: int) -> str | None:
        """인덱스로 파일 경로 반환"""
        files = self.get_image_files()
        if 0 <= idx < len(files):
            return files[idx]
        return None

    def get_file_index(self, path: str) -> int:
        """파일 경로로 인덱스 반환"""
        files = self.get_image_files()
        try:
            return files.index(path)
        except ValueError:
            return -1
```

#### 1.2 ImageViewer에 공유 모델 추가
**파일:** `image_viewer/main.py`

**작업:**
- `self.fs_model: ImageFileSystemModel` 추가 (항상 존재)
- `self.image_files` 제거 예정 (Phase 2에서)
- `self.current_index` → `self.current_file_path` 변경 검토

```python
class ImageViewer(QMainWindow):
    def __init__(self):
        super().__init__()

        # 공유 파일 시스템 모델 (항상 존재)
        from image_viewer.ui_explorer_grid import ImageFileSystemModel
        self.fs_model = ImageFileSystemModel(self)
        self.fs_model.directoryLoaded.connect(self._on_fs_directory_loaded)

        # 기존 코드...
        self.image_files: list[str] = []  # Phase 2에서 제거
        self.current_index = -1
```

### Phase 2: View Mode 리팩토링

#### 2.1 DisplayController 수정
**파일:** `image_viewer/display_controller.py`

**작업:**
- `_setup_fs_watcher()` 제거 (이미 `self.fs_model`이 감시 중)
- `_reload_image_files()` 제거
- `open_folder()` 간소화: 모델에 rootPath만 설정

```python
def open_folder(self) -> None:
    viewer = self.viewer
    dir_path = QFileDialog.getExistingDirectory(...)
    if not dir_path:
        return

    # Explorer 모드는 기존과 동일
    if not viewer.explorer_state.view_mode:
        # ... 기존 로직
        return

    # View 모드: 모델에 폴더 설정만
    viewer.fs_model.setRootPath(dir_path)

    # 첫 이미지 표시
    files = viewer.fs_model.get_image_files()
    if not files:
        viewer._update_status("No images found.")
        return

    viewer.current_index = 0
    viewer._save_last_parent_dir(dir_path)
    self.display_image()
    self.maintain_decode_window(back=0, ahead=5)
    viewer.enter_fullscreen()
```

#### 2.2 ImageViewer 네비게이션 수정
**파일:** `image_viewer/main.py`

**작업:**
- `next_image()`, `prev_image()` 등에서 `self.image_files` 대신 `self.fs_model.get_image_files()` 사용
- 또는 `_on_fs_directory_loaded()`에서 `self.image_files` 동기화 (과도기)

```python
def next_image(self):
    files = self.fs_model.get_image_files()
    if not files or self.current_index >= len(files) - 1:
        return
    self.current_index += 1
    self.display_image()
    self.maintain_decode_window()
```

#### 2.3 파일 시스템 변경 처리
**파일:** `image_viewer/main.py`

**작업:**
- `_on_fs_directory_loaded()` 핸들러 추가
- 파일 추가/삭제 시 current_index 조정

```python
def _on_fs_directory_loaded(self, path: str):
    """파일 시스템 변경 감지 시 호출"""
    if not self.explorer_state.view_mode:
        return  # Explorer 모드는 자동 업데이트

    # View 모드: 현재 파일 유지하면서 목록 업데이트
    current_file = None
    files = self.fs_model.get_image_files()

    if self.current_index >= 0:
        old_files = self.image_files  # 임시
        if self.current_index < len(old_files):
            current_file = old_files[self.current_index]

    # 현재 파일이 여전히 존재하면 인덱스 업데이트
    if current_file and current_file in files:
        self.current_index = files.index(current_file)
    elif self.current_index >= len(files):
        self.current_index = max(0, len(files) - 1)

    self._update_status()
    _logger.debug("fs changed: %d files", len(files))
```

### Phase 3: Explorer Mode 연결

#### 3.1 Explorer 모드에서 공유 모델 사용
**파일:** `image_viewer/explorer_mode_operations.py`

**작업:**
- `_setup_explorer_mode()`에서 `viewer.fs_model` 사용
- 새 모델 생성하지 않고 기존 모델 재사용

```python
def _setup_explorer_mode(viewer) -> None:
    # 기존: grid.model = ImageFileSystemModel()
    # 변경: grid.model = viewer.fs_model

    grid = viewer.explorer_state._explorer_grid
    if grid is None:
        grid = ThumbnailGridWidget(viewer)
        viewer.explorer_state._explorer_grid = grid

    # 공유 모델 사용
    grid.setModel(viewer.fs_model)

    # 현재 폴더가 있으면 설정
    current_folder = viewer.fs_model.rootPath()
    if current_folder:
        grid.load_folder(current_folder)
```

### Phase 4: Trim 리팩토링

#### 4.1 Trim 워크플로우 수정
**파일:** `image_viewer/trim_operations.py`

**작업:**
- `viewer.image_files` 대신 `viewer.fs_model.get_image_files()` 사용
- 배치 트림 후 수동 리로드 제거 (모델이 자동 감지)

```python
def start_trim_workflow(viewer) -> None:
    # 기존: paths = list(viewer.image_files)
    # 변경: paths = viewer.fs_model.get_image_files()

    if not overwrite:
        # 배치 저장
        paths = viewer.fs_model.get_image_files()
        worker = TrimBatchWorker(paths, profile)
        # ... 기존 로직
        # 수동 리로드 제거 (모델이 자동 감지)
        return

    # Overwrite 모드
    preloader = TrimPreloader(viewer.fs_model.get_image_files(), profile)
    # ... 기존 로직
```

### Phase 5: Converter 통합

#### 5.1 WebP Converter 수정
**파일:** `image_viewer/ui_convert_webp.py`

**작업:**
- 생성자에서 `fs_model` 받기
- 폴더 선택 시 모델의 rootPath 사용

```python
class WebPConvertDialog(QDialog):
    def __init__(self, parent, fs_model: ImageFileSystemModel, start_folder=None):
        super().__init__(parent)
        self.fs_model = fs_model

        # 기본 폴더: fs_model의 현재 폴더
        if start_folder is None:
            start_folder = fs_model.rootPath()

        # ... 기존 로직
```

#### 5.2 메인에서 호출 수정
**파일:** `image_viewer/main.py`

```python
def open_convert_dialog(self) -> None:
    if self._convert_dialog is None:
        self._convert_dialog = WebPConvertDialog(self, self.fs_model)
    self._convert_dialog.show()
```

### Phase 6: 정리 및 최적화

#### 6.1 중복 코드 제거
- `image_viewer/display_controller.py`: `_setup_fs_watcher()`, `_reload_image_files()` 제거
- `image_viewer/main.py`: `self.image_files` 제거 (완전히 모델로 대체)
- `image_viewer/explorer_state.py`: `_fs_watcher` 제거

#### 6.2 image_files 완전 제거
**파일:** `image_viewer/main.py`

**작업:**
- `self.image_files` 제거
- 모든 참조를 `self.fs_model.get_image_files()` 또는 캐싱된 값으로 변경

```python
# 제거:
self.image_files: list[str] = []

# 대체 옵션 1: 매번 모델에서 가져오기
def next_image(self):
    files = self.fs_model.get_image_files()
    # ...

# 대체 옵션 2: 캐싱 (성능 최적화)
def _on_fs_directory_loaded(self, path: str):
    self._cached_files = self.fs_model.get_image_files()
    # ...
```

#### 6.3 성능 최적화
- `get_image_files()` 결과 캐싱 검토
- `directoryLoaded` 시그널 중복 발생 방지
- 불필요한 UI 업데이트 최소화

## 테스트 계획

### 단위 테스트
1. `ImageFileSystemModel.get_image_files()` 정확성
2. 파일 추가/삭제 시 시그널 발생 확인
3. 인덱스 변환 로직 (`get_file_at_index`, `get_file_index`)

### 통합 테스트
1. View 모드에서 파일 추가 → 자동 감지 확인
2. Explorer 모드에서 파일 삭제 → View 모드 동기화 확인
3. Trim 작업 후 `.trim` 파일 자동 표시 확인
4. 모드 전환 시 파일 목록 일관성 확인

### 수동 테스트 시나리오
1. 폴더 열기 → View 모드에서 이미지 탐색
2. Explorer 모드 전환 → 같은 파일 목록 확인
3. 외부에서 이미지 추가 → 두 모드 모두 자동 표시
4. Trim 실행 → `.trim` 파일 자동 표시
5. Converter 실행 → 변환된 파일 자동 표시

## 예상 효과

### 긍정적 효과
- **메모리 절약**: 파일 목록 중복 저장 제거
- **일관성 보장**: 단일 진실의 원천
- **코드 간소화**: 파일 스캔 로직 중복 제거 (~100 lines)
- **자동 동기화**: 모든 기능이 파일 변경 자동 감지
- **확장성**: 새 기능 추가 시 모델만 참조

### 위험 요소
- **대규모 리팩토링**: 여러 파일 수정 필요
- **회귀 버그 가능성**: 철저한 테스트 필요
- **성능 영향**: `get_image_files()` 호출 빈도 최적화 필요

## 롤백 계획

각 Phase를 별도 브랜치에서 작업:
- `refactor/phase1-model-prep`
- `refactor/phase2-view-mode`
- `refactor/phase3-explorer-mode`
- `refactor/phase4-trim`
- `refactor/phase5-converter`
- `refactor/phase6-cleanup`

문제 발생 시 이전 Phase로 롤백 가능

## 타임라인 (예상)

- Phase 1: 2-3 hours (모델 개선)
- Phase 2: 3-4 hours (View 모드)
- Phase 3: 1-2 hours (Explorer 모드)
- Phase 4: 1-2 hours (Trim)
- Phase 5: 1 hour (Converter)
- Phase 6: 2-3 hours (정리 및 테스트)

**총 예상 시간: 10-15 hours**

## 다음 단계

1. 이 계획 검토 및 승인
2. Phase 1부터 순차적으로 진행
3. 각 Phase 완료 후 테스트 및 커밋
4. 문제 발생 시 즉시 롤백 및 재검토
