"""Image thumbnail grid widget (for file explorer mode)"""

import hashlib
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QImage, QImageWriter, QPixmap
from PySide6.QtWidgets import QGridLayout, QPushButton, QScrollArea, QWidget

from .logger import get_logger

_logger = get_logger("ui_explorer_grid")


class ThumbnailGridWidget(QScrollArea):
    """Widget that displays image thumbnails in a grid"""

    image_selected = Signal(str)  # Image selection signal

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)

        self._container = QWidget()
        self._layout = QGridLayout(self._container)
        self._layout.setSpacing(10)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self.setWidget(self._container)

        self._thumb_buttons: dict[str, QPushButton] = {}
        self._thumb_cache: OrderedDict[str, QPixmap] = OrderedDict()
        # Maximum LRU cache items
        self._max_thumb_cache: int = 512
        # Disk cache root (project local)
        self._disk_cache_dir: Path = Path(".cache/image_viewer_thumbs")
        # Worker for thumbnail saving (disk I/O offloading)
        self._io_pool = ThreadPoolExecutor(max_workers=2)
        # Default thumbnail size (width x height)
        self._thumb_size: tuple[int, int] = (256, 195)
        # Button size (thumbnail + margin)
        self._button_w = self._thumb_size[0] + 20
        self._button_h = self._thumb_size[1] + 20
        # Currently displayed image path list (for layout recalculation)
        self._image_paths: list[str] = []
        self._image_extensions = {
            ".jpg",
            ".jpeg",
            ".png",
            ".bmp",
            ".gif",
            ".webp",
            ".tif",
            ".tiff",
        }
        self._loader = None  # Loader instance (lazy setup)

        _logger.debug("ThumbnailGridWidget initialized")

    def _save_disk_thumb_qimage_async(self, image_path: str, q_image: QImage) -> None:
        try:
            q_copy = q_image.copy()
            p = self._get_disk_thumb_path(image_path)
            tmp = p.with_suffix(p.suffix + ".part")
            self._disk_cache_dir.mkdir(parents=True, exist_ok=True)

            def _job():
                try:
                    writer = QImageWriter(str(tmp), b"JPG")
                    writer.setQuality(85)
                    ok = writer.write(q_copy)
                    if not ok:
                        try:
                            # fallback to direct save
                            q_copy.save(str(tmp), "JPG", quality=85)
                        except Exception:
                            return
                    # Atomic replacement: replace partial file with final file
                    os.replace(str(tmp), str(p))
                except Exception as ex:
                    try:
                        if tmp.exists():
                            tmp.unlink(missing_ok=True)  # type: ignore[arg-type]
                    except Exception:
                        pass
                    _logger.debug(
                        "disk cache save async error for %s: %s", image_path, ex
                    )

            self._io_pool.submit(_job)
        except Exception as ex:
            _logger.debug("schedule disk save error for %s: %s", image_path, ex)

    # ---- Cache helpers ------------------------------------------------------
    def _get_disk_thumb_path(self, image_path: str) -> Path:
        try:
            abs_path = os.path.abspath(image_path)
            w, h = self._thumb_size
            key = f"{abs_path}|{w}x{h}".encode()
            digest = hashlib.sha1(key).hexdigest()
            return self._disk_cache_dir / f"{digest}.jpg"
        except Exception:
            safe = image_path.replace(os.sep, "_").replace(":", "_")
            return self._disk_cache_dir / f"fallback_{safe}.jpg"

    def _load_disk_thumb(self, image_path: str) -> QPixmap | None:
        try:
            p = self._get_disk_thumb_path(image_path)
            if not p.exists():
                return None
            pixmap = QPixmap(str(p))
            if pixmap.isNull():
                return None
            return pixmap
        except Exception as ex:
            _logger.debug("disk cache load error for %s: %s", image_path, ex)
            return None

    def _save_disk_thumb(self, image_path: str, pixmap: QPixmap) -> None:
        try:
            self._disk_cache_dir.mkdir(parents=True, exist_ok=True)
            p = self._get_disk_thumb_path(image_path)
            # Save as PNG (lossless, no quality option needed)
            pixmap.save(str(p), "PNG")
        except Exception as ex:
            _logger.debug("disk cache save error for %s: %s", image_path, ex)

    def _touch_lru(self, image_path: str, pixmap: QPixmap) -> None:
        try:
            # Move order on update
            if image_path in self._thumb_cache:
                try:
                    self._thumb_cache.move_to_end(image_path)
                except Exception:
                    # Re-insert if not OrderedDict
                    self._thumb_cache.pop(image_path, None)
                    self._thumb_cache[image_path] = pixmap
            else:
                self._thumb_cache[image_path] = pixmap
            # Remove FIFO if capacity is exceeded
            while len(self._thumb_cache) > self._max_thumb_cache:
                try:
                    self._thumb_cache.popitem(last=False)
                except Exception:
                    break
        except Exception as ex:
            _logger.debug("lru touch error: %s", ex)

    # Public API --------------------------------------------------------------
    def set_loader(self, loader) -> None:
        """Connect a Loader instance and bind its signals.
        If loader is None, disconnects the existing one.
        """
        try:
            # Disconnect existing connection
            try:
                if self._loader is not None:
                    self._loader.image_decoded.disconnect(self._on_thumbnail_ready)
            except Exception:
                pass

            self._loader = loader
            if self._loader:
                self._loader.image_decoded.connect(self._on_thumbnail_ready)
                _logger.debug("loader connected to ThumbnailGridWidget")
            else:
                _logger.debug("loader detached from ThumbnailGridWidget")
        except Exception as ex:
            _logger.debug("error setting loader: %s", ex)

    def load_folder(self, folder_path: str) -> None:
        """Asynchronously load images from a folder and display them in a grid."""
        try:
            self._clear_grid()

            # Collect images from the folder
            images: list[str] = []
            try:
                folder = Path(folder_path)
                if not folder.is_dir():
                    _logger.warning("not a directory: %s", folder_path)
                    return
                images = sorted(
                    [
                        str(p)
                        for p in folder.iterdir()
                        if p.is_file() and p.suffix.lower() in self._image_extensions
                    ]
                )
            except (PermissionError, OSError) as ex:
                _logger.debug("failed to list folder: %s, error=%s", folder_path, ex)
                return

            if not images:
                _logger.debug("no images found in: %s", folder_path)
                return

            # Dynamically calculate columns and create buttons
            self._image_paths = images
            cols = self._compute_columns()
            max_row = -1
            for idx, image_path in enumerate(images):
                row = idx // cols
                col = idx % cols
                max_row = max(max_row, row)

                btn = QPushButton()
                btn.setFixedSize(self._button_w, self._button_h)
                btn.setToolTip(Path(image_path).name)
                btn.clicked.connect(
                    lambda checked=False, p=image_path: self._on_image_clicked(p)
                )

                self._layout.addWidget(btn, row, col)
                self._thumb_buttons[image_path] = btn

                # If in cache, use immediately; otherwise, request
                if image_path in self._thumb_cache:
                    self._set_button_icon(btn, self._thumb_cache[image_path])
                else:
                    self._request_thumbnail(image_path)

            # Bottom stretch
            if max_row >= 0:
                self._layout.setRowStretch(max_row + 1, 1)

            # Safe relayout (to handle view size changes)
            self._relayout()

            _logger.debug("grid loaded: folder=%s, images=%d", folder_path, len(images))
        except Exception as ex:
            _logger.error("failed to load_folder: %s", ex)

    def resume_pending_thumbnails(self) -> None:
        """Re-issue thumbnail requests for items that are still empty."""
        try:
            if not self._image_paths:
                return
            for path in self._image_paths:
                btn = self._thumb_buttons.get(path)
                if btn is None:
                    continue
                try:
                    icon = btn.icon()
                except Exception:
                    icon = None
                has_icon = icon is not None and not icon.isNull()
                if not has_icon:
                    self._request_thumbnail(path)
        except Exception as ex:
            _logger.debug("resume_pending_thumbnails failed: %s", ex)

    def set_thumbnail_size_wh(self, width: int, height: int) -> None:
        """Set thumbnail width/height in pixels."""
        try:
            w = max(32, min(1024, int(width)))
            h = max(32, min(1024, int(height)))
            self._thumb_size = (w, h)
            self._button_w = w + 20
            self._button_h = h + 20
            for btn in self._thumb_buttons.values():
                btn.setFixedSize(self._button_w, self._button_h)
            self._relayout()
        except Exception as ex:
            _logger.debug("set_thumbnail_size_wh failed: %s", ex)

    def set_thumbnail_size(self, size: int) -> None:
        """Backward compatibility API for setting square size."""
        self.set_thumbnail_size_wh(size, size)

    def set_horizontal_spacing(self, spacing: int) -> None:
        """Set horizontal spacing."""
        try:
            spacing = max(0, min(64, int(spacing)))
            try:
                self._layout.setHorizontalSpacing(spacing)
            except Exception:
                self._layout.setSpacing(spacing)
            self._relayout()
        except Exception as ex:
            _logger.debug("set_horizontal_spacing failed: %s", ex)

    def get_thumbnail_size(self) -> tuple[int, int]:
        return self._thumb_size

    def get_horizontal_spacing(self) -> int:
        try:
            hs = self._layout.horizontalSpacing()
            if isinstance(hs, int) and hs >= 0:
                return hs
        except Exception:
            pass
        return self._layout.spacing()

    # Internal helpers --------------------------------------------------------
    def _compute_columns(self) -> int:
        try:
            w = self.viewport().width()
            if w <= 0:
                return 4  # Initial safe value
            m = self._layout.contentsMargins()
            try:
                hs = self._layout.horizontalSpacing()
                if hs is None or hs < 0:
                    hs = self._layout.spacing()
            except Exception:
                hs = self._layout.spacing()
            avail = max(1, w - (m.left() + m.right()))
            unit = max(1, self._button_w + hs)
            cols = max(1, int((avail + hs) // unit))
            return cols
        except Exception as ex:
            _logger.debug("_compute_columns failed: %s", ex)
            return 4

    def _relayout(self) -> None:
        try:
            cols = self._compute_columns()
            # Remove all items (preserving widgets)
            while self._layout.count() > 0:
                self._layout.takeAt(0)
            max_row = -1
            for idx, path in enumerate(self._image_paths):
                row = idx // cols
                col = idx % cols
                btn = self._thumb_buttons.get(path)
                if btn is not None:
                    btn.setFixedSize(self._button_w, self._button_h)
                    self._layout.addWidget(btn, row, col)
                    max_row = max(max_row, row)
            if max_row >= 0:
                self._layout.setRowStretch(max_row + 1, 1)
        except Exception as ex:
            _logger.debug("_relayout failed: %s", ex)

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        try:
            if self._thumb_buttons:
                self._relayout()
        except Exception:
            pass

    def _request_thumbnail(self, image_path: str) -> None:
        try:
            # 1) Check disk cache first
            pix = self._load_disk_thumb(image_path)
            if pix is not None and not pix.isNull():
                # Update button and LRU only if the grid is visible (irrelevant to click UX if not)
                if self.isVisible():
                    if image_path in self._thumb_buttons:
                        self._set_button_icon(self._thumb_buttons[image_path], pix)
                    self._touch_lru(image_path, pix)
                _logger.debug("thumbnail from disk cache: %s", image_path)
                return

            # 2) Request from loader
            if not self._loader:
                _logger.debug(
                    "loader not set, skipping thumbnail request for %s", image_path
                )
                return
            self._loader.request_load(
                image_path,
                target_width=self._thumb_size[0],
                target_height=self._thumb_size[1],
                size="both",
            )
            _logger.debug("thumbnail requested: %s", image_path)
        except Exception as ex:
            _logger.debug("error requesting thumbnail: %s, error=%s", image_path, ex)

    def _on_thumbnail_ready(self, path: str, image_data, error) -> None:
        try:
            if error:
                _logger.debug("thumbnail decode error for %s: %s", path, error)
                return
            if image_data is None:
                return
            # Convert numpy array to QImage/QPixmap
            try:
                height, width, _ = image_data.shape
                bytes_per_line = 3 * width
                q_image = QImage(
                    image_data.data, width, height, bytes_per_line, QImage.Format_RGB888
                )
                # Save to disk asynchronously in a worker thread
                self._save_disk_thumb_qimage_async(path, q_image)
                pixmap = QPixmap.fromImage(q_image)
                if not pixmap.isNull() and self.isVisible():
                    # Update LRU + button only when visible
                    self._touch_lru(path, pixmap)
                    if path in self._thumb_buttons:
                        btn = self._thumb_buttons[path]
                        self._set_button_icon(btn, pixmap)
                        _logger.debug("thumbnail set: %s", path)
            except Exception as ex:
                _logger.debug("error converting thumbnail to pixmap/save: %s", ex)
        except Exception as ex:
            _logger.debug("error in _on_thumbnail_ready: %s", ex)

    def _set_button_icon(self, button: QPushButton, pixmap: QPixmap) -> None:
        try:
            scaled = pixmap.scaled(
                self._thumb_size[0],
                self._thumb_size[1],
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            button.setIcon(QIcon(scaled))
            button.setIconSize(scaled.size())
            button.setText("")
        except Exception as ex:
            _logger.debug("error setting button icon: %s", ex)

    def _on_image_clicked(self, image_path: str) -> None:
        try:
            if Path(image_path).exists():
                self.image_selected.emit(image_path)
                _logger.debug("image selected: %s", image_path)
        except Exception as ex:
            _logger.debug("error on image click: %s", ex)

    def _clear_grid(self) -> None:
        try:
            while self._layout.count() > 0:
                item = self._layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._thumb_buttons.clear()
            self._image_paths = []
        except Exception as ex:
            _logger.debug("error clearing grid: %s", ex)
