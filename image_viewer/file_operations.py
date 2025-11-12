"""File operation handlers: delete, trim, etc."""
import gc
import os
import time as _time
import traceback as _tb

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox
from send2trash import send2trash

from .logger import get_logger

_logger = get_logger("file_operations")


def delete_current_file(viewer) -> None:
    """Delete the current file and move to trash.

    Args:
        viewer: The ImageViewer instance
    """
    # 현재 파일을 휴지통으로 이동(확인 대화상자 표시).
    # UX: 삭제 확정 후 먼저 다른 이미지로 전환하고, 그 다음 실제 삭제를 시도한다.
    if (
        not viewer.image_files
        or viewer.current_index < 0
        or viewer.current_index >= len(viewer.image_files)
    ):
        _logger.debug("[delete] abort: no images or invalid index")
        return
    del_path = viewer.image_files[viewer.current_index]
    abs_path = os.path.abspath(del_path)
    _logger.debug(
        "[delete] start: idx=%s, del_path=%s, abs_path=%s, total=%s",
        viewer.current_index,
        del_path,
        abs_path,
        len(viewer.image_files),
    )

    # 확인 다이얼로그
    proceed = True
    base = os.path.basename(del_path)
    ret = QMessageBox.question(
        viewer,
        "휴지통으로 이동",
        f"이 파일을 휴지통으로 이동하시겠습니까?\n{base}",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    proceed = ret == QMessageBox.StandardButton.Yes
    _logger.debug("[delete] confirm: proceed=%s", proceed)
    if not proceed:
        _logger.debug("[delete] user cancelled")
        return

    # 1) 다른 이미지로 전환하여 표시 기준을 바꾼다
    if len(viewer.image_files) > 1:
        if viewer.current_index < len(viewer.image_files) - 1:
            new_index = viewer.current_index + 1
        else:
            new_index = viewer.current_index - 1
        _logger.debug(
            "[delete] switch image: %s -> %s", viewer.current_index, new_index
        )
        viewer.current_index = new_index
        try:
            viewer.display_image()
            viewer.maintain_decode_window()
        except Exception as ex:
            _logger.debug("[delete] switch image error: %s", ex)
    else:
        _logger.debug("[delete] single image case: will clear view later")

    # 화면/캐시에서 해당 경로 제거 + 이벤트/GC로 안정화
    try:
        removed = viewer.pixmap_cache.pop(del_path, None) is not None
        _logger.debug("[delete] cache pop: removed=%s", removed)
    except Exception as ex:
        _logger.debug("[delete] cache pop error: %s", ex)
    try:
        QApplication.processEvents()
        _logger.debug("[delete] processEvents done")
        gc.collect()
        _logger.debug("[delete] gc.collect done")
        _time.sleep(0.15)
        _logger.debug("[delete] settle sleep done")
    except Exception as ex:
        _logger.debug("[delete] settle phase error: %s", ex)

    # 2) 실제 휴지통 이동(재시도 포함)
    try:
        try:
            last_err = None
            for attempt in range(1, 4):
                try:
                    _logger.debug("[delete] trash attempt %s", attempt)
                    send2trash(abs_path)
                    last_err = None
                    _logger.debug("[delete] trash success")
                    break
                except Exception as ex:
                    last_err = ex
                    _logger.debug(
                        "[delete] trash failed attempt %s: %s", attempt, ex
                    )
                    _time.sleep(0.2)
            if last_err is not None:
                raise last_err
        except Exception:
            raise
    except Exception as e:
        _logger.debug("[delete] trash final error: %s", e)
        QMessageBox.critical(
            viewer,
            "이동 실패",
            (
                "휴지통으로 이동 중 오류가 발생했습니다.\n"
                "send2trash 설치 및 경로를 확인해 주세요.\n\n"
                f"오류: {e}\n"
                f"원본경로: {del_path}\n"
                f"절대경로: {abs_path}\n"
            ),
        )
        return

    # 삭제 성공 확인 후에만, 재요청/완료 신호를 확실히 무시하도록 ignore 적용
    try:
        if hasattr(viewer, "loader"):
            viewer.loader.ignore_path(del_path)
    except Exception:
        pass

    # 3) 목록에서 제거하고 인덱스 정리
    try:
        try:
            del_pos = viewer.image_files.index(del_path)
        except ValueError:
            del_pos = None
        _logger.debug("[delete] remove list: pos=%s", del_pos)
        if del_pos is not None:
            viewer.image_files.pop(del_pos)
            if del_pos <= viewer.current_index:
                old_idx = viewer.current_index
                viewer.current_index = max(0, viewer.current_index - 1)
                _logger.debug(
                    "[delete] index adjust: %s -> %s", old_idx, viewer.current_index
                )
    except Exception as ex:
        _logger.debug("[delete] list pop error, fallback remove: %s", ex)
        try:
            viewer.image_files.remove(del_path)
            _logger.debug("[delete] list remove by value: success")
        except Exception as ex2:
            _logger.debug("[delete] list remove by value error: %s", ex2)

    # 4) 최종 표시/상태 갱신
    if not viewer.image_files:
        _logger.debug("[delete] list empty: clearing view")
        viewer.current_index = -1
        try:
            from PySide6.QtCore import Qt

            empty = QPixmap(1, 1)
            empty.fill(Qt.GlobalColor.transparent)
            viewer.canvas.set_pixmap(empty)
        except Exception as ex:
            _logger.debug("[delete] clear view error: %s", ex)
        viewer.setWindowTitle("Image Viewer")
        viewer._update_status()
        return
    try:
        _logger.debug(
            "[delete] show current: idx=%s, total=%s",
            viewer.current_index,
            len(viewer.image_files),
        )
        viewer.display_image()
        viewer.maintain_decode_window()
    except Exception as ex:
        _logger.debug("[delete] final display error: %s", ex)
