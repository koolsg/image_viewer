# 디코딩 아키텍처 (전체 이미지 및 썸네일)

📌 목적: 전체 이미지 디코딩과 썸네일 디코딩이 어떻게 구현되어 있는지, 데이터 흐름은 어떻게 되는지, 성능상 위험 요소와 개선 가능성은 무엇인지 문서화합니다.

---

## 1) 구조 개요 (함수·스레드·프로세스 관점) 🔧

- 전체 이미지 디코딩 (뷰 모드)
  - 진입점: `ImageEngine.request_decode()` → 내부적으로 `Loader` 파이프라인으로 전달
  - 디코더: `image_viewer.image_engine.decoder.decode_image` (pyvips 사용) — RGB `numpy.ndarray` 반환
  - 동시성:
    - `Loader`는 `ProcessPoolExecutor`(프로세스 풀)를 사용해 `decode_image`를 워커 프로세스에서 실행
    - I/O 스케줄링: `Loader.io_pool`는 `ThreadPoolExecutor`로 작업 제출을 담당
  - 스레드/소유권:
    - 디코딩은 워커 프로세스에서 수행되고 결과(넘파이 배열)는 `Loader.image_decoded` 신호로 UI/코어 스레드에 전달
    - GUI용 변환: `ConvertWorker`가 numpy → `QImage`로 변환(백그라운드 스레드), 이후 메인 스레드에서 `QPixmap`으로 마무리

- 썸네일 디코딩 (익스플로러 모드)
  - 진입점: `EngineCore.request_thumbnail(path)`이 썸네일 생성 파이프라인을 트리거
  - 현재 방식(권장): `image_viewer.image_engine.decoder.encode_image_to_png` (pyvips 사용) — **파일에서 바로 PNG 바이트를 생성** (중간에 numpy 배열을 만들지 않음)
  - 동시성:
    - 이 역시 `Loader`의 `ProcessPoolExecutor`에서 병렬로 실행
  - FS/DB 연동:
    - `FSDBLoadWorker`(EngineCore의 `QThread`)가 DB/파일시스템을 검사해 `missing_paths`를 방출
    - `EngineCore`는 이들을 `_missing_thumb_queue`에 적재하고 `_missing_thumb_timer`로 `_pump_missing_thumb_queue()`를 호출해 소량씩 요청
  - 마무리:
    - 워커가 PNG bytes를 반환하면 `EngineCore._on_thumb_decoded()`가 이를 검증하고 `ThumbDBBytesAdapter.upsert_meta()`로 DB에 저장

---

## 2) 데이터 흐름 (단계별 설명)

### A. 전체 이미지 (뷰) 데이터 흐름

1. 사용자 요청 또는 프리패치로 `ImageEngine.request_decode(path, target_size)` 호출
2. `Loader.request_load(path, target_width, target_height, size)`가 프로세스 풀에 작업 제출
3. 워커 프로세스에서 `decode_image(path, ...)`(pyvips) 실행
   - 크기 요청 시 `pyvips.Image.thumbnail`, 전체일 경우 `new_from_file` 사용
   - 3채널 `uint8` 버퍼로 변환해 `numpy` 배열로 반환
4. `Loader`가 `(path, numpy_array, None)`을 UI/코어 스레드로 방출 (`image_decoded` 신호)
5. `ConvertWorker`가 numpy → `QImage`로 변환(백그라운드 스레드) 후 `image_converted` 방출
6. `ImageEngine._on_image_converted()`(GUI 스레드)에서 `QImage` → `QPixmap`으로 변환하고 캐시/방출

---

### B. 썸네일 (익스플로러) 데이터 흐름 — 직접 인코드 방식(현재)

1. `FSDBLoadWorker`가 DB를 조사해 썸네일이 없는 파일들을 `missing_paths`로 방출
2. `EngineCore._on_db_missing_paths()`가 이를 `_missing_thumb_queue`에 적재하고 `_missing_thumb_timer` 시작
3. `_pump_missing_thumb_queue()`가 소량(예: 8개)씩 꺼내 `request_thumbnail()` 호출
4. `request_thumbnail()`가 `_thumb_loader.request_load(path, tw, th, "both")`를 호출
5. `Loader.executor`가 `encode_image_to_png(path, ...)`을 워커 프로세스에서 실행
   - 내부적으로 `pyvips.Image.thumbnail` 또는 `new_from_file` 이후 `write_to_buffer('.png')`로 PNG bytes를 얻음
6. `Loader`가 `(path, png_bytes, None)`을 `EngineCore._on_thumb_decoded()`로 방출
7. `EngineCore._on_thumb_decoded()`가 PNG 바이트를 검증하고 stat/mtime/원본 치수를 읽어 `ThumbDBBytesAdapter.upsert_meta()`로 DB에 저장
8. UI는 `thumb_generated` 이벤트 또는 DB 청크 업데이트를 통해 썸네일을 표시

---

## 3) 관찰된 동작 및 성능 고려사항 ⚠️

