# 📸 썸네일 캐시 시스템

**업데이트 기준:** 2025-12-22

> 현재 구현(2025-12-22 기준)을 문서 상단에 배치했습니다. 이전 문서는 문서 하단의 '레거시(보관용)' 섹션으로 이동했습니다.

## 🏗️ 핵심 요약
- 현재 구현에서는 **썸네일 DB 읽기/프리페치와 생성(디코드→PNG 바이트 저장)**을 `EngineCore`(비-GUI 쓰레드)가 담당합니다.
- UI(Explorer model / grid)는 `ImageEngine`의 신호(`explorer_thumb_rows`, `explorer_thumb_generated`)를 소비하여 **바이트 → QPixmap/QIcon** 변환을 수행합니다.
- 디스크 저장은 데이터 어댑터인 `ThumbDBBytesAdapter`를 통해 수행되며, 썸네일 BLOB은 **nullable**입니다 (메타는 존재할 수 있음).

---

## 🧭 아키텍처 개요

```
┌────────────────────────────┐            ┌──────────────────────────┐
│  UI: ThumbnailGridWidget   │ <--------> │  ImageEngine (UI thread) │
│  ExplorerTableModel (UI)   │            └─────────┬────────────────┘
└───────┬────────────────────┘                      │
        │ DecorationRole 요청 (icon)                 │ 전송: _core_request_thumbnail (signal)
        ▼                                           ▼
┌────────────────────────────┐            ┌──────────────────────────┐
│ ExplorerTableModel.data()  │            │  EngineCore (core thread)│
│  - checks _thumb_icons/_bytes│ -- (missing)-> request_thumbnail(path)   │
└─────────┬──────────────────┘            │  - Loader(decode_image)  │
          │                               │  - ThumbDBBytesAdapter   │
          │                               │  - emits thumb_db_chunk / thumb_generated
          ▼                               └──────────────────────────┘
   (uses cached bytes/icon)                         ▲
          │                                         │
          └──────── UI updates (QPixmap/QIcon) ◀────┘
```

---

## 🔁 상세 데이터 흐름 (현재 구현)

1) 폴더 열기
- `ImageEngine.open_folder()` → emits initial empty snapshots, sends `_core_open_folder` signal to `EngineCore.open_folder()`.
- `EngineCore` scans folder, emits `folder_scanned` and starts DB prefetch or generation.

2) DB 프리페치
- `EngineCore._start_db_loader()`가 `FSDBLoadWorker`를 실행해 DB의 행(chunk)을 읽고 `thumb_db_chunk` 시그널로 전달.
- Engine (`_on_core_thumb_db_chunk`)은 `_meta_cache`를 갱신하고 `explorer_thumb_rows`를 emit.
- `ExplorerTableModel._on_thumb_rows()`는 전달받은 행에서 `thumbnail` 바이트(있다면)를 취해 `self._thumb_bytes`에 저장하고, 파일 해상도 메타를 업데이트하여 UI를 갱신.

3) UI에서 아이템 렌더링
- `ExplorerTableModel.data(..., DecorationRole)`:
  - 우선 `self._thumb_icons`를 확인.
  - 없으면 `self._thumb_bytes`에서 PNG 바이트를 읽어 `QPixmap`으로 변환, 스케일 후 `QIcon`으로 캐시 후 반환.
  - 바이트도 없으면 `self._engine.request_thumbnail(path)`로 **지연 생성 요청**.

4) 썸네일 생성 (누락시)
- `ImageEngine.request_thumbnail(path)` → 코어 쓰레드로 `_core_request_thumbnail` 시그널.
- `EngineCore.request_thumbnail()`는 중복·이미 생성된 경우를 검사(`_thumb_pending`, `_thumb_done`)하고, 내부 `Loader.request_load(path, tw, th, "both")`로 디코드 요청.
- 디코더(주로 pyvips)에서 numpy 배열 리턴 → `EngineCore._on_thumb_decoded()`에서
  - numpy → `QImage` → PNG bytes로 인코딩
  - `ThumbDBBytesAdapter.upsert_meta()`로 메타/thumbnail 바이트 저장
  - `_thumb_done`에 (mtime_ms, size, tw, th)로 마킹
  - `thumb_generated` 시그널 emit (payload dict)

