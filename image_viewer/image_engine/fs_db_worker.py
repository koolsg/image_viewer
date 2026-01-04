from __future__ import annotations

import time
import traceback
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from image_viewer.logger import get_logger
from image_viewer.path_utils import abs_dir, db_key

from .db.db_operator import DbOperator
from .db.thumbdb_bytes_adapter import ThumbDBBytesAdapter
from .meta_utils import to_mtime_ms_from_stat as _to_mtime_ms_from_stat

_logger = get_logger("fs_db_worker")


class FSDBLoadWorker(QObject):
    """DB 스캔/로딩 전담 워커 (스켈레톤).

    설계 요약:
    - 이 객체는 QThread에서 실행될 `run` 진입점을 제공합니다.
    - 워커는 DB/IO를 수행하고 GUI-safe 페이로드(바이트/메타/경로 목록)를 시그널로 방출합니다.
    - 워커 내부에서 Qt GUI 객체(QPixmap/QImage)를 생성하면 안 됩니다.
    """

    # 시그널 계약
    # payloads are intentionally simple (list/dict/primitive types)
    chunk_loaded = Signal(list)  # list[dict]
    missing_paths = Signal(list)  # list[str]
    finished = Signal(int)  # generation id
    error = Signal(dict)  # {"message": str, "traceback": str, "context": dict}
    progress = Signal(int, int)  # processed, total

    def __init__(
        self,
        folder_path: str = "",
        db_path: str = "",
        db_operator: DbOperator | None = None,
        **kwargs,
    ) -> None:
        parent = kwargs.get("parent")
        super().__init__(parent)
        self._db_path = str(db_path)
        self._folder_path = folder_path
        self._thumb_width = int(kwargs.get("thumb_width", 256))
        self._thumb_height = int(kwargs.get("thumb_height", 195))
        self._generation = int(kwargs.get("generation", 0))
        self._prefetch_limit = int(kwargs.get("prefetch_limit", 48))
        self._chunk_size = int(kwargs.get("chunk_size", 800))
        self._stopped = False
        self._db_operator = db_operator

    def configure(self, **kwargs) -> None:
        """구성 옵션 설정(예: chunk_size, whitelist 등)."""
        for k, v in kwargs.items():
            if hasattr(self, f"_{k}"):
                setattr(self, f"_{k}", v)

    def run(self) -> None:  # noqa: PLR0912,PLR0915
        """QThread에서 호출되는 진입점.

        구현은 DB 조회, 파일 검증, chunk emit 과 missing emit 을 담당합니다.
        예외는 `error` 시그널로 보고되어야 하며, 항상 `finished`를 emit 해야 합니다.
        """
        try:
            # Use a stable, single convention for emitted/query paths.
            # We treat `db_key()` as the canonical storage/key format
            # (absolute + drive normalized + forward slashes), which also
            # matches Qt's common '/'-style paths on Windows.
            folder = abs_dir(self._folder_path)
            if not folder.is_dir() or not Path(self._db_path).exists():
                # fallback: emit missing for current dir
                paths: list[str] = [db_key(p) for p in folder.iterdir() if p.is_file()][: self._prefetch_limit]
                if paths:
                    self.missing_paths.emit(paths)
                self.finished.emit(self._generation)
                return

            db = ThumbDBBytesAdapter(self._db_path, operator=self._db_operator)
            # Collect path stats
            paths_with_stats: list[tuple[str, int, int]] = []
            for p in folder.iterdir():
                if self._stopped:
                    self.finished.emit(self._generation)
                    return
                if not p.is_file():
                    continue
                name = p.name.lower()
                if not name.endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff")):
                    continue
                try:
                    stat = p.stat()
                    paths_with_stats.append((db_key(p), _to_mtime_ms_from_stat(stat), int(stat.st_size)))
                except Exception:
                    continue

            if not paths_with_stats:
                self.missing_paths.emit([p for (p, _m, _s) in paths_with_stats[: self._prefetch_limit]])
                self.finished.emit(self._generation)
                return

            # Progress/metrics
            total = len(paths_with_stats)
            processed = 0
            start_ts = time.time()
            _logger.debug("FSDBLoadWorker run: total files=%d chunk_size=%d", total, self._chunk_size)
            # emit initial progress
            with suppress(Exception):
                self.progress.emit(0, total)

            have_thumb: set[str] = set()
            # Use ThumbDBBytesAdapter (via ThumbDBBytesAdapter/ThumbDBOperator) to query rows in chunks
            for i in range(0, len(paths_with_stats), self._chunk_size):
                if self._stopped:
                    self.finished.emit(self._generation)
                    return
                chunk = paths_with_stats[i : i + self._chunk_size]
                paths = [path for (path, _m, _s) in chunk]
                # Fast lookup for current file stats using canonical DB keys.
                cur_by_key: dict[str, tuple[int, int]] = {p: (mt, sz) for (p, mt, sz) in chunk}
                rows = db.get_rows_for_paths(paths)
                if not rows:
                    processed += len(chunk)
                    with suppress(Exception):
                        self.progress.emit(processed, total)
                    continue
                filtered: list[dict] = []
                rows_total = 0
                rows_matched = 0
                rows_valid = 0
                for path, thumbnail, w, h, db_mtime, db_size, db_tw, db_th, _created_at in rows:
                    rows_total += 1
                    # Rows are stored and queried using canonical db_key().
                    key = str(path)

                    cur = cur_by_key.get(key)
                    if cur is None:
                        continue
                    rows_matched += 1
                    cur_mtime_ms, cur_size = cur
                    try:
                        if db_size is None or int(db_size) != int(cur_size):
                            continue
                        if db_mtime is None or int(db_mtime) != int(cur_mtime_ms):
                            continue
                        # If DB stored thumbnail dimensions, ensure they match current target.
                        # If they don't match, treat as invalid so the thumbnail gets regenerated.
                        if db_tw is not None and int(db_tw) not in (0, self._thumb_width):
                            continue
                        if db_th is not None and int(db_th) not in (0, self._thumb_height):
                            continue
                    except Exception:
                        continue
                    rows_valid += 1

                    thumb_present = False
                    try:
                        thumb_present = thumbnail is not None and len(thumbnail) > 0
                    except Exception:
                        thumb_present = False

                    filtered.append(
                        {
                            # Emit canonical path so downstream caches/keying are stable.
                            "path": key,
                            "thumbnail": thumbnail,
                            "width": w,
                            "height": h,
                            "mtime": db_mtime,
                            "size": db_size,
                            "thumb_width": db_tw,
                            "thumb_height": db_th,
                        }
                    )
                    # Only treat as "have thumbnail" if bytes are present and valid.
                    # Otherwise, the core should regenerate it.
                    if thumb_present:
                        have_thumb.add(key)
                if filtered:
                    self.chunk_loaded.emit(filtered)
                _logger.debug(
                    "FSDBLoadWorker chunk: paths=%d db_rows=%d matched=%d valid=%d",
                    len(chunk),
                    rows_total,
                    rows_matched,
                    rows_valid,
                )
                # update processed count and emit progress
                processed += len(chunk)
                with suppress(Exception):
                    self.progress.emit(processed, total)

            missing = [p for (p, _m, _s) in paths_with_stats if p not in have_thumb]
            emit_count = min(len(missing), self._prefetch_limit)
            _logger.debug(
                "FSDBLoadWorker missing/outdated: total_missing=%d have_thumb=%d emit=%d limit=%d",
                len(missing),
                len(have_thumb),
                emit_count,
                self._prefetch_limit,
            )
            if missing:
                self.missing_paths.emit(missing[: self._prefetch_limit])
            elapsed = time.time() - start_ts
            _logger.debug("FSDBLoadWorker finished: processed=%d total=%d elapsed=%.3fs", processed, total, elapsed)
            with suppress(Exception):
                self.progress.emit(total, total)

            self.finished.emit(self._generation)
        except Exception as exc:
            self.error.emit(
                {
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                    "context": {"folder": self._folder_path, "db": self._db_path},
                }
            )
            self.finished.emit(self._generation)

    def stop(self) -> None:
        """중단 요청: run 루프는 주기적으로 `_stopped`를 확인해야 함."""
        self._stopped = True