### 로그에서 관찰된 증상
- 파일이 많은 폴더를 열면 `request_load queued` 로그가 대량으로 찍히며 pending 수치가 크게 증가합니다(예: 99건). 이는 썸네일이 캐시되지 않은 경우 예상되는 동작입니다.
- `FSDBLoadWorker`는 누락 경로를 청크로 방출하고 `EngineCore`는 이를 배치 단위로 펌핑합니다(기본 배치 8, 타이머 0ms).
- 각 `request_load`는 `ProcessPoolExecutor`에 작업을 제출하므로 동시 작업이 많아지면 CPU/IO가 포화될 수 있습니다.

### 잠재 병목과 위험
- 프로세스 폭주: 대용량 폴더에서 한꺼번에 많은 작업을 제출하면 프로세스 풀/메모리/IO가 과부하될 수 있음
- DB 쓰기 집중: `upsert_meta()`가 연속적으로 호출되면 쓰기/워처 이벤트가 폭주할 수 있음 (`_suppress_watch_until`로 일부 억제는 함)
- 가시성 지연: 뷰포트 근처의 썸네일 우선순위를 부여하지 않으면, 사용자가 보는 썸네일이 늦게 생성될 수 있음
- pyvips 의존성: 현재 썸네일 경로는 `pyvips`를 필요로 하며(폴백 없음), pyvips가 없을 경우 에러로 드러남

---

## 4) 권장 사항 및 개선 가능성 ✅

### 단기(저위험) 변경
- `_pump_missing_thumb_queue()` 동작 튜닝
  - `batch_size`와 `remaining_queue_len`를 디버그로 남겨 실제 스로틀링 동작을 측정하도록 함
  - 배치 크기 감소(예: 8 -> 4) 또는 배치 간 짧은 지연(예: 50~200ms) 도입으로 즉시성 부하를 완화
- 프리페치 상한: `_start_db_loader`의 `prefetch_limit`을 더 보수적으로 적용(현재 `min(n,256)`), 저사양 장치에서는 더 낮게
- 계측 추가: `Loader._pending` 크기, 활성 future 수, `FSDBLoadWorker`의 missing 카운트를 로그/메트릭으로 남김

### 중기(구조적) 변경
- 우선순위 큐: `_missing_thumb_queue`를 우선순위 큐로 바꿔 **뷰포트 근처 썸네일을 우선 생성**하도록 하여 가시성 지연을 줄임
- 워커 풀 크기 제어: `ProcessPoolExecutor(max_workers=K)`를 명시적으로 설정할 수 있게 하여 CPU에 맞게 적정값을 조정
- DB 쓰기 스로틀링: `upsert_meta()` 호출을 묶거나 쓰기 큐를 두어 DB 쓰기 폭주를 완화
### 장기적(기능) 아이디어
- 전용 썸네일 워커 풀: 썸네일 전용으로 더 작고 분리된 프로세스 풀을 두어 전체 이미지 디코드 작업이 썸네일을 방해하지 않도록 함
- 온디스크 캐싱 정책: 생성 직후의 썸네일에 대해 in-memory LRU 같은 임시 캐시를 두어 반복적인 DB 쓰기를 줄임
- 배치 생성: 저우선순위(스로틀링)로 전체 폴더의 썸네일을 생성하는 선택형 백그라운드 작업 제공
---

## 5) 운영 체크리스트 / 추가할 메트릭 🧭
- 큐를 펌프할 때 디버그 로그를 남기기: `batch_size=%d remaining=%d`
- `Loader` 상태 주기적 로깅: `pending=%d in_progress=%d` (내부 집합/future에서 파생)
- `FSDBLoadWorker`의 `missing_paths` 방출 로그(청크 크기 및 총 누락 수)를 수집하도록 보장

---

## 부록: 주요 파일 및 심볼
- `image_viewer/image_engine/decoder.py` — `decode_image`, `encode_image_to_png`
- `image_viewer/image_engine/loader.py` — `Loader`, `executor` (`ProcessPoolExecutor`) 및 `io_pool` (`ThreadPoolExecutor`)
- `image_viewer/image_engine/engine_core.py` — `_start_db_loader`, `request_thumbnail`, `_pump_missing_thumb_queue`, `_on_thumb_decoded`, `_missing_thumb_queue`
- `image_viewer/image_engine/fs_db_worker.py` — `FSDBLoadWorker` (`missing_paths`, `chunk_loaded` 방출)
- `image_viewer/image_engine/convert_worker.py` — `ConvertWorker` (뷰 모드: numpy → `QImage`)
- DB 어댑터: `image_viewer/image_engine/db/thumbdb_bytes_adapter.py` — `ThumbDBBytesAdapter.upsert_meta()`

---

## 다음 단계 제안
- 앞서 언급한 계측 로그 3개를 추가하고, 큰 폴더 테스트를 통해 기준선을 수집(큐 길이, CPU, I/O)
- 기준에 따라 `pump`의 기본 `batch`/`delay_ms`를 보수적으로 결정하고 `SettingsManager` 또는 환경변수로 구성 가능하게 변경

---

원하시면 제가 다음을 진행하겠습니다:
- (A) `_pump_missing_thumb_queue()`에 **계측 로그**와 `batch_size`/`delay_ms` 구성을 추가하고, 테스트 및 간단한 시뮬레이션을 실행
- (B) 뷰포트 기반 **우선순위 큐** 구현(간단한 휴리스틱 포함) 및 테스트 하니스 추가

어떤 것을 먼저 해볼까요? (A/B 선택 또는 다른 제안) 🔧