5) UI 갱신 (생성 완료)
- `ImageEngine._on_core_thumb_generated()`가 `_meta_cache`를 갱신하고 `explorer_thumb_generated`를 emit.
- `ExplorerTableModel._on_thumb_generated()` → `_on_thumb_rows()` 호출로 내부 바이트/아이콘이 갱신되고 `dataChanged`를 emit하여 해당 셀이 즉시 그려짐.

6) 결함 처리
- DB에 저장된 썸네일이 손상되어 `QPixmap.loadFromData()` 실패 시, 구현은 해당 BLOB을 `thumbnail=None`으로 재저장하여 향후 재디코드를 유도합니다.

---

## 🗄️ DB 스키마 & 파일명
- EngineCore는 폴더 DB 파일로 `SwiftView_thumbs.db`를 사용해 `ThumbDBBytesAdapter`를 생성합니다 (경로 비교 및 스캔 필터에는 내부적으로 소문자 `swiftview_thumbs.db` 상수가 사용됨).
- 저장되는 메타/필드(업데이트 시):
  - path, thumbnail (BLOB, nullable), width, height, mtime, size, thumb_width, thumb_height, created_at
- 중요한 점: **thumbnail BLOB은 nullable**이며, 메타는 존재할 수 있음 (DB 프리페치 시에는 바이트 없이 메타만 채워진 행이 올 수 있음).

---

## ⚡ 캐시 계층 (현행)
1. 메모리 (UI): ExplorerTableModel의 `_thumb_icons`/`_thumb_bytes` (즉시 렌더 가능)
2. 디스크 (SQLite): `SwiftView_thumbs.db` (bytes + meta; fast lookup)
3. 원본 디코드: `EngineCore`의 `Loader` → pyvips 디코더 (비동기)

---

## 🔍 디버깅 팁
- 로그: --log-level DEBUG --log-cats engine_core,engine,ui_explorer_grid
- DB 파일 위치: Path(folder) / "SwiftView_thumbs.db"
- 캐시 점검: Explorer model 내부 상태
  - `len(model._thumb_bytes)`, `len(model._thumb_icons)`
- 손상된 BLOB 감지: 로그에 `cleared corrupt thumbnail blob for path:` 메시지

---

## 🔧 관련 코드 위치 (참고)
- image_viewer/image_engine/engine_core.py  ← DB preload + thumbnail generation
- image_viewer/image_engine/engine.py       ← UI-thread 엔진 브리지, signals: `explorer_thumb_rows`, `explorer_thumb_generated`
- image_viewer/image_engine/db/thumbdb_bytes_adapter.py ← DB adapter (low-level)
- image_viewer/image_engine/fs_db_worker.py ← DB chunk loader
- image_viewer/image_engine/thumbnail_cache.py ← UI-facing helper (schema helpers, not used as the core path)
- image_viewer/ui_explorer_grid.py / explorer_model.py ← UI 소비자 (bytes→pixmap)
- image_viewer/loader.py / image_viewer/decoder.py ← 디코딩 파이프

---

## ✅ 주의/권장 사항
- 문서화된 구현과 달리, **썸네일 생성은 Core thread에서 수행**되어 DB에 바이트로 저장되고 UI는 이를 소비합니다. 문서나 로그에서 혼동되지 않도록 이 책임 경계를 기억하세요.
- 개선 아이디어(우선순위 제안):
  - LRU 메모리 제한 (Explorer model에 적용)
  - visible-only lazy generation (스캔 이후 즉시 전체 생성 대신)
  - DB 정리 / vacuum 정기화 작업 자동화

---

**요약:** 실제 구현에서는 EngineCore가 DB 프리페치/생성(바이트 저장)을 담당하고, ImageEngine/ExplorerModel이 이를 소비해 최종적으로 UI에 `QIcon`/`QPixmap`을 렌더링합니다. 이 문서는 현재 코드베이스의 클래스/시그널/데이터 흐름을 반영하도록 갱신되었습니다.

---

