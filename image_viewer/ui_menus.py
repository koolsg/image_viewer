from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QColor, QShortcut


from typing import TYPE_CHECKING
from .logger import get_logger

if TYPE_CHECKING:
    from .main import ImageViewer

_logger = get_logger("ui_menus")

def build_menus(viewer: "ImageViewer") -> None:
    """viewer의 메뉴 바와 보기 메뉴를 구성한다.

    - 한국어 라벨 유지
    - 썸네일 모드에 따라 고품질 축소 토글 활성/비활성
    - viewer가 기대하는 action 속성들을 세팅
    """
    menu_bar = viewer.menuBar()

    # 파일 메뉴
    file_menu = menu_bar.addMenu("파일(&F)")
    open_action = QAction("폴더 열기...(&O)", viewer)
    open_action.setShortcut(QKeySequence("Ctrl+O"))
    open_action.triggered.connect(viewer.open_folder)
    file_menu.addAction(open_action)

    exit_action = QAction("종료(&X)", viewer)
    exit_action.setShortcut(QKeySequence("Alt+F4"))
    exit_action.triggered.connect(viewer.close)
    file_menu.addAction(exit_action)

    # 보기 메뉴
    view_menu = menu_bar.addMenu("보기(&V)")
    viewer.view_group = QActionGroup(viewer)
    viewer.view_group.setExclusive(True)

    viewer.fit_action = QAction("맞춤 보기(&F)", viewer, checkable=True)
    viewer.fit_action.setShortcut("F")
    viewer.fit_action.setChecked(True)
    viewer.fit_action.triggered.connect(viewer.choose_fit)
    viewer.view_group.addAction(viewer.fit_action)
    view_menu.addAction(viewer.fit_action)

    viewer.actual_action = QAction("실제 크기(&A)", viewer, checkable=True)
    viewer.actual_action.setShortcut("1")
    viewer.actual_action.setChecked(False)
    viewer.actual_action.triggered.connect(viewer.choose_actual)
    viewer.view_group.addAction(viewer.actual_action)
    view_menu.addAction(viewer.actual_action)

    viewer.hq_downscale_action = QAction("고품질 축소(맞춤 전용)(&Q)", viewer, checkable=True)
    viewer.hq_downscale_action.setChecked(False)
    viewer.hq_downscale_action.triggered.connect(viewer.toggle_hq_downscale)
    view_menu.addAction(viewer.hq_downscale_action)

    # 디코딩 전략 토글: 썸네일 모드(fast viewing)
    from .strategy import ThumbnailStrategy
    is_thumbnail = isinstance(getattr(viewer, 'decoding_strategy', None), ThumbnailStrategy)
    viewer.thumbnail_mode_action = QAction("썸네일 모드(fast viewing)", viewer, checkable=True)
    viewer.thumbnail_mode_action.setChecked(is_thumbnail)
    viewer.thumbnail_mode_action.triggered.connect(viewer.toggle_thumbnail_mode)
    view_menu.addAction(viewer.thumbnail_mode_action)

    # 전략에 따라 고품질 축소 옵션 활성화/비활성화
    strategy = getattr(viewer, 'decoding_strategy', None)
    if strategy:
        viewer.hq_downscale_action.setEnabled(strategy.supports_hq_downscale())

    # 배율 곱 설정
    viewer.multiplier_action = QAction("배율 곱 설정...", viewer)
    viewer.multiplier_action.triggered.connect(viewer.prompt_custom_multiplier)
    view_menu.addAction(viewer.multiplier_action)

    # 배경 메뉴
    bg_menu = view_menu.addMenu("배경")
    viewer.bg_black_action = QAction("검정", viewer, checkable=True)
    viewer.bg_white_action = QAction("흰색", viewer, checkable=True)
    viewer.bg_custom_action = QAction("기타...", viewer)
    bg_menu.addAction(viewer.bg_black_action)
    bg_menu.addAction(viewer.bg_white_action)
    bg_menu.addAction(viewer.bg_custom_action)
    viewer.bg_black_action.triggered.connect(lambda: viewer.set_background_qcolor(QColor(0, 0, 0)))
    viewer.bg_white_action.triggered.connect(lambda: viewer.set_background_qcolor(QColor(255, 255, 255)))
    viewer.bg_custom_action.triggered.connect(viewer.choose_background_custom)
    if hasattr(viewer, '_sync_bg_checks'):
        viewer._sync_bg_checks()

    # 확대/축소
    zoom_in_action = QAction("확대", viewer)
    zoom_in_action.setShortcut(QKeySequence.ZoomIn)
    zoom_in_action.triggered.connect(lambda: viewer.zoom_by(1.25))
    view_menu.addAction(zoom_in_action)

    zoom_out_action = QAction("축소", viewer)
    zoom_out_action.setShortcut(QKeySequence.ZoomOut)
    zoom_out_action.triggered.connect(lambda: viewer.zoom_by(0.75))
    view_menu.addAction(zoom_out_action)

    # 트림 기능
    try:
        viewer.trim_action = QAction("트림...", viewer)
        viewer.trim_action.triggered.connect(viewer.start_trim_workflow)
        view_menu.addAction(viewer.trim_action)
    except Exception as ex:
        # 메뉴 생성 실패는 실행을 막지 않음
        _logger.debug("trim menu unavailable: %s", ex)

    # 전체 화면
    viewer.fullscreen_action = QAction("전체 화면", viewer, checkable=True)
    viewer.fullscreen_action.setShortcuts([
        QKeySequence(Qt.Key_Return),
        QKeySequence(Qt.Key_Enter),
    ])
    viewer.fullscreen_action.triggered.connect(viewer.toggle_fullscreen)
    view_menu.addAction(viewer.fullscreen_action)

    # 전역 단축키
    try:
        viewer._shortcut_next = QShortcut(QKeySequence(Qt.Key_Right), viewer)
        viewer._shortcut_next.activated.connect(viewer.next_image)
        viewer._shortcut_prev = QShortcut(QKeySequence(Qt.Key_Left), viewer)
        viewer._shortcut_prev.activated.connect(viewer.prev_image)

        viewer._shortcut_first = QShortcut(QKeySequence(Qt.Key_Home), viewer)
        viewer._shortcut_first.activated.connect(viewer.first_image)
        viewer._shortcut_last = QShortcut(QKeySequence(Qt.Key_End), viewer)
        viewer._shortcut_last.activated.connect(viewer.last_image)

        viewer._shortcut_escape = QShortcut(QKeySequence(Qt.Key_Escape), viewer)
        viewer._shortcut_escape.activated.connect(viewer.exit_fullscreen)

        # 스페이스: 현재 글로벌 뷰 적용
        viewer._shortcut_space = QShortcut(QKeySequence(Qt.Key_Space), viewer)
        viewer._shortcut_space.activated.connect(viewer.snap_to_global_view)

        # 확대/축소 추가 단축키(옵션)
        viewer._shortcut_zoom_in = QShortcut(QKeySequence(Qt.Key_Up), viewer)
        viewer._shortcut_zoom_in.activated.connect(lambda: viewer.zoom_by(1.25))
        viewer._shortcut_zoom_out = QShortcut(QKeySequence(Qt.Key_Down), viewer)
        viewer._shortcut_zoom_out.activated.connect(lambda: viewer.zoom_by(0.75))
    except Exception as ex:
        _logger.debug("shortcuts unavailable: %s", ex)
