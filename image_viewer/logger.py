import logging
import sys
from typing import Optional


import os

def setup_logger(level: int = logging.INFO, name: str = "image_viewer") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    # 환경변수 우선 적용
    env_level = (os.getenv("IMAGE_VIEWER_LOG_LEVEL") or "").strip().lower()
    if env_level:
        level_map = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }
        level = level_map.get(env_level, level)

    logger.setLevel(level)

    handler = logging.StreamHandler(stream=sys.stderr)
    fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(fmt)

    # 카테고리 필터 (쉼표 구분)
    cats = (os.getenv("IMAGE_VIEWER_LOG_CATS") or "").strip()
    if cats:
        allowed = {c.strip() for c in cats.split(",") if c.strip()}

        class _CategoryFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                # record.name 예: image_viewer.main, image_viewer.loader
                name = record.name
                # 루트 이름 제거
                if name.startswith(f"{name.split('.')[0]}"):
                    pass
                # child 이름 추출
                parts = name.split(".")
                suffix = parts[-1] if parts else name
                return suffix in allowed

        handler.addFilter(_CategoryFilter())

    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    base = setup_logger()
    return base if not name else base.getChild(name)