## 레거시(보관용)
아래는 기존(이전) 문서의 전체 내용(보관용)입니다. 원본 문장을 그대로 보존했습니다.

# 📸 SwiftView 썸네일 캐시 시스템 설명

## 🏗️ 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────┐
│                    Explorer Mode 폴더 열기                    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  ImageFileSystemModel.data() - Qt가 각 아이템 렌더링 요청    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │ _request_thumbnail()   │
         └────────┬───────────────┘
                  │
    ┌─────────────┴─────────────┐
    │                           │
    ▼                           ▼
┌─────────────┐         ┌──────────────┐
│ 메모리 캐시  │         │ 디스크 캐시   │
│ 확인        │         │ 확인         │
└─────┬───────┘         └──────┬───────┘
      │                        │
      │ 있음                   │ 있음
      ▼                        ▼
   [즉시 표시]          [SQLite 로드]
                              │
                              │ 없음
                              ▼
                    ┌──────────────────┐
                    │ Loader에 디코딩   │
                    │ 요청 (비동기)     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ _on_thumbnail_   │
                    │ ready() 콜백     │
                    └────────┬─────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
                    ▼                 ▼
            ┌──────────────┐  ┌──────────────┐
            │ 메모리 캐시   │  │ 디스크 캐시   │
            │ 저장         │  │ 저장 (SQLite) │
            └──────────────┘  └──────────────┘
```

---

## 📝 상세 흐름

### 1️⃣ **폴더 로드 시작**
```python
# ThumbnailGridWidget.load_folder()
def load_folder(self, folder_path: str) -> None:
    with busy_cursor():  # 🕐 모래시계 커서 시작
        idx = self._model.setRootPath(folder_path)
        self._list.setRootIndex(idx)
```

### 2️⃣ **Qt가 각아이템 렌더링 요청**
```python
# ImageFileSystemModel.data()
def data(self, index: QModelIndex, role: int):
    if role == Qt.DecorationRole and self._view_mode == "thumbnail":
        if icon := self._thumb_cache.get(path):  # 메모리 캐시 확인
            return icon
        self._request_thumbnail(path)  # 없으면 요청
```

### 3️⃣ **썸네일 요청 처리**
```python
def _request_thumbnail(self, path: str) -> None:
    # 1. 메모리 캐시 확인
    if path in self._thumb_cache:
        return  # ✅ 이미 있음

    # 2. 디스크 캐시 확인 (SQLite)
    icon = self._load_disk_icon(path)
    if icon is not None:
        self._thumb_cache[path] = icon  # 메모리에 저장
        self.dataChanged.emit(...)      # UI 업데이트
        return  # ✅ 디스크에서 로드 성공

    # 3. 디스크에도 없음 → Loader에 디코딩 요청
    if not self._busy_cursor_active:
        QApplication.setOverrideCursor(...)  # 🕐 모래시계 시작
        self._busy_cursor_active = True

    self._thumb_pending.add(path)
    self._loader.request_load(
        path,
        target_width=256,
        target_height=195,
        size="both"
    )
```

### 4️⃣ **디스크 캐시 로드 (SQLite)**
```python
def _load_disk_icon(self, path: str) -> QIcon | None:
    # 1. DB 초기화 (폴더별로 한 번만)
    self._ensure_db_cache(path)  # SwiftView_thumbs.db 생성/연결

    # 2. 파일 정보 확인
    stat = file_path.stat()
    mtime = stat.st_mtime  # 수정 시간
    size = stat.st_size    # 파일 크기

    # 3. SQLite에서 조회
    result = self._db_cache.get(
        path, mtime, size,
        thumb_width=256, thumb_height=195
    )

    # 4. 캐시 유효성 검증
    # - 파일 경로 일치
    # - mtime 일치 (파일이 수정되지 않았는지)
    # - size 일치 (파일 크기가 같은지)
    # - 썸네일 크기 일치 (설정이 바뀌지 않았는지)

    if result:
        pixmap, orig_width, orig_height = result
        return QIcon(pixmap)  # ✅ 캐시 히트

    return None  # ❌ 캐시 미스
