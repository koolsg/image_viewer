import sys
import os
import json
import threading
import queue
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from PySide6.QtCore import Qt, QObject, Signal, QRectF
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QFileDialog,
    QMenu,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QStatusBar,
)
from PySide6.QtGui import QPixmap, QAction, QKeySequence, QImage, QShortcut, QActionGroup, QPainter
from .decoder import decode_image

# --- Top-level function for the Process Pool ---
# This function must be at the top level to be pickleable by multiprocessing
def decode_image(file_path, file_bytes):
    # shim retained for backward compatibility if imported elsewhere
    from .decoder import decode_image as _decode
    return _decode(file_path, file_bytes)


class Loader(QObject):
    """Manages the background loading and decoding pipeline."""
    image_decoded = Signal(str, object, object) # path, numpy_array, error

    def __init__(self):
        super().__init__()
        self.executor = ProcessPoolExecutor()
        # Parallel I/O pool to improve warmup and prefetch throughput
        max_io = max(2, min(4, (os.cpu_count() or 2)))
        self.io_pool = ThreadPoolExecutor(max_workers=max_io)
        self._pending = set()
        self._lock = threading.Lock()

    def _io_and_decode(self, file_path: str):
        """Read file bytes and submit decode to process pool."""
        try:
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
            future = self.executor.submit(decode_image, file_path, file_bytes)
            future.add_done_callback(self.on_decode_finished)
        except Exception as e:
            with self._lock:
                self._pending.discard(file_path)
            self.image_decoded.emit(file_path, None, str(e))

    def on_decode_finished(self, future):
        """Callback that runs when a decoding process is finished."""
        path, data, error = future.result()
        with self._lock:
            self._pending.discard(path)
        self.image_decoded.emit(path, data, error)

    def request_load(self, path):
        with self._lock:
            if path in self._pending:
                return
            self._pending.add(path)
        self.io_pool.submit(self._io_and_decode, path)

    def shutdown(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.io_pool.shutdown(wait=False, cancel_futures=True)  # type: ignore
        except TypeError:
            self.io_pool.shutdown(wait=False)


class ImageCanvas(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pix_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pix_item)
        self._fit_to_window = True
        self._zoom = 1.0
        self._hq_downscale = False  # High-quality downscale when in Fit
        self._hq_pixmap = None      # Cached pixmap for current Fit size
        # For temporary zoom-on-press behavior
        self._press_zoom_saved = None
        self._press_fit_saved = None
        self._press_zoom_multiplier = 2.0
        self.setRenderHints(self.renderHints())
        # Use high-quality pixmap scaling when the view transforms images
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def get_fit_scale(self) -> float:
        pix = self._pix_item.pixmap()
        if pix.isNull():
            return 1.0
        pw = max(1, pix.width())
        ph = max(1, pix.height())
        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())
        sx = vw / pw
        sy = vh / ph
        # KeepAspectRatio uses the limiting dimension
        return min(sx, sy)

    def set_pixmap(self, pixmap: QPixmap):
        self._pix_item.setPixmap(pixmap)
        self._pix_item.setOffset(0, 0)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._hq_pixmap = None  # reset HQ cache on new image
        self.apply_current_view()

    def wheelEvent(self, event):
        if self._pix_item.pixmap().isNull():
            return
        # Ctrl+wheel zooms; plain wheel navigates images
        if event.modifiers() & Qt.ControlModifier:
            angle = event.angleDelta().y()
            factor = 1.25 if angle > 0 else 0.8
            self.zoom_by(factor)
        else:
            angle = event.angleDelta().y()
            parent = self.parent()
            # Positive = wheel up => prev, Negative = wheel down => next
            if angle > 0 and hasattr(parent, "prev_image"):
                parent.prev_image()
                event.accept()
            elif angle < 0 and hasattr(parent, "next_image"):
                parent.next_image()
                event.accept()
            else:
                super().wheelEvent(event)

    def mousePressEvent(self, event):
        # Map browser back/forward mouse buttons to zoom out/in
        # Qt Extra buttons: XButton1 (Back), XButton2 (Forward)
        try:
            btn = event.button()
        except Exception:
            btn = None
        # Middle click behaves like Space: snap to global view
        if btn == Qt.MiddleButton:
            parent = self.parent()
            if hasattr(parent, "snap_to_global_view"):
                parent.snap_to_global_view()
                event.accept()
                return
        if btn == Qt.LeftButton:
            # Save current view state and apply temporary zoom relative to FIT scale
            if self._press_zoom_saved is None and self._press_fit_saved is None:
                self._press_zoom_saved = self._zoom
                self._press_fit_saved = self._fit_to_window
                # Exit fit and apply multiplier relative to current FIT scale
                self._fit_to_window = False
                mul = float(getattr(self, "_press_zoom_multiplier", 2.0) or 2.0)
                fit_scale = self.get_fit_scale()
                target = fit_scale * mul
                self._zoom = max(0.05, min(target, 20.0))
                self.apply_current_view()
            event.accept()
            # Keep default drag/pan behavior as well
            super().mousePressEvent(event)
            return
        if btn == Qt.XButton1:  # Back
            self.zoom_by(0.8)
            event.accept()
            return
        elif btn == Qt.XButton2:  # Forward
            self.zoom_by(1.25)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        try:
            btn = event.button()
        except Exception:
            btn = None
        if btn == Qt.LeftButton and (self._press_zoom_saved is not None or self._press_fit_saved is not None):
            # Restore previous view state exactly
            prev_zoom = self._press_zoom_saved if self._press_zoom_saved is not None else 1.0
            prev_fit = bool(self._press_fit_saved)
            self._press_zoom_saved = None
            self._press_fit_saved = None
            self._fit_to_window = prev_fit
            self._zoom = prev_zoom
            self.apply_current_view()
            event.accept()
            # Allow default behavior too
            super().mouseReleaseEvent(event)
            return
        super().mouseReleaseEvent(event)

    def toggle_fit(self):
        self._fit_to_window = not self._fit_to_window
        if self._fit_to_window:
            self.fit_to_view()

    def is_fit(self):
        return self._fit_to_window

    def fit_to_view(self):
        pix = self._pix_item.pixmap()
        if pix.isNull():
            return
        self._zoom = 1.0
        self.fitInView(self._pix_item, Qt.KeepAspectRatio)

    def zoom_by(self, factor: float):
        self._fit_to_window = False
        self._zoom *= factor
        # clamp zoom
        self._zoom = max(0.05, min(self._zoom, 20.0))
        self.scale(factor, factor)

    def reset_zoom(self):
        self._fit_to_window = False
        self._zoom = 1.0
        self.resetTransform()

    def apply_current_view(self):
        pix = self._pix_item.pixmap()
        if pix.isNull():
            return
        self.resetTransform()
        if self._fit_to_window:
            if self._hq_downscale:
                print("[HQ] route chosen (fit mode)")
                # Render a high-quality downscaled pixmap to fit viewport
                self._apply_hq_fit()
            else:
                self.fitInView(self._pix_item, Qt.KeepAspectRatio)
        else:
            if abs(self._zoom - 1.0) > 1e-6:
                self.scale(self._zoom, self._zoom)

    def _apply_hq_fit(self):
        pix = self._pix_item.pixmap()
        if pix.isNull():
            return
        # Compute target size keeping aspect ratio within viewport
        vw, vh = self.viewport().width(), self.viewport().height()
        pw, ph = pix.width(), pix.height()
        if vw <= 0 or vh <= 0 or pw <= 0 or ph <= 0:
            print("[HQ] invalid dims, fallback fitInView")
            self.fitInView(self._pix_item, Qt.KeepAspectRatio)
            return
        sx = vw / pw
        sy = vh / ph
        scale = min(sx, sy)
        tw, th = max(1, int(pw * scale)), max(1, int(ph * scale))

        # Reuse cached HQ pixmap if size matches
        if self._hq_pixmap is not None and self._hq_pixmap.width() == tw and self._hq_pixmap.height() == th:
            print(f"[HQ] cached pixmap reused: {tw}x{th}")
            self._pix_item.setPixmap(self._hq_pixmap)
            self.fitInView(self._pix_item, Qt.KeepAspectRatio)
            return

        try:
            # Convert source to QImage then to PIL for Lanczos resize
            qimg = pix.toImage().convertToFormat(QImage.Format_RGB888)
            width, height = qimg.width(), qimg.height()
            bpl = qimg.bytesPerLine()
            import numpy as np  # lazy use
            # Convert to bytes and reshape with stride (bytesPerLine) to handle row padding
            buf = qimg.bits().tobytes()
            if len(buf) < bpl * height:
                print(f"[HQ] buffer too small: len={len(buf)} bpl={bpl} h={height}")
                self.fitInView(self._pix_item, Qt.KeepAspectRatio)
                return
            arr = np.frombuffer(buf, dtype=np.uint8).reshape((height, bpl))[:, : (width * 3)]
            arr = arr.reshape((height, width, 3))
            try:
                from PIL import Image
            except Exception:
                # Fallback to normal fit if Pillow missing
                print("[HQ] pillow missing -> fallback fitInView")
                self.fitInView(self._pix_item, Qt.KeepAspectRatio)
                return
            im = Image.fromarray(arr, mode="RGB")
            im_resized = im.resize((tw, th), Image.LANCZOS)
            arr2 = np.asarray(im_resized)
            h2, w2, _ = arr2.shape
            qimg2 = QImage(arr2.data, w2, h2, w2 * 3, QImage.Format_RGB888)
            new_pix = QPixmap.fromImage(qimg2)
            self._hq_pixmap = new_pix
            self._pix_item.setPixmap(new_pix)
            self._scene.setSceneRect(QRectF(new_pix.rect()))
            self.fitInView(self._pix_item, Qt.KeepAspectRatio)
            print(f"[HQ] generated pixmap: {w2}x{h2}")
        except Exception as e:
            # On any error, fall back to normal fit
            print(f"[HQ] exception -> fallback: {e}")
            self.fitInView(self._pix_item, Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # If in fit mode, keep the image fitted to the new viewport size
        if self._fit_to_window:
            # In HQ mode regenerate cached pixmap on size change
            if self._hq_downscale:
                print("[HQ] resize -> invalidate cache")
                self._hq_pixmap = None
            self.apply_current_view()


class ImageViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Viewer")
        self.resize(1024, 768)

        self.image_files = []
        self.current_index = -1
        from collections import OrderedDict
        self.pixmap_cache = OrderedDict()
        self.cache_size = 20 # Max number of pixmaps to keep in cache
        self.supported_formats = (".png", ".jpg", ".jpeg", ".webp")

        self.canvas = ImageCanvas(self)
        self.setCentralWidget(self.canvas)
        self._placeholder = QLabel("Press Ctrl+O to open a folder")
        self._placeholder.setStyleSheet("QLabel { color: grey; font-size: 20px; }")
        self._placeholder.setAlignment(Qt.AlignCenter)
        # Overlay approach skipped; we show placeholder text in title/status when empty

        self._create_menus()
        self._create_statusbar()

        self.loader = Loader()
        self.loader.image_decoded.connect(self.on_image_ready)

        # Settings file path (stored next to this module)
        self._settings_path = os.path.join(os.path.dirname(__file__), "settings.json")

    def _create_menus(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        open_action = QAction("&Open Folder...", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self.open_folder)
        file_menu.addAction(open_action)

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menu_bar.addMenu("&View")
        # View mode actions (exclusive)
        self.view_group = QActionGroup(self)
        self.view_group.setExclusive(True)

        self.fit_action = QAction("&Fit to Window", self, checkable=True)
        self.fit_action.setShortcut("F")
        self.fit_action.setChecked(True)
        self.fit_action.triggered.connect(self.choose_fit)
        self.view_group.addAction(self.fit_action)
        view_menu.addAction(self.fit_action)

        self.actual_action = QAction("&Actual Size", self, checkable=True)
        self.actual_action.setShortcut("1")
        self.actual_action.setChecked(False)
        self.actual_action.triggered.connect(self.choose_actual)
        self.view_group.addAction(self.actual_action)
        view_menu.addAction(self.actual_action)

        # High-quality downscale toggle (Fit only)
        self.hq_downscale_action = QAction("High-&quality downscale (Fit)", self, checkable=True)
        self.hq_downscale_action.setChecked(False)
        self.hq_downscale_action.triggered.connect(self.toggle_hq_downscale)
        view_menu.addAction(self.hq_downscale_action)

        # Press Zoom Multiplier: user-defined only
        multiplier_menu = view_menu.addMenu("Press Zoom &Multiplier")
        custom_act = QAction("&Custom...", self)
        custom_act.triggered.connect(self.prompt_custom_multiplier)
        multiplier_menu.addAction(custom_act)

        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.triggered.connect(lambda: self.zoom_by(1.25))
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.triggered.connect(lambda: self.zoom_by(0.8))
        view_menu.addAction(zoom_out_action)

        # Full Screen toggle
        self.fullscreen_action = QAction("&Full Screen", self, checkable=True)
        # Use Enter/Return keys to toggle fullscreen
        self.fullscreen_action.setShortcuts([
            QKeySequence(Qt.Key_Return),
            QKeySequence(Qt.Key_Enter),
        ])
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(self.fullscreen_action)

        # Global shortcuts for image navigation and zoom control
        self._shortcut_next = QShortcut(QKeySequence(Qt.Key_Right), self)
        self._shortcut_next.activated.connect(self.next_image)
        self._shortcut_prev = QShortcut(QKeySequence(Qt.Key_Left), self)
        self._shortcut_prev.activated.connect(self.prev_image)

        self._shortcut_first = QShortcut(QKeySequence(Qt.Key_Home), self)
        self._shortcut_first.activated.connect(self.first_image)
        self._shortcut_last = QShortcut(QKeySequence(Qt.Key_End), self)
        self._shortcut_last.activated.connect(self.last_image)

        self._shortcut_zoom_in = QShortcut(QKeySequence(Qt.Key_Up), self)
        self._shortcut_zoom_in.activated.connect(lambda: self.zoom_by(1.25))
        self._shortcut_zoom_out = QShortcut(QKeySequence(Qt.Key_Down), self)
        self._shortcut_zoom_out.activated.connect(lambda: self.zoom_by(0.8))

        self._shortcut_snap = QShortcut(QKeySequence(Qt.Key_Space), self)
        self._shortcut_snap.activated.connect(self.snap_to_global_view)

        # Fullscreen shortcuts
        self._shortcut_escape = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._shortcut_escape.activated.connect(self.exit_fullscreen)

    def _create_statusbar(self):
        status = QStatusBar(self)
        self.setStatusBar(status)
        self._status_text = ""
        self._update_status()

    def _update_status(self, extra: str = ""):
        if self.current_index == -1 or not self.image_files:
            text = "Ready — Ctrl+O to open folder"
        else:
            fname = os.path.basename(self.image_files[self.current_index])
            idx = self.current_index + 1
            total = len(self.image_files)
            text = f"{fname}  ({idx}/{total})"
        if extra:
            text = f"{text} — {extra}"
        self.statusBar().showMessage(text)

    def _load_last_parent_dir(self):
        try:
            if os.path.exists(self._settings_path):
                with open(self._settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    val = data.get("last_parent_dir")
                    if isinstance(val, str) and os.path.isdir(val):
                        return val
                    # Load press zoom multiplier if present
                    mul = data.get("press_zoom_multiplier")
                    try:
                        if mul is not None:
                            self.canvas._press_zoom_multiplier = float(mul)
                    except Exception:
                        pass
        except Exception:
            pass
        # Fallback directory when unset or invalid
        try:
            return os.path.expanduser("~")
        except Exception:
            return os.getcwd()

    def _save_last_parent_dir(self, parent_dir: str):
        try:
            data = {}
            if os.path.exists(self._settings_path):
                try:
                    with open(self._settings_path, "r", encoding="utf-8") as f:
                        data = json.load(f) or {}
                except Exception:
                    data = {}
            data["last_parent_dir"] = parent_dir
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            # Best-effort; ignore persistence issues
            pass

    def _save_settings_key(self, key: str, value):
        try:
            data = {}
            if os.path.exists(self._settings_path):
                try:
                    with open(self._settings_path, "r", encoding="utf-8") as f:
                        data = json.load(f) or {}
                except Exception:
                    data = {}
            data[key] = value
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def open_folder(self):
        start_dir = self._load_last_parent_dir()
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder", start_dir)
        if folder_path:
            # Save parent so next time the dialog shows where this folder lives
            parent_dir = os.path.dirname(folder_path)
            if parent_dir and os.path.isdir(parent_dir):
                self._save_last_parent_dir(parent_dir)
            self.image_files = sorted([
                os.path.join(folder_path, f)
                for f in os.listdir(folder_path)
                if f.lower().endswith(self.supported_formats)
            ])

            if self.image_files:
                self.current_index = 0
                self.pixmap_cache.clear() # Clear cache for new folder
                self.display_image()
                # Initial warmup: current + next 5 (total 6)
                self.maintain_decode_window(back=0, ahead=5)
                self.fit_action.setChecked(True)
                self.canvas._fit_to_window = True
            else:
                self.current_index = -1
                self.image_files = []
                self._update_status("No images found in the selected folder")

    def display_image(self):
        """Requests to display the current image."""
        if self.current_index == -1:
            return

        image_path = self.image_files[self.current_index]
        self.setWindowTitle(f"Image Viewer - {os.path.basename(image_path)}")

        if image_path in self.pixmap_cache:
            # LRU: move to end as most recently used
            pix = self.pixmap_cache.pop(image_path)
            self.pixmap_cache[image_path] = pix
            self.update_pixmap(pix)
        else:
            self._update_status("Loading…")
            self.loader.request_load(image_path)

    def on_image_ready(self, path, image_data, error):
        """Slot to handle the decoded image data from the loader."""
        if error:
            print(f"Error decoding {path}: {error}")
            # Optionally show error on the label if it's the current image
            if path == self.image_files[self.current_index]:
                self.label.setText(f"Error: {error}")
            return

        # Convert numpy array to QPixmap
        height, width, channel = image_data.shape
        bytes_per_line = 3 * width
        q_image = QImage(image_data.data, width, height, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)

        # Cache the pixmap
        # LRU cache: ensure recency order
        if path in self.pixmap_cache:
            self.pixmap_cache.pop(path)
        self.pixmap_cache[path] = pixmap
        if len(self.pixmap_cache) > self.cache_size:
            # Evict least-recently-used
            oldest_key, _ = self.pixmap_cache.popitem(last=False)

        # Display if it's the current image
        if path == self.image_files[self.current_index]:
            self.update_pixmap(pixmap)

    def update_pixmap(self, pixmap):
        if pixmap and not pixmap.isNull():
            self.canvas.set_pixmap(pixmap)
            info = f"{pixmap.width()}x{pixmap.height()}"
            self._update_status(info)
        else:
            self._update_status("Failed to load image")

    def keyPressEvent(self, event):
        if not self.image_files:
            return

        key = event.key()
        if key == Qt.Key_Right:
            self.next_image()
        elif key == Qt.Key_Left:
            self.prev_image()
        else:
            super().keyPressEvent(event)

    def maintain_decode_window(self, back: int = 3, ahead: int = 5):
        """Ensure a sliding window around the current image is decoded/scheduled.

        Keeps [current-back, current+ahead] images warm in cache/pending.
        """
        if not self.image_files:
            return
        n = len(self.image_files)
        i = self.current_index
        start = max(0, i - back)
        end = min(n - 1, i + ahead)
        # Schedule current first (display_image already schedules if missing)
        # Then schedule the rest in increasing distance order could be added later.
        for idx in range(start, end + 1):
            path = self.image_files[idx]
            if path not in self.pixmap_cache:
                self.loader.request_load(path)

    # Navigation helpers
    def next_image(self):
        if not self.image_files:
            return
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self.display_image()
        self.maintain_decode_window()

    def prev_image(self):
        if not self.image_files:
            return
        self.current_index = (self.current_index - 1) % len(self.image_files)
        self.display_image()
        self.maintain_decode_window()

    def first_image(self):
        if not self.image_files:
            return
        self.current_index = 0
        self.display_image()
        self.maintain_decode_window()

    def last_image(self):
        if not self.image_files:
            return
        self.current_index = len(self.image_files) - 1
        self.display_image()
        self.maintain_decode_window()

    def closeEvent(self, event):
        self.loader.shutdown()
        event.accept()

    # View commands
    def toggle_fit(self):
        # Backward-compat: treat as selecting Fit explicitly
        self.choose_fit()

    def zoom_by(self, factor: float):
        self.canvas.zoom_by(factor)

    def reset_zoom(self):
        self.canvas.reset_zoom()

    # View mode selection and snapping
    def choose_fit(self):
        self.canvas._fit_to_window = True
        self.fit_action.setChecked(True)
        if hasattr(self, 'actual_action'):
            self.actual_action.setChecked(False)
        self.canvas.apply_current_view()

    def choose_actual(self):
        self.canvas._fit_to_window = False
        self.canvas._zoom = 1.0
        if hasattr(self, 'fit_action'):
            self.fit_action.setChecked(False)
        if hasattr(self, 'actual_action'):
            self.actual_action.setChecked(True)
        self.canvas.apply_current_view()

    def toggle_hq_downscale(self):
        enabled = self.hq_downscale_action.isChecked()
        self.canvas._hq_downscale = enabled
        # Invalidate cache and reapply if in fit
        self.canvas._hq_pixmap = None
        if self.canvas.is_fit():
            self.canvas.apply_current_view()

    def snap_to_global_view(self):
        if hasattr(self, 'fit_action') and self.fit_action.isChecked():
            self.choose_fit()
        else:
            self.choose_actual()

    # Settings: press zoom multiplier
    def set_press_zoom_multiplier(self, value: float):
        try:
            v = float(value)
        except Exception:
            return
        v = max(0.1, min(v, 10.0))
        self.canvas._press_zoom_multiplier = v
        # persist
        self._save_settings_key("press_zoom_multiplier", v)
        # no preset checks; only custom entry

    def prompt_custom_multiplier(self):
        try:
            from PySide6.QtWidgets import QInputDialog
        except Exception:
            return
        current = getattr(self.canvas, "_press_zoom_multiplier", 2.0)
        # Use positional arguments for wide compatibility; decimals=1
        val, ok = QInputDialog.getDouble(
            self,
            "Press Zoom Multiplier",
            "Enter multiplier (1.0-10.0):",
            float(current),
            0.1,
            10.0,
            1,
        )
        if ok:
            self.set_press_zoom_multiplier(val)

    # Fullscreen control
    def enter_fullscreen(self):
        if self.isFullScreen():
            return
        # Save previous state/geometry to restore cleanly without flicker
        self._prev_state = self.windowState()
        try:
            self._prev_geometry = self.saveGeometry()
        except Exception:
            self._prev_geometry = None
        # Hide menu and status bars for immersive viewing
        self.menuBar().setVisible(False)
        if self.statusBar():
            self.statusBar().setVisible(False)
        # Enter fullscreen by setting the window state flag (avoids intermediate resize)
        self.setWindowState(self._prev_state | Qt.WindowFullScreen)
        if hasattr(self, 'fullscreen_action'):
            self.fullscreen_action.setChecked(True)
        # Re-apply view after size change
        self.canvas.apply_current_view()

    def exit_fullscreen(self):
        if not self.isFullScreen():
            return
        # Restore previous state atomically to avoid visible intermediate size
        self.setUpdatesEnabled(False)
        prev = getattr(self, "_prev_state", Qt.WindowMaximized)
        self.setWindowState(prev & ~Qt.WindowFullScreen)
        geom = getattr(self, "_prev_geometry", None)
        if geom and not (prev & Qt.WindowMaximized):
            try:
                self.restoreGeometry(geom)
            except Exception:
                pass
        # Restore UI chrome
        self.menuBar().setVisible(True)
        if self.statusBar():
            self.statusBar().setVisible(True)
        if hasattr(self, 'fullscreen_action'):
            self.fullscreen_action.setChecked(False)
        self.setUpdatesEnabled(True)
        self.canvas.apply_current_view()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()

if __name__ == "__main__":
    # This is important for multiprocessing on some platforms (e.g., Windows)
    from multiprocessing import freeze_support
    freeze_support()

    app = QApplication(sys.argv)
    viewer = ImageViewer()
    viewer.showMaximized()
    sys.exit(app.exec())
