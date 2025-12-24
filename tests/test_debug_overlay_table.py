from PySide6.QtWidgets import QWidget

from image_viewer.crop.ui_crop_debug_overlay import DebugOverlay


def test_debug_overlay_table_shows_keys_and_values(qtbot):
    parent = QWidget()
    overlay = DebugOverlay(parent)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitForWindowShown(parent)

    overlay.show_message({"mouse": "10,20", "hit": "MOVE", "cursor": "OpenHandCursor"})

    # Give the overlay time to apply pending timers
    qtbot.wait(60)
    assert overlay.isVisible()
    # Ensure left column labels present
    assert overlay._key_labels["mouse"].text() == "mouse"
    assert overlay._key_labels["hit"].text() == "hit"
    assert overlay._key_labels["cursor"].text() == "cursor"
    # And values displayed
    assert overlay._value_labels["mouse"].text() == "10,20"
    assert overlay._value_labels["hit"].text() == "MOVE"
    assert overlay._value_labels["cursor"].text() == "OpenHandCursor"


def test_debug_overlay_hides_when_all_empty(qtbot):
    parent = QWidget()
    overlay = DebugOverlay(parent)
    qtbot.addWidget(parent)

    overlay.show_message({"mouse": "", "hit": ""})
    assert not overlay.isVisible()


def test_debug_overlay_parses_compound_string(qtbot):
    parent = QWidget()
    overlay = DebugOverlay(parent)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitForWindowShown(parent)

    line1 = "hover: hit=TOP_LEFT"
    line2 = "cursor=OpenHandCursor handler=h0 (x=10 y=20)"
    overlay.show_message(line1 + "\n" + line2)

    # Give the overlay time to apply pending timers
    qtbot.wait(60)
    assert overlay.isVisible()
    assert overlay._value_labels["hit"].text() == "TOP_LEFT"
    assert overlay._value_labels["handler"].text() == "h0"
    assert overlay._value_labels["cursor"].text() == "OpenHandCursor"


def test_debug_overlay_persists_visible_when_requested(qtbot):
    parent = QWidget()
    overlay = DebugOverlay(parent)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitForWindowShown(parent)

    # Simulate requested debug mode (e.g., launched with env / debug logger)
    overlay._debug_requested = True

    # When message is empty, the overlay should remain visible in debug mode
    overlay.show_message({"mouse": "", "hit": ""})
    assert overlay.isVisible()

    # And explicit clear should not hide it
    overlay._clear_and_hide()
    assert overlay.isVisible()


def test_debug_mode_suppresses_logger_when_requested(caplog):
    from image_viewer.crop.ui_crop_selection import SelectionRectItem
    import logging

    from PySide6.QtWidgets import QGraphicsPixmapItem

    from image_viewer.crop import ui_crop_selection as ucs

    sel = SelectionRectItem(QGraphicsPixmapItem())
    # Simulate that debug-mode was requested by the dialog
    setattr(sel, "_debug_overlay_requested", True)

    called: dict[str, str] = {}

    def fake_debug(msg, *args, **kwargs):
        called['msg'] = msg % args if args else msg

    orig_debug = ucs._logger.debug
    ucs._logger.debug = fake_debug
    try:
        sel._log_hit_transition(sel.MOVE, "OpenHandCursor")
    finally:
        ucs._logger.debug = orig_debug

    # Ensure that debug was not emitted to the module logger when debug-mode requested
    assert 'msg' not in called


def test_non_debug_mode_logs_to_logger(caplog):
    from image_viewer.crop.ui_crop_selection import SelectionRectItem
    import logging

    from PySide6.QtWidgets import QGraphicsPixmapItem

    sel = SelectionRectItem(QGraphicsPixmapItem())
    setattr(sel, "_debug_overlay_requested", False)

    # Monkeypatch the module logger's debug method to observe calls directly
    from image_viewer.crop import ui_crop_selection as ucs

    called: dict[str, str] = {}

    def fake_debug(msg, *args, **kwargs):
        called['msg'] = msg % args if args else msg

    orig_debug = ucs._logger.debug
    ucs._logger.debug = fake_debug
    try:
        sel._log_hit_transition(sel.MOVE, "OpenHandCursor")
    finally:
        ucs._logger.debug = orig_debug

    assert 'msg' in called and 'hit=' in called['msg']