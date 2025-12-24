import contextlib
import re

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget


class DebugOverlay(QFrame):
    """Small translucent overlay that shows transient debug messages in the view's bottom-left

    Implemented using Qt widgets instead of HTML so font, layout and styling are
    controlled by Qt APIs for easier debugging and consistent appearance.
    """

    def __init__(self, parent_viewport: QWidget):
        super().__init__(parent_viewport)
        # Allow the overlay to auto-size vertically while capping width so the
        # left column (labels) and right column (values) remain aligned.
        self.setMaximumWidth(360)
        style = (
            "background-color: rgba(0, 0, 0, 200); color: #ffffff; "
            "border-radius: 6px; padding-left: 6px; padding-right: 6px;"
        )
        self.setStyleSheet(style)
        font = self.font()

        # font.setPointSize(26)
        with contextlib.suppress(Exception):
            font.setFamily("Courier New")
        self.setFont(font)

        # Build a simple key/value grid using Qt widgets so styles and fonts are honored
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(4)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(6)

        self._key_labels: dict[str, QLabel] = {}
        self._value_labels: dict[str, QLabel] = {}
        for i, k in enumerate(self.ROW_KEYS):
            key_lbl = QLabel(k, self)
            key_font = key_lbl.font()
            key_font.setBold(True)
            key_lbl.setFont(key_font)
            key_lbl.setStyleSheet("color: #bbbbbb;")

            val_lbl = QLabel("", self)
            val_lbl.setWordWrap(True)
            val_lbl.setStyleSheet("color: #ffffff;")

            self._grid.addWidget(key_lbl, i, 0, alignment=Qt.AlignmentFlag.AlignLeft)
            self._grid.addWidget(val_lbl, i, 1, alignment=Qt.AlignmentFlag.AlignLeft)

            self._key_labels[k] = key_lbl
            self._value_labels[k] = val_lbl

        vbox.addLayout(self._grid)

        # Plain text fallback label (shown when arbitrary text is provided)
        self._plain_label = QLabel("", self)
        self._plain_label.setWordWrap(True)
        self._plain_label.hide()
        vbox.addWidget(self._plain_label)

        self.hide()

        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.setInterval(50)
        # Pending message while throttling; may be str or dict
        self._pending_message: str | dict[str, str] | None = None
        self._throttle_timer.timeout.connect(self._apply_pending)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(1800)
        self._hide_timer.timeout.connect(self._clear_and_hide)

        # Current displayed values (merged across partial updates)
        self._current_table: dict[str, str] = {k: "" for k in self.ROW_KEYS}

        # Whether the overlay was requested by the dialog (controls 'always visible' behavior)
        self._debug_requested: bool = False

    def _apply_pending(self) -> None:
        if self._pending_message is not None:
            # Re-run the message handling for the pending item
            pm = self._pending_message
            self._pending_message = None
            with contextlib.suppress(Exception):
                self.show_message(pm)
        self._hide_timer.start()

    # Fixed ordered rows to display in the overlay (left column = item, right column = value)
    ROW_KEYS = ("mouse", "hit", "cursor", "handler")

    def _parse_message_table(self, msg: str | dict[str, str]) -> dict[str, str] | None:
        """Parse the incoming message into a normalization dict or return None.

        Supports dict input or plain strings with multiple `key=value` tokens per line.
        The parser finds all `key=value` pairs anywhere in the text so inputs like:
            "hover: hit=TOP_LEFT"
            "cursor=OpenHandCursor handler=h0 (x=10 y=20)"
        will produce keys `hit`, `cursor`, `handler`, `x`, `y`.
        """
        if isinstance(msg, dict):
            return {str(k): ("" if v is None else str(v)) for k, v in msg.items()}

        text = str(msg)
        parsed: dict[str, str] = {}
        # Find all simple key=value pairs (keys are alphanumeric/_ identifiers,
        # values are non-whitespace tokens; this handles multiple pairs per line)
        for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s)]+)", text):
            k = m.group(1)
            v = m.group(2)
            parsed[k] = v
        return parsed if parsed else None

    def _update_widgets_from_table(self, table: dict[str, str]) -> bool:
        """Update the internal QLabel widgets from the provided table.

        Returns True if at least one value is non-empty (so the overlay should be shown)
        and False if all values are empty (overlay should be hidden).
        """
        any_value = False
        for k in self.ROW_KEYS:
            v = table.get(k, "")
            text = "" if v is None else str(v)
            if bool(text.strip()):
                any_value = True
            with contextlib.suppress(Exception):
                self._value_labels[k].setText(text)
        return any_value

    def show_message(self, msg: str | dict[str, str]) -> None:
        """Show a message in the overlay.

        Accepts either a plain string or a dictionary mapping message types (left column)
        to content (right column). Uses a fixed row ordering so the left column stays
        consistent (even when values are empty). If all displayed values are empty,
        the overlay is hidden to avoid showing an empty box.
        """
        try:
            table = self._parse_message_table(msg)

            if table is not None:
                # Merge parsed table into current display state so partial updates
                # (e.g., mouse-only updates) do not wipe other keys like `hit`/`handler`.
                display_table = dict(self._current_table)
                for k, v in table.items():
                    # store as-is (allow explicit empty strings to clear keys)
                    display_table[str(k)] = v

                # Update the widget labels from the merged table
                any_value = self._update_widgets_from_table(display_table)
                if not any_value:
                    # If merged table is empty, clear current state
                    self._current_table = {k: "" for k in self.ROW_KEYS}
                    self._plain_label.hide()
                    # Clear visual labels
                    for v in self._value_labels.values():
                        with contextlib.suppress(Exception):
                            v.setText("")
                    # If debug was explicitly requested, keep overlay visible (empty grid)
                    if getattr(self, "_debug_requested", False):
                        if not self.isVisible():
                            self.show()
                        return
                    # Otherwise hide to avoid showing an empty box
                    self.hide()
                    return

                # Commit merged values to current state
                self._current_table = display_table

                # Ensure plain fallback label is hidden while grid is used
                self._plain_label.hide()

                if not self.isVisible():
                    self.show()
                if self._throttle_timer.isActive():
                    self._pending_message = table
                    return
                # Let widgets resize to fit content and then reposition
                with contextlib.suppress(Exception):
                    self.adjustSize()
                    self.reposition()
                self._hide_timer.start()
                self._throttle_timer.start()
                return

            # Fallback: plain text
            if not self.isVisible():
                self.show()
            if self._throttle_timer.isActive():
                self._pending_message = str(msg)
                return
            # Show plain fallback text in a dedicated label
            with contextlib.suppress(Exception):
                self._plain_label.setText(str(msg))
                self._plain_label.show()
                for k in self.ROW_KEYS:
                    with contextlib.suppress(Exception):
                        self._value_labels[k].setText("")
                self.adjustSize()
                self.reposition()
            self._hide_timer.start()
            self._throttle_timer.start()
        except Exception:
            pass

    def reposition(self) -> None:
        try:
            parent = self.parentWidget()
            if parent is None:
                return
            ph = parent.height()
            x = 6
            y = ph - self.height() - 6
            self.move(x, y)
        except Exception:
            pass

    def _clear_and_hide(self) -> None:
        # Clear the current state and hide the overlay unless debug was requested
        try:
            self._current_table = {k: "" for k in self.ROW_KEYS}
            for v in self._value_labels.values():
                with contextlib.suppress(Exception):
                    v.setText("")
            # Only hide if not explicitly requested
            if not getattr(self, "_debug_requested", False):
                self.hide()
        except Exception:
            pass


class ViewportWatcher(QObject):
    def __init__(self, overlay: DebugOverlay, parent: QObject | None = None):
        super().__init__(parent)
        self._overlay = overlay

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore
        try:
            # Use the typed enum member for compatibility with PySide6 typing
            if event.type() == QEvent.Type.Resize:
                QTimer.singleShot(0, self._overlay.reposition)
        except Exception:
            pass
        return False
