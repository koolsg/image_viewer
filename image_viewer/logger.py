import logging
import os
import sys


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

    # Get or create single stream handler
    if logger.handlers:
        handler = logger.handlers[0]
    else:
        handler = logging.StreamHandler(stream=sys.stderr)
        logger.addHandler(handler)

    # Formatter (idempotent)
    fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(fmt)

    # Update category filter from env
    # Clear previous filters and apply a new one if cats provided
    handler.filters.clear()
    cats = (os.getenv("IMAGE_VIEWER_LOG_CATS") or "").strip()
    if cats:
        allowed = {c.strip() for c in cats.split(",") if c.strip()}

        class _CategoryFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                # record.name like: image_viewer.main, image_viewer.loader
                parts = (record.name or "").split(".")
                suffix = parts[-1] if parts else record.name
                return suffix in allowed

        handler.addFilter(_CategoryFilter())

    # Do not propagate beyond the project logger
    logger.propagate = False
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    base = setup_logger()
    return base if not name else base.getChild(name)
