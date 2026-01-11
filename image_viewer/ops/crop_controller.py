from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RectN:
    """Normalized rect (0..1) in (x, y, w, h) form."""

    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    def normalized(self) -> RectN:
        x, y, w, h = float(self.x), float(self.y), float(self.w), float(self.h)
        if w < 0:
            x = x + w
            w = -w
        if h < 0:
            y = y + h
            h = -h
        return RectN(x, y, w, h)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _anchor_flags(anchor: str) -> tuple[bool, bool, bool, bool]:
    """Return (fix_left, fix_right, fix_top, fix_bottom)."""
    a = (anchor or "").lower()
    if a in {"move", "center", "c", ""}:
        return False, False, False, False

    # Canonical handle names: tl,tr,bl,br,l,r,t,b
    known = {
        "tl": (True, False, True, False),
        "tr": (False, True, True, False),
        "bl": (True, False, False, True),
        "br": (False, True, False, True),
        "l": (True, False, False, False),
        "r": (False, True, False, False),
        "t": (False, False, True, False),
        "b": (False, False, False, True),
    }
    if a in known:
        return known[a]

    # Fallback: treat letter presence as intent.
    return ("l" in a, "r" in a, "t" in a, "b" in a)


def _apply_aspect(*, w: float, h: float, cur_w: float, cur_h: float, ratio: float) -> tuple[float, float]:
    r = float(ratio)
    if r <= 0:
        return w, h

    dw = abs(w - cur_w)
    dh = abs(h - cur_h)
    if dw >= dh:
        return w, max(h, w / r)
    return max(w, h * r), h


def _apply_bounds(*, x: float, y: float, w: float, h: float, min_size: tuple[float, float]) -> RectN:
    min_w, min_h = float(min_size[0]), float(min_size[1])
    # Clamp size first.
    w = _clamp(w, min_w, 1.0)
    h = _clamp(h, min_h, 1.0)
    # Then clamp position.
    x = _clamp(x, 0.0, max(0.0, 1.0 - w))
    y = _clamp(y, 0.0, max(0.0, 1.0 - h))
    return RectN(x, y, w, h)


def clamp_rect_n(
    *,
    current: RectN,
    proposed: RectN,
    anchor: str,
    aspect_ratio: float,
    min_size: tuple[float, float],
) -> RectN:
    """Clamp/adjust a proposed normalized crop rect.

    Rules:
    - Keep rect within [0..1] bounds.
    - Enforce minimum width/height.
    - Optionally enforce aspect ratio (width/height), trying to preserve the
      user's dominant change direction (compares against current).

    Anchor semantics:
    - For handle drags (tl,tr,bl,br,l,r,t,b), the opposite side(s) are treated as
      fixed.
    - For move/center, size is preserved; position is clamped by shifting.
    """

    min_w, min_h = float(min_size[0]), float(min_size[1])
    cur = current.normalized()
    prop = proposed.normalized()

    a = (anchor or "").lower()
    if a in {"move", "center", "c", ""}:
        # Move: preserve size, clamp by shifting.
        w = max(cur.w, min_w)
        h = max(cur.h, min_h)
        return _apply_bounds(x=prop.x, y=prop.y, w=w, h=h, min_size=min_size)

    fix_left, fix_right, fix_top, fix_bottom = _anchor_flags(a)
    x1_fixed = cur.x if fix_left else None
    x2_fixed = cur.x2 if fix_right else None
    y1_fixed = cur.y if fix_top else None
    y2_fixed = cur.y2 if fix_bottom else None

    x, y, w, h = prop.x, prop.y, prop.w, prop.h
    w = max(w, min_w)
    h = max(h, min_h)

    w, h = _apply_aspect(w=w, h=h, cur_w=cur.w, cur_h=cur.h, ratio=aspect_ratio)
    w = max(w, min_w)
    h = max(h, min_h)

    if x1_fixed is not None and x2_fixed is None:
        x = x1_fixed
    elif x2_fixed is not None and x1_fixed is None:
        x = x2_fixed - w
    elif x1_fixed is not None and x2_fixed is not None:
        x = x1_fixed
        w = max(min_w, x2_fixed - x1_fixed)

    if y1_fixed is not None and y2_fixed is None:
        y = y1_fixed
    elif y2_fixed is not None and y1_fixed is None:
        y = y2_fixed - h
    elif y1_fixed is not None and y2_fixed is not None:
        y = y1_fixed
        h = max(min_h, y2_fixed - y1_fixed)

    return _apply_bounds(x=x, y=y, w=w, h=h, min_size=min_size)
