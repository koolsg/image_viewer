from __future__ import annotations

from image_viewer.ops.crop_controller import RectN, clamp_rect_n


def test_move_clamps_to_bounds() -> None:
    cur = RectN(0.25, 0.25, 0.5, 0.5)
    prop = RectN(0.9, 0.9, 0.5, 0.5)

    out = clamp_rect_n(
        current=cur,
        proposed=prop,
        anchor="move",
        aspect_ratio=0.0,
        min_size=(0.01, 0.01),
    )

    assert 0.0 <= out.x <= 0.5
    assert 0.0 <= out.y <= 0.5
    assert out.w == cur.w
    assert out.h == cur.h


def test_handle_negative_sizes_are_normalized() -> None:
    cur = RectN(0.2, 0.2, 0.4, 0.4)
    # Proposed drag crosses over: negative w/h
    prop = RectN(0.6, 0.6, -0.2, -0.1)

    out = clamp_rect_n(
        current=cur,
        proposed=prop,
        anchor="br",
        aspect_ratio=0.0,
        min_size=(0.01, 0.01),
    )

    assert out.w >= 0
    assert out.h >= 0
    assert 0.0 <= out.x <= 1.0
    assert 0.0 <= out.y <= 1.0
    assert out.x + out.w <= 1.0 + 1e-9
    assert out.y + out.h <= 1.0 + 1e-9


def test_aspect_ratio_is_enforced() -> None:
    cur = RectN(0.25, 0.25, 0.5, 0.5)
    # Expand width from the right handle.
    prop = RectN(0.25, 0.25, 0.7, 0.5)

    out = clamp_rect_n(
        current=cur,
        proposed=prop,
        anchor="r",
        aspect_ratio=1.0,
        min_size=(0.01, 0.01),
    )

    assert abs((out.w / out.h) - 1.0) < 1e-6


def test_min_size_is_enforced() -> None:
    cur = RectN(0.25, 0.25, 0.5, 0.5)
    prop = RectN(0.25, 0.25, 0.01, 0.01)

    out = clamp_rect_n(
        current=cur,
        proposed=prop,
        anchor="br",
        aspect_ratio=0.0,
        min_size=(0.2, 0.3),
    )

    assert out.w >= 0.2
    assert out.h >= 0.3
