from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from image_viewer.app.backend import BackendFacade
from image_viewer.image_engine.engine import ImageEngine
from image_viewer.infra.logger import get_logger, setup_logger
from image_viewer.infra.path_utils import abs_path_str
from image_viewer.infra.settings_manager import SettingsManager
from image_viewer.ui.styles import apply_theme

_logger = get_logger("main")
_BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
_GEN_PATH_SPLIT_MAX = 1
_GEN_PATH_PARTS = 2


def _apply_cli_logging_options(argv: list[str]) -> list[str]:
    """Parse our CLI options before Qt touches argv.

    We strip supported options from argv so Qt doesn't choke on unknown flags.
    """
    try:
        import argparse  # noqa: PLC0415

        parser = argparse.ArgumentParser(description="Image Viewer", add_help=False)
        parser.add_argument("--log-level")
        parser.add_argument("--log-cats")
        args, remaining = parser.parse_known_args(argv)

        if args.log_level:
            os.environ["IMAGE_VIEWER_LOG_LEVEL"] = str(args.log_level)
        if args.log_cats:
            os.environ["IMAGE_VIEWER_LOG_CATS"] = str(args.log_cats)

        return [argv[0], *remaining]
    except Exception:
        return argv


@contextlib.contextmanager
def _suppress_expected(*exceptions: type[BaseException]):
    """Context manager that suppresses expected exception types and logs unexpected ones.

    Usage: with _suppress_expected(TypeError, ValueError, OSError):
    """
    try:
        yield
    except exceptions:
        return
    except Exception as e:  # pragma: no cover - defensive logging
        _logger.exception("Unexpected error in suppressed block: %s", e)


class Main(QObject):
    """Deprecated legacy QML bridge.

    The application now exposes `BackendFacade` to QML and routes all inbound
    commands via `backend.dispatch(cmd, payload)`.

    This class is intentionally kept as a stub so that any accidental imports
    fail fast (the project is pre-release and does not guarantee backward
    compatibility).
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__()  # QObject doesn't accept arbitrary args
        raise RuntimeError(
            "Main(QObject) has been removed. Use BackendFacade via image_viewer.app.backend.BackendFacade."
        )


def run(argv: list[str] | None = None) -> int:
    """Entry point: create QApplication, load QML, expose `BackendFacade` backend."""
    if argv is None:
        argv = sys.argv

    argv = _apply_cli_logging_options(list(argv))

    # Apply CLI-provided env overrides (IMAGE_VIEWER_LOG_LEVEL / IMAGE_VIEWER_LOG_CATS)
    # after parsing, because many module-level loggers are created before env vars exist.
    setup_logger()
    _logger.info("Starting Image Viewer (QML)")

    # Qt Quick Controls: ensure we use a non-native style so that our QML
    # customizations (background/contentItem overrides) are supported.
    # This also avoids noisy startup warnings like:
    #   "The current style does not support customization of this control"
    QQuickStyle.setStyle("Fusion")

    app = QApplication(argv)

    settings_path = abs_path_str(_BASE_DIR / "settings.json")
    settings = SettingsManager(settings_path)

    theme = settings.get("theme", "dark")
    font_size = int(settings.get("font_size", 10))
    apply_theme(app, theme, font_size)

    engine = ImageEngine()
    backend = BackendFacade(engine=engine, settings=settings)

    # Ensure engine-owned worker threads are stopped cleanly before Qt starts
    # tearing down QObjects, otherwise we can hit:
    #   "QThread: Destroyed while thread '' is still running"
    app.aboutToQuit.connect(engine.shutdown)

    qml_engine = QQmlApplicationEngine()
    qml_engine.addImageProvider("engine", backend.engine_image_provider)
    qml_engine.addImageProvider("thumb", backend.thumb_provider)

    # Expose backend before QML loads so startup handlers can safely call it.
    qml_engine.rootContext().setContextProperty("backend", backend)

    # QML entrypoint (single source of truth): image_viewer/ui/qml/App.qml
    qml_root = _BASE_DIR / "ui" / "qml"
    qml_engine.addImportPath(str(qml_root))

    qml_file = qml_root / "App.qml"
    if not qml_file.exists():
        _logger.error("QML entrypoint not found: %s", qml_file)
        return 1

    qml_url = QUrl.fromLocalFile(str(qml_file))
    qml_engine.load(qml_url)
    if not qml_engine.rootObjects():
        _logger.error("Failed to load QML root: %s", qml_url.toString())
        return 1

    # Root object is still useful for diagnostics, but we no longer inject objects
    # via root.setProperty(). (backend is a context property.)
    root = qml_engine.rootObjects()[0]
    # QML files use `pragma ComponentBehavior: Bound`, which requires external
    # objects to be accessed via declared properties (e.g. `root.backend`).
    root.setProperty("backend", backend)

    # Startup restore: prefer reopening the last opened folder when it exists.
    # Fall back to last_parent_dir for backward compatibility.
    with contextlib.suppress(Exception):
        last_dir = getattr(settings, "last_open_dir", None) or settings.last_parent_dir
        if last_dir and os.path.isdir(last_dir):
            backend.dispatch("openFolder", {"path": last_dir})

    return app.exec()
