from __future__ import annotations

from PySide6.QtCore import Qt


def cursor_name(cursor_shape) -> str:
    cmap = {
        Qt.CursorShape.SizeFDiagCursor: "SizeFDiagCursor",
        Qt.CursorShape.SizeBDiagCursor: "SizeBDiagCursor",
        Qt.CursorShape.SizeHorCursor: "SizeHorCursor",
        Qt.CursorShape.SizeVerCursor: "SizeVerCursor",
        Qt.CursorShape.OpenHandCursor: "OpenHandCursor",
        Qt.CursorShape.ClosedHandCursor: "ClosedHandCursor",
        Qt.CursorShape.CrossCursor: "CrossCursor",
        Qt.CursorShape.ArrowCursor: "ArrowCursor",
    }
    try:
        if isinstance(cursor_shape, int):
            return cmap.get(cursor_shape, str(cursor_shape))
        if hasattr(cursor_shape, "shape"):
            return cmap.get(cursor_shape.shape(), str(cursor_shape.shape()))
        return str(cursor_shape)
    except Exception:
        return str(cursor_shape)


def overlay_message(
    hit_name: str, cursor: str, handler_name: str | None = None, x: int | None = None, y: int | None = None
) -> str:
    if handler_name and x is not None and y is not None:
        return f"hover: hit={hit_name}\ncursor={cursor} handler={handler_name} (x={x} y={y})"
    return f"hover: hit={hit_name}\ncursor={cursor} handler={handler_name or 'none'}"
