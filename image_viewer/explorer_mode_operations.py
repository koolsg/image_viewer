"""Explorer mode operations: folder/image selection, UI setup."""

import contextlib
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStackedWidget

from .logger import get_logger
from .ui_canvas import ImageCanvas

_logger = get_logger("explorer_mode")


def toggle_view_mode(viewer) -> None:
    """Toggle between View Mode and Explorer Mode.
    
    Args:
        viewer: The ImageViewer instance
    """
    viewer.explorer_state.view_mode = not viewer.explorer_state.view_mode
    _update_ui_for_mode(viewer)
    _logger.debug("view_mode toggled: %s", viewer.explorer_state.view_mode)


def _update_ui_for_mode(viewer) -> None:
    """Rebuild UI based on current mode.
    
    Args:
        viewer: The ImageViewer instance
    """
    if viewer.explorer_state.view_mode:
        _setup_view_mode(viewer)
    else:
        _setup_explorer_mode(viewer)

    # 메뉴 동기화
    if hasattr(viewer, "explorer_mode_action"):
        viewer.explorer_mode_action.setChecked(not viewer.explorer_state.view_mode)


def _setup_view_mode(viewer) -> None:
    """Setup View Mode: show only canvas.
    
    Args:
        viewer: The ImageViewer instance
    """
    try:
        # Explorer Grid 로더 연결 해제(점프 후 UI 부하 차단)
        try:
            grid = getattr(viewer.explorer_state, "_explorer_grid", None)
            if grid is not None:
                grid.set_loader(None)
        except Exception:
            pass

        current_widget = viewer.centralWidget()

        # Check if we're using the stacked widget architecture
        if isinstance(current_widget, QStackedWidget):
            # Good: stacked widget exists, just switch to canvas page (Index 0)
            try:
                current_widget.setCurrentIndex(0)
                _logger.debug("switched to View Mode via stacked widget")
            except Exception as e:
                _logger.warning("failed to switch stacked widget page: %s", e)
        else:
            # Fallback: manually set canvas as central widget
            try:
                # Verify canvas is valid
                if viewer.canvas:
                    viewer.canvas.parent()  # This will raise if C++ object deleted

                    # Set canvas as central widget
                    viewer.setCentralWidget(viewer.canvas)
                    viewer.canvas.show()
                    _logger.debug("switched to View Mode with existing canvas")
            except RuntimeError as e:
                # Canvas C++ object is deleted
                _logger.warning("canvas C++ object is invalid: %s", e)
                try:
                    viewer.canvas = ImageCanvas(viewer)
                    viewer.setCentralWidget(viewer.canvas)
                    _logger.warning("canvas recreated and set as central widget")
                except Exception as e2:
                    _logger.error("failed to recreate canvas: %s", e2)
            except Exception as e:
                _logger.warning("failed to set canvas as central widget: %s", e)
                try:
                    viewer.canvas = ImageCanvas(viewer)
                    viewer.setCentralWidget(viewer.canvas)
                    _logger.warning("canvas recreated and set as central widget")
                except Exception as e2:
                    _logger.error("failed to recreate canvas: %s", e2)

    except Exception as e:
        _logger.error("failed to setup view mode: %s", e)


