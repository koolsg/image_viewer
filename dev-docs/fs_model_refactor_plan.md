## FS Model Refactor Plan & Status

1) 목적
 - `image_viewer/image_engine/fs_model.py`의 복잡도를 낮추고 책임을 분리하여 유지보수성과 테스트 용이성을 향상.
 - 주요 목표
   - 파일시스템 스캔, DB 조회/업데이트, 파일 메타(stat/mtime) 처리를 명확히 분리.
   - 워커(백그라운드) → 메인(GUI) 통신 시 페이로드를 경량화하고 GUI 오브젝트는 메인 스레드에서만 materialize.
   - DB 접근을 `ThumbDB` 래퍼로 통합하고 마이그레이션·트랜잭션 관리 진입점을 마련.
   - 주의: UI(사용자 조작)는 DB나 파일을 직접 수정하지 않습니다. 사용자가 UI에서 파일/캐시 관련 작업(예: 삭제, 이름 변경, 캐시 요청)을 요청하면 해당 요청을 `ImageFileSystemModel`과 image_engine에서 처리합니다. 즉, 파일 조작과 썸네일 업데이트는 image-engine과 `ImageFileSystemModel`에서만 수행되며, UI는 단순히 명령을 전달하고 결과(업데이트/시각적 반영)만 표시합니다. 또한, 썸네일 관련 작업은 대부분 자동입니다: 폴더를 열면 캐시에서 썸네일을 읽고, 썸네일이 없거나 불일치하면 자동으로 생성됩니다. 파일 오퍼레이션(이름 변경/삭제/덮어쓰기 등)이 발생하면 썸네일 재생성/갱신이 자동으로 트리거됩니다.

2) 남은 작업 (Outstanding / To-do)
 - [중] `ThumbnailCache` 통합: `ThumbDB.upsert_meta()`로 썸네일/메타 쓰기 경로 통일 및 통합 테스트 작성(구현/테스트). (이유: 현재 쓰기 경로가 분산되어 있어 메타 일관성/캐시 불일치 위험) — `DbOperator` 및 adapter 적용으로 내부 쓰기 경로를 통일했습니다.
 - [중] 동시성/DB 안정성: `ThumbDB`·`ThumbnailCache`의 동시 읽기·쓰기 시나리오에 대한 통합 테스트(멀티스레드/잠금 재현) 작성 및 재시도/롤백 정책 설계. (이유: 동시성 문제 검증이 미흡함) — 테스트 작성 및 스레드-안전 수정을 적용해 잠재적 경합을 완화했습니다.
 - [중] DB 오퍼레이터 통합: 모든 DB read/write를 중앙 `DbOperator`로 통합해 쓰레드 안전성과 일관성을 보장하도록 리팩터. 상세 설계/마이그레이션 가이드는 [db_operator_migration_plan.md](db_operator_migration_plan.md)를 참고하세요.
 - [낮] DB 마이그레이션 헬퍼: `thumb_db.py`를 위한 버전관리 마이그레이션 스크립트(샘플) 추가 및 관련 테스트(업그레이드/롤백). (이유: 런타임 스키마 보정은 있으나 명시적 마이그레이션/테스트가 없음)
 - [높] 테스트 확장: 워커 정상·오류·취소, 마이그레이션 케이스, DB 접근 오류(권한/잠금), 메타 일관성 관련 테스트 추가. (이유: 예외/중단 시나리오 커버리지가 낮음)
 - [낮] 성능 테스트: 대용량 폴더(수만 파일)에 대한 청크/메모리/스루풋 벤치마크 및 청크사이즈 튜닝. (이유: 현재 대규모 데이터셋 성능이 미측정)
 - [중] 문서: 시그널 경량화 검증 절차·롤아웃(스테이징/feature-flag) 및 마이그레이션 안내 문서화. (이유: 운영/롤아웃 위험 완화를 위함)

3) 완료된 작업 (Done / Implemented)
 - 워커 모듈 분리: `image_viewer/image_engine/fs_db_worker.py` 스켈레톤/인터페이스 도입.
 - `ThumbDB` 도입: `image_viewer/image_engine/thumb_db.py` 및 관련 유닛 테스트(`tests/test_thumb_db_wrapper.py`).
 - `meta_utils.py` 추가: mtime/메타 변환 유틸 제공으로 중복 제거.
 - `FSModel` 개선: `set_db_loader_factory()` DI 지점 추가 및 `_ThumbDbLoadWorker.run()` 분해 리팩토링.
 - GUI 안전성: 워커→메인 시그널 페이로드 경량화 보장(메인 스레드에서 GUI 오브젝트 materialize).
 - 예외 처리 개선: 불필요한 `try/except: pass` → `contextlib.suppress`로 정리.
 - 정적검사/테스트: `ruff`, `pyright`, `pytest` 통과(현재 기준).
 - `ImageFileSystemModel`: `progress` signal 추가 및 `FSDBLoadWorker.progress` 재전달 구현 + 단위 테스트 추가.

체크리스트(현재 요약)
 - 완료: 워커 분리, `ThumbDB` 도입, `meta_utils` 도입, 시그널 경량화, 리팩토링/기본 테스트.
 - 보류/진행중: `ThumbnailCache` 완전 통합, 진행률·메트릭 보강, 마이그레이션 헬퍼, 테스트/성능 확장.

권장 배포 절차
 1. 변경사항을 feature 브랜치로 커밋 후 CI(`ruff/pyright/pytest`) 확인.
 2. 레거시 shim 제거 전 스테이징에서 충분한 기간 동안 호환성/안정성 검증.



