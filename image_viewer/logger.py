import contextlib
import logging
import os
import sys

# Session file logger removed: do not write session logs to disk by default


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

    # Ensure there is exactly one stderr StreamHandler. We do not create a
    # FileHandler for session logs; the application avoids writing a session log
    # file by default to respect environments where disk writes are undesired.
    stream_handler: logging.StreamHandler | None = None
    for h in list(logger.handlers):
        if isinstance(h, logging.StreamHandler):
            try:
                if getattr(h, "stream", None) is sys.stderr:
                    stream_handler = h
            except Exception:
                continue

    if stream_handler is None:
        stream_handler = logging.StreamHandler(stream=sys.stderr)
        logger.addHandler(stream_handler)

    # Formatter (idempotent)
    # Do not include the full logger name in messages to keep output concise
    fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    stream_handler.setFormatter(fmt)

    # Update category filter from env
    # Clear previous filters and apply a new one if cats provided
    stream_handler.filters.clear()
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

    # Install a lightweight stderr wrapper to filter noisy 'FIXME qt_isinstance' lines
    # Controlled by the IMAGE_VIEWER_FILTER_QT_FIXME env var; default is enabled so users are
    # not spammed by known Qt/pybind11 warnings. Set env var to '0' or 'false' to opt-out.
    try:
        env = os.getenv("IMAGE_VIEWER_FILTER_QT_FIXME")
        enabled = True if env is None else env.strip().lower() in ("1", "true", "yes")

        if enabled and not getattr(sys.stderr, "_filtered_by_image_viewer", False):
            outfile = os.path.join(os.getcwd(), "debug.log.filtered")

            class _FilteredStderr:
                """Wrap stderr and suppress known noisy lines while recording them to a file.

                Suppresses lines containing the text 'FIXME qt_isinstance' and appends them to
                a separate file (debug.log.filtered) so diagnostics are preserved even when
                the lines are suppressed from stderr.
                """

                def __init__(self, orig, out_path: str):
                    self._orig = orig
                    self._out_path = out_path
                    # visible marker for tests
                    self._filtered_by_image_viewer = True

                def write(self, s: str) -> None:  # pragma: no cover - thin wrapper
                    try:
                        if isinstance(s, str) and "FIXME qt_isinstance" in s:
                            # Persist the suppressed line for later inspection
                            with contextlib.suppress(Exception), open(self._out_path, "a", encoding="utf-8") as f:
                                f.write(s)
                            return
                    except Exception:
                        pass
                    with contextlib.suppress(Exception):
                        self._orig.write(s)

                def flush(self) -> None:  # pragma: no cover - thin wrapper
                    with contextlib.suppress(Exception):
                        return getattr(self._orig, "flush", lambda: None)()

                def isatty(self) -> bool:  # pragma: no cover - thin wrapper
                    try:
                        return getattr(self._orig, "isatty", lambda: False)()
                    except Exception:
                        return False

            sys.stderr = _FilteredStderr(sys.stderr, outfile)
    except Exception:
        # Never fail logger setup for this convenience wrapper
        pass

    # Do not propagate beyond the project logger
    logger.propagate = False
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    base = setup_logger()
    return base if not name else base.getChild(name)