```

### 5️⃣ **SQLite 캐시 구조**
```sql
-- ThumbnailCache._init_db()
CREATE TABLE thumbnails (
    path TEXT PRIMARY KEY,           -- 파일 경로
    mtime REAL NOT NULL,             -- 수정 시간 (검증용)
    size INTEGER NOT NULL,           -- 파일 크기 (검증용)
    width INTEGER,                   -- 원본 이미지 너비
    height INTEGER,                  -- 원본 이미지 높이
    thumb_width INTEGER NOT NULL,    -- 썸네일 너비
    thumb_height INTEGER NOT NULL,   -- 썸네일 높이
    thumbnail BLOB NOT NULL,         -- PNG 바이너리 데이터
    created_at REAL NOT NULL         -- 캐시 생성 시간
);

-- 인덱스 (빠른 조회)
CREATE INDEX idx_mtime ON thumbnails(mtime);
CREATE INDEX idx_created_at ON thumbnails(created_at);
```

### 6️⃣ **비동기 디코딩 완료 콜백**
```python
def _on_thumbnail_ready(self, path: str, image_data, error) -> None:
    self._thumb_pending.discard(path)  # pending 목록에서 제거

    if error or image_data is None:
        self._check_thumbnail_completion()  # 🕐 완료 확인
        return

    # 1. numpy array → QPixmap 변환
    q_image = QImage(image_data.data, width, height, ...)
    pixmap = QPixmap.fromImage(q_image)

    # 2. 크기 조정 (smooth scaling)
    scaled = pixmap.scaled(256, 195, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    # 3. 메모리 캐시에 저장
    self._thumb_cache[path] = QIcon(scaled)

    # 4. 원본 해상도 읽기 (QImageReader - 헤더만)
    reader = QImageReader(path)
    size = reader.size()
    orig_width = size.width()
    orig_height = size.height()

    # 5. 디스크 캐시에 저장 (SQLite)
    self._save_disk_icon(path, scaled, orig_width, orig_height)

    # 6. UI 업데이트
    self.dataChanged.emit(idx, idx, [Qt.DecorationRole, Qt.DisplayRole])

    # 7. 모든 썸네일 완료 확인
    self._check_thumbnail_completion()  # 🕐 커서 복원 체크
```

### 7️⃣ **디스크 캐시 저장 (SQLite)**
```python
def _save_disk_icon(self, path: str, pixmap: QPixmap,
                    orig_width: int, orig_height: int) -> None:
    # 1. 파일 정보 확인
    stat = file_path.stat()
    mtime = stat.st_mtime
    size = stat.st_size

    # 2. SQLite에 저장
    self._db_cache.set(
        path, mtime, size,
        orig_width, orig_height,
        thumb_width=256, thumb_height=195,
        pixmap  # PNG BLOB으로 변환되어 저장
    )
```

```python
# ThumbnailCache.set()
def set(self, path, mtime, size, width, height,
        thumb_width, thumb_height, pixmap):
    # QPixmap → PNG bytes 변환
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    pixmap.save(buffer, "PNG")
    thumbnail_data = buffer.data().data()

    # SQLite INSERT OR REPLACE
    self._conn.execute("""
        INSERT OR REPLACE INTO thumbnails
        (path, mtime, size, width, height,
         thumb_width, thumb_height, thumbnail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (path, mtime, size, width, height,
          thumb_width, thumb_height, thumbnail_data, time.time()))

    self._conn.commit()
```

### 8️⃣ **모든 썸네일 완료 확인**
```python
def _check_thumbnail_completion(self) -> None:
    if self._busy_cursor_active and not self._thumb_pending:
        QApplication.restoreOverrideCursor()  # 🕐 모래시계 해제
        self._busy_cursor_active = False
```

---

## 🎯 캐시 계층 구조

```
┌─────────────────────────────────────────┐
│  Level 1: 메모리 캐시 (dict)             │
│  - 가장 빠름 (즉시 반환)                  │
│  - 프로그램 종료 시 사라짐                │
│  - self._thumb_cache: dict[str, QIcon]  │
└─────────────────────────────────────────┘
                  ↓ 미스
┌─────────────────────────────────────────┐
│  Level 2: 디스크 캐시 (SQLite)           │
│  - 빠름 (~10ms)                          │
│  - 영구 저장 (폴더별 SwiftView_thumbs.db)│
│  - 파일 수정 시 자동 무효화               │
└─────────────────────────────────────────┘
                  ↓ 미스
┌─────────────────────────────────────────┐
│  Level 3: 원본 디코딩 (Loader)           │
│  - 느림 (~100-500ms)                     │
│  - pyvips로 이미지 디코딩                │
│  - 비동기 처리 (백그라운드 스레드)        │
└─────────────────────────────────────────┘
```

---

## 💾 캐시 파일 위치

```
D:\Photos\
├── image1.jpg
├── image2.png
└── SwiftView_thumbs.db  ← 숨김 파일 (Windows)
    └── [SQLite database]
        ├── image1.jpg → PNG BLOB (256x195)
        └── image2.png → PNG BLOB (256x195)
```

**특징:**
- 각 폴더마다 독립적인 캐시 DB
- Windows Thumbs.db 방식과 동일
- 폴더 이동 시 캐시도 함께 이동
- 숨김 파일 속성 (Windows)

---

## ⚡ 성능 최적화

1. **3단계 캐싱:**
   - 메모리 → 디스크 → 디코딩 순서로 확인
   - 대부분의 경우 메모리/디스크에서 즉시 반환

2. **파일 검증:**
   - mtime + size로 파일 변경 감지
   - 파일이 수정되면 자동으로 재생성

3. **비동기 처리:**
   - 디코딩은 백그라운드 스레드에서 처리
   - UI 블로킹 없음

4. **Busy Cursor:**
   - 첫 썸네일 요청 시 모래시계 표시
   - 모든 썸네일 완료 시 자동 해제
   - 사용자에게 진행 상황 피드백

---

## 🔧 관련 파일

- `image_viewer/thumbnail_cache.py`: SQLite 캐시 관리 클래스
- `image_viewer/ui_explorer_grid.py`: 썸네일 요청/로드/저장 로직
- `image_viewer/loader.py`: 비동기 이미지 디코딩
- `image_viewer/decoder.py`: pyvips 기반 이미지 디코딩

---

## 📊 성능 측정 (예상)

| 상황 | 시간 | 설명 |
|------|------|------|
| 메모리 캐시 히트 | ~1ms | 즉시 반환 |
| 디스크 캐시 히트 | ~10ms | SQLite 조회 + PNG 디코딩 |
| 캐시 미스 (첫 로드) | ~100-500ms | 원본 이미지 디코딩 + 리사이징 |
| 폴더 재방문 | ~10ms/이미지 | 대부분 디스크 캐시에서 로드 |

---

## 🐛 디버깅 팁

1. **캐시 확인:**
```python
# 메모리 캐시 크기
len(model._thumb_cache)

# 디스크 캐시 위치
Path(folder) / "SwiftView_thumbs.db"
```

2. **로그 확인:**
```bash
# 썸네일 로딩 로그
--log-level DEBUG --log-cats thumbnail_cache,ui_explorer_grid
```

3. **캐시 무효화:**
- 파일 수정 시간 변경: 자동 무효화
- 썸네일 크기 변경: 자동 무효화
- 수동 삭제: `SwiftView_thumbs.db` 파일 삭제

---

## 🔮 향후 개선 사항

1. **LRU 메모리 캐시:**
   - 현재: 무제한 메모리 사용
   - 개선: 최대 500MB 제한, LRU 정책

2. **Lazy Loading:**
   - 현재: 모든 썸네일 즉시 요청
   - 개선: 스크롤 시 visible items만 로드

3. **캐시 정리:**
   - 현재: 수동 정리 필요
   - 개선: 30일 이상 된 캐시 자동 정리

4. **멀티스레드 디코딩:**
   - 현재: 단일 스레드
   - 개선: ProcessPoolExecutor로 병렬 처리

---

**핵심:** 이 시스템의 핵심은 **3단계 캐싱 + 파일 검증 + 비동기 처리**입니다. 처음 폴더를 열 때는 느리지만, 두 번째부터는 SQLite 캐시 덕분에 매우 빠르게 로드됩니다.
