import logging
import os
import sys

_SESSION_LOG_NAME = "image-view_session.log"


def setup_logger(level: int = logging.INFO, name: str = "image_viewer") -> logging.Logger:
    """Create or update the project logger.

    - Respects env overrides IMAGE_VIEWER_LOG_LEVEL/IMAGE_VIEWER_LOG_CATS on every call
      (so late CLI parsing can still take effect).
    - Ensures there is exactly one StreamHandler on the base logger and updates
      its formatter/filters instead of bailing out early.
    """
    logger = logging.getLogger(name)

    # Resolve level from env (override default)
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

    # Ensure there is exactly one stderr StreamHandler and one session FileHandler.
    stream_handler: logging.StreamHandler | None = None
    file_handler: logging.FileHandler | None = None
    for h in list(logger.handlers):
        if isinstance(h, logging.FileHandler):
            try:
                if os.path.basename(getattr(h, "baseFilename", "")) == _SESSION_LOG_NAME:
                    file_handler = h
            except Exception:
                continue
        elif isinstance(h, logging.StreamHandler):
            try:
                if getattr(h, "stream", None) is sys.stderr:
                    stream_handler = h
            except Exception:
                continue

    if stream_handler is None:
        stream_handler = logging.StreamHandler(stream=sys.stderr)
        logger.addHandler(stream_handler)

    if file_handler is None:
        # Overwrite on each process start.
        file_handler = logging.FileHandler(_SESSION_LOG_NAME, mode="w", encoding="utf-8")
        logger.addHandler(file_handler)

    # Formatter (idempotent)
    # Do not include the full logger name in messages to keep output concise
    fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    stream_handler.setFormatter(fmt)
    file_handler.setFormatter(fmt)

    # Update category filter from env
    # Clear previous filters and apply a new one if cats provided
    stream_handler.filters.clear()
    file_handler.filters.clear()
    cats = (os.getenv("IMAGE_VIEWER_LOG_CATS") or "").strip()
    if cats:
        allowed = {c.strip() for c in cats.split(",") if c.strip()}

        class _CategoryFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                # record.name like: image_viewer.main, image_viewer.loader
                parts = (record.name or "").split(".")
                suffix = parts[-1] if parts else record.name
                return suffix in allowed

        stream_handler.addFilter(_CategoryFilter())
        file_handler.addFilter(_CategoryFilter())

    # Do not propagate beyond the project logger
    logger.propagate = False
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    base = setup_logger()
    return base if not name else base.getChild(name)