def _setup_explorer_mode(viewer) -> None:
    """Setup Explorer Mode: tree + grid layout.
    
    Args:
        viewer: The ImageViewer instance
    """
    try:
        from image_viewer.ui_explorer_grid import ThumbnailGridWidget
        from image_viewer.ui_explorer_tree import FolderTreeWidget

        current_widget = viewer.centralWidget()
        stacked_widget = None

        if isinstance(current_widget, QStackedWidget):
            stacked_widget = current_widget
            _logger.debug("reusing existing stacked widget")
        else:
            stacked_widget = QStackedWidget()
            if isinstance(current_widget, ImageCanvas):
                viewer.takeCentralWidget()
                stacked_widget.addWidget(current_widget)
            elif viewer.canvas:
                stacked_widget.addWidget(viewer.canvas)
            viewer.setCentralWidget(stacked_widget)
            _logger.debug("created stacked widget for mode switching")

        # 이미 Page 1이 있으면 그대로 재사용(그리드/트리/썸네일 캐시 보존)
        if stacked_widget.count() > 1:
            try:
                stacked_widget.widget(1)
                # 기존 grid 참조가 있으면 로더만 재연결
                grid = getattr(viewer.explorer_state, "_explorer_grid", None)
                if grid is not None:
                    with contextlib.suppress(Exception):
                        grid.set_loader(viewer.thumb_loader)
            except Exception:
                pass
            stacked_widget.setCurrentIndex(1)
            _logger.debug("switched to existing Explorer page")
            return

        # 최초 생성 경로
        from PySide6.QtWidgets import QSplitter

        splitter = QSplitter(Qt.Orientation.Horizontal)
        tree = FolderTreeWidget()
        grid = ThumbnailGridWidget()

        try:
            grid.set_loader(viewer.thumb_loader)
        except Exception as ex:
            _logger.debug("failed to attach thumb_loader: %s", ex)

        # 설정 적용
        try:
            if any(
                viewer._settings_manager.has(key)
                for key in ("thumbnail_width", "thumbnail_height", "thumbnail_size")
            ):
                use_size_only = (
                    viewer._settings_manager.has("thumbnail_size")
                    and not viewer._settings_manager.has("thumbnail_width")
                    and not viewer._settings_manager.has("thumbnail_height")
                )
                size = int(viewer._settings_manager.get("thumbnail_size"))
                width = (
                    size
                    if use_size_only
                    else int(viewer._settings_manager.get("thumbnail_width"))
                )
                height = (
                    size
                    if use_size_only
                    else int(viewer._settings_manager.get("thumbnail_height"))
                )
                if hasattr(grid, "set_thumbnail_size_wh"):
                    grid.set_thumbnail_size_wh(width, height)
                elif hasattr(grid, "set_thumbnail_size"):
                    grid.set_thumbnail_size(int(width))
            if viewer._settings_manager.has("thumbnail_hspacing"):
                grid.set_horizontal_spacing(
                    int(viewer._settings_manager.get("thumbnail_hspacing"))
                )
        except Exception as e:
            _logger.debug("failed to apply grid settings: %s", e)

        splitter.addWidget(tree)
        splitter.addWidget(grid)
        splitter.setSizes([300, 700])

        # 신호 연결
        tree.folder_selected.connect(
            lambda p: _on_explorer_folder_selected(viewer, p, grid)
        )
        grid.image_selected.connect(lambda p: _on_explorer_image_selected(viewer, p))

        # Page 1 추가 및 전환
        stacked_widget.addWidget(splitter)
        stacked_widget.setCurrentIndex(1)

        viewer.explorer_state._explorer_tree = tree
        viewer.explorer_state._explorer_grid = grid

        # 현재 폴더 자동 로드
        if viewer.image_files:
            current_dir = str(Path(viewer.image_files[0]).parent)
            tree.set_root_path(current_dir)
            grid.load_folder(current_dir)

        _logger.debug("switched to Explorer Mode")
    except Exception as e:
        _logger.error("failed to setup explorer mode: %s", e)


def _on_explorer_folder_selected(viewer, folder_path: str, grid) -> None:
    """Handle folder selection in explorer.
    
    Args:
        viewer: The ImageViewer instance
        folder_path: Selected folder path
        grid: The thumbnail grid widget
    """
    try:
        grid.load_folder(folder_path)
        _logger.debug("explorer folder selected: %s", folder_path)
    except Exception as e:
        _logger.error(
            "failed to load folder in explorer: %s, error=%s", folder_path, e
        )


