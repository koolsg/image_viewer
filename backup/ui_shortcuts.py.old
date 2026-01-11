from PySide6.QtCore import Qt

from .view_mode_operations import delete_current_file


def dispatch_key_event(viewer, event) -> bool:
    """
    Centralized key event dispatcher.
    Returns True if the event was handled and should stop propagation.
    Returns False if the event should be handled by the default mechanism.
    """
    try:
        key = event.key()
    except Exception:
        return False

    # Common / Global Interactions
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        return _handle_enter(viewer)

    # Logic depends on the current mode
    explorer_state = getattr(viewer, "explorer_state", None)
    if not explorer_state:
        return False

    is_view_mode = getattr(explorer_state, "view_mode", True)

    if is_view_mode:
        return _handle_view_mode_keys(viewer, key)

    return False


def _handle_enter(viewer) -> bool:
    # In specific widget contexts (like renaming in Tree), we might NOT want to toggle mode.
    # However, keyPressEvent in main usually catches it before child widgets if we are filtering events,
    # OR after if we override keyPressEvent.
    # If we use main.py's keyPressEvent override, it happens *before* propagation if we don't call super,
    # or *after* propagation if child didn't accept it?
    # Actually QMainWindow keyPressEvent is usually called if focused widget didn't accept.
    # But if we want to catch global shortcuts, overriding keyPress in Main Window works for unhandled keys.
    # BUT for Arrows in Explorer Grid, Grid WILL handle them.
    # The issue was QShortcut (WindowContext) stealing them from Grid.
    # By moving to keyPressEvent in MainWindow, Grid gets first dibs if it has focus.

    # If we are in Explorer mode and focus is on Grid, Enter might mean "Open Image".
    # Grid handles Enter potentially.
    # If Grid handles it, MainWindow won't see it (assuming Grid accepts).
    # Let's see grid logic. It does handle Enter.

    if hasattr(viewer, "toggle_view_mode"):
        viewer.toggle_view_mode()
        return True
    return False


def _handle_view_mode_keys(viewer, key) -> bool:  # noqa: PLR0911
    """Handle keys specific to View Mode."""
    # Navigation and simple actions
    actions = {
        Qt.Key.Key_Right: "next_image",
        Qt.Key.Key_Left: "prev_image",
        Qt.Key.Key_Home: "first_image",
        Qt.Key.Key_End: "last_image",
        Qt.Key.Key_Space: "snap_to_global_view",
    }

    if key in actions:
        method_name = actions[key]
        if hasattr(viewer, method_name):
            getattr(viewer, method_name)()
            return True

    # Zoom
    if key == Qt.Key.Key_Up and hasattr(viewer, "zoom_by"):
        viewer.zoom_by(1.25)
        return True
    elif key == Qt.Key.Key_Down and hasattr(viewer, "zoom_by"):
        viewer.zoom_by(0.75)
        return True

    # Rotation
    if key == Qt.Key.Key_A and viewer.canvas:
        viewer.canvas.rotate_by(-90)
        return True
    elif key == Qt.Key.Key_D and viewer.canvas:
        viewer.canvas.rotate_by(90)
        return True

    # Deletion
    if key == Qt.Key.Key_Delete:
        delete_current_file(viewer)
        return True

    return False
