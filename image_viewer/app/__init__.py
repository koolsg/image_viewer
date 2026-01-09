"""QML-facing application facade and state objects.

This package implements the recommended QML↔Python boundary:
- Single command entry: backend.dispatch(cmd, payload)
- UI binding via state QObjects (backend.viewer / backend.explorer / backend.settings)
- Python→QML notifications via backend.event / backend.taskEvent
"""
