"""Trim workflow operations."""

import contextlib
import traceback as _tb

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMessageBox

from .logger import get_logger
from .trim import apply_trim_to_file, detect_trim_box_stats, make_trim_preview
from .ui_trim import TrimBatchWorker, TrimProgressDialog

_logger = get_logger("trim_operations")


def start_trim_workflow(viewer) -> None:
    """Start the trim workflow.
    
    Handles two modes:
    1. Batch save as copies: parallel processing with progress dialog
    2. Overwrite existing: file-by-file confirmation with preview
    
    Args:
        viewer: The ImageViewer instance
    """
    # 재진입/중복 실행 방지
    if viewer.trim_state.is_running:
        _logger.debug("trim workflow already running")
        return
    viewer.trim_state.is_running = True
    try:
        if not viewer.image_files:
            return

        # 0) 트림 민감도 프로파일 선택 (기본/공격적)
        prof_box = QMessageBox(viewer)
        prof_box.setWindowTitle("트림 민감도")
        prof_box.setText("어떤 프로파일로 트림할까요?")
        btn_norm = prof_box.addButton("기본", QMessageBox.ButtonRole.AcceptRole)
        btn_agg = prof_box.addButton("공격적", QMessageBox.ButtonRole.ActionRole)
        btn_cancel = prof_box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        prof_box.setDefaultButton(btn_norm)
        prof_box.exec()
        clicked_prof = prof_box.clickedButton()
        if clicked_prof is btn_cancel or clicked_prof is None:
            return
        profile = "aggressive" if clicked_prof is btn_agg else "normal"

        # 1) 저장 모드 선택 (덮어씌우기/사본/취소)
        mode_box = QMessageBox(viewer)
        mode_box.setWindowTitle("트림")
        mode_box.setText(
            "Stats 방식으로 트림하겠습니다.\n(덮어씌우기, 따로 저장, 취소)"
        )
        overwrite_btn = mode_box.addButton(
            "덮어씌우기", QMessageBox.ButtonRole.AcceptRole
        )
        saveas_btn = mode_box.addButton(
            "사본 저장(_trimmed)", QMessageBox.ButtonRole.ActionRole
        )
        cancel_btn = mode_box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        mode_box.setDefaultButton(overwrite_btn)
        mode_box.exec()
        clicked = mode_box.clickedButton()
        if clicked is cancel_btn or clicked is None:
            return
        overwrite = clicked is overwrite_btn

        if not overwrite:
            # 사본 저장: 백그라운드 스레드 일괄 처리 + 진행 대화상자
            paths = list(viewer.image_files)
            dlg = TrimProgressDialog(viewer)

            # 동기 처리
            worker = TrimBatchWorker(paths, profile)

            def _on_progress(total: int, index: int, name: str):
                dlg.on_progress(total, index, name)

            worker.progress.connect(_on_progress)
            worker.finished.connect(dlg.accept)
            worker.run()
            dlg.exec()
            viewer.maintain_decode_window()
            return

        # 덮어씌우기: 파일별 승인(미리보기 + Y/N/A 단축키)
        stop_all = False
        for path in list(viewer.image_files):
            if stop_all:
                break
            try:
                crop = detect_trim_box_stats(path, profile=profile)
            except Exception:
                crop = None
            if not crop:
                continue
            preview = make_trim_preview(path, crop)
            if preview is None:
                continue
            prev_pix = (
                viewer.canvas._pix_item.pixmap() if viewer.canvas._pix_item else None
            )
            try:
                viewer.trim_state.in_preview = True
                viewer.canvas.set_pixmap(preview)
                viewer.canvas._preset_mode = "fit"
                viewer.canvas.apply_current_view()
            except Exception as e:
                _logger.error("trim preview display error: %s", e)

            box = QMessageBox(viewer)
            box.setWindowTitle("Trim")
            box.setText("트림할까요? (Y/N)")
            yes = box.addButton("Accept (Y)", QMessageBox.ButtonRole.YesRole)
            no = box.addButton("Reject (N)", QMessageBox.ButtonRole.NoRole)
            abort_btn = box.addButton(
                "Abort (A)", QMessageBox.ButtonRole.RejectRole
            )
            # Y/N/A 단축키 동작 추가: 단축키로 버튼 클릭을 트리거
            try:
                sc_y = QShortcut(QKeySequence("Y"), box)
                sc_n = QShortcut(QKeySequence("N"), box)
                sc_a = QShortcut(QKeySequence("A"), box)
                sc_y.activated.connect(lambda: yes.click())
                sc_n.activated.connect(lambda: no.click())
                sc_a.activated.connect(lambda: abort_btn.click())
            except Exception:
                pass
            box.setDefaultButton(yes)
            box.exec()
            clicked_btn = box.clickedButton()
            if clicked_btn is abort_btn:
                stop_all = True
                accepted = False
            else:
                accepted = clicked_btn is yes

            # 원래 뷰 복귀
            try:
                if prev_pix and not prev_pix.isNull():
                    viewer.canvas.set_pixmap(prev_pix)
                    viewer.canvas.apply_current_view()
                else:
                    viewer.display_image()
            except Exception as e:
                _logger.error("trim preview restore error: %s", e)
                viewer.display_image()
            finally:
                viewer.trim_state.in_preview = False

            if not accepted:
                continue

            # 로그: 덮어쓰기 직전 상태 출력
            _logger.debug("[trim] overwrite prep: %s", path)
            displaying = False
            cached = False

            with contextlib.suppress(Exception):
                displaying = (
                    viewer.current_index >= 0
                    and viewer.current_index < len(viewer.image_files)
                    and viewer.image_files[viewer.current_index] == path
                )

            with contextlib.suppress(Exception):
                cached = path in viewer.pixmap_cache

            _logger.debug(
                "[trim] overwrite start: %s, displaying=%s, cached=%s",
                path,
                displaying,
                cached,
            )

            try:
                apply_trim_to_file(path, crop, overwrite=True)
                _logger.debug("[trim] overwrite ok: %s", path)
            except Exception:
                _logger.debug(
                    "[trim] overwrite error: %s\n%s", path, _tb.format_exc()
                )
                QMessageBox.critical(
                    viewer,
                    "Trim 오류",
                    f"파일 저장 실패: {path}",
                )
                continue

            # 캐시 무효화 및 필요시 재표시
            with contextlib.suppress(Exception):
                viewer.pixmap_cache.pop(path, None)
            if (
                viewer.current_index >= 0
                and viewer.current_index < len(viewer.image_files)
                and viewer.image_files[viewer.current_index] == path
            ):
                viewer.display_image()

        viewer.maintain_decode_window()
    finally:
        # 실행 플래그 해제
        viewer.trim_state.is_running = False
        _logger.debug("trim workflow finished")