def _on_explorer_image_selected(viewer, image_path: str) -> None:
    """Handle image selection in explorer.
    
    Args:
        viewer: The ImageViewer instance
        image_path: Selected image path
    """
    try:
        # View Mode로 전환하고 해당 이미지 표시
        if not viewer.explorer_state.view_mode:
            viewer.explorer_state.view_mode = True
            _update_ui_for_mode(viewer)

        # 포커스 보장: 화살표/단축키 즉시 동작
        try:
            viewer.setFocus(Qt.FocusReason.OtherFocusReason)
            if hasattr(viewer, "canvas") and viewer.canvas is not None:
                viewer.canvas.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass

        # jump 거리 계산(디버깅용)
        try:
            cur_idx = viewer.current_index
            tgt_idx = (
                viewer.image_files.index(image_path)
                if image_path in viewer.image_files
                else None
            )
            _logger.debug(
                "explorer select: cur=%s tgt=%s path=%s",
                cur_idx,
                tgt_idx,
                image_path,
            )
        except Exception:
            pass

        # image_path로 이미지 표시
        if image_path in viewer.image_files:
            viewer.current_index = viewer.image_files.index(image_path)
        else:
            # 새 폴더인 경우 먼저 폴더를 열기
            new_folder = str(Path(image_path).parent)
            _logger.debug("explorer select: open_folder_at %s", new_folder)
            open_folder_at(viewer, new_folder)
            if image_path in viewer.image_files:
                viewer.current_index = viewer.image_files.index(image_path)

        _logger.debug(
            "explorer select display: idx=%s path=%s",
            viewer.current_index,
            image_path,
        )
        viewer.display_image()
        # 전환 직후 과도한 프리페치 방지
        viewer.maintain_decode_window(back=0, ahead=1)
        _logger.debug("explorer image selected done: %s", image_path)
    except Exception as e:
        _logger.error(
            "failed to select image in explorer: %s, error=%s", image_path, e
        )


def open_folder_at(viewer, folder_path: str) -> None:
    """Open a specific folder directly.
    
    Args:
        viewer: The ImageViewer instance
        folder_path: Path to the folder to open
    """
    try:
        if not os.path.isdir(folder_path):
            _logger.warning("not a directory: %s", folder_path)
            return

        # 세션 상태 정리: Viewer/Thumbnail 로더 모두 대기/무시 목록 초기화
        try:
            if hasattr(viewer, "loader"):
                viewer.loader._ignored.clear()
                viewer.loader._pending.clear()
                if hasattr(viewer.loader, "_latest_id"):
                    viewer.loader._latest_id.clear()
        except Exception:
            pass
        try:
            if hasattr(viewer, "thumb_loader") and viewer.thumb_loader is not None:
                viewer.thumb_loader._ignored.clear()
                viewer.thumb_loader._pending.clear()
                if hasattr(viewer.thumb_loader, "_latest_id"):
                    viewer.thumb_loader._latest_id.clear()
        except Exception:
            pass

        viewer.pixmap_cache.clear()
        viewer.current_index = -1

        # 이미지 목록 재구성
        files = []
        for name in os.listdir(folder_path):
            p = os.path.join(folder_path, name)
            if os.path.isfile(p):
                lower = name.lower()
                if lower.endswith(
                    (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".bmp",
                        ".gif",
                        ".webp",
                        ".tif",
                        ".tiff",
                    )
                ):
                    files.append(p)
        files.sort()
        viewer.image_files = files

        if not viewer.image_files:
            viewer.setWindowTitle("Image Viewer")
            viewer._update_status("No images found.")
            return

        viewer.current_index = 0
        viewer._save_last_parent_dir(folder_path)
        viewer.setWindowTitle(
            f"Image Viewer - {os.path.basename(viewer.image_files[viewer.current_index])}"
        )
        # 초기 프리패치도 경량화
        viewer.maintain_decode_window(back=0, ahead=3)

        _logger.debug(
            "folder opened: %s, images=%d", folder_path, len(viewer.image_files)
        )
    except Exception as e:
        _logger.error("failed to open_folder_at: %s, error=%s", folder_path, e)
