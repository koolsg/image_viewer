import pytest

from image_viewer.crop import detect_crop_by_ratio


def test_detect_crop_by_ratio_centered():
    # Image 400x300, target 1:1 -> should produce 300x300 centered
    left, top, w, h = detect_crop_by_ratio(400, 300, 1, 1)
    assert w == 300 and h == 300
    assert left == 50 and top == 0


def test_detect_crop_by_ratio_wide():
    # Image 800x200, target 3:2 -> should produce width smaller than original
    left, top, w, h = detect_crop_by_ratio(800, 200, 3, 2)
    assert h == 200
    assert w == int(round(200 * (3.0 / 2.0)))


def test_make_preview_requires_pyvips(monkeypatch):
    # Ensure make_crop_preview raises if pyvips is not available
    import image_viewer.crop as crop_mod

    monkeypatch.setattr(crop_mod, "pyvips", None)
    with pytest.raises(RuntimeError):
        crop_mod.make_crop_preview("/non/existent.jpg", (0, 0, 10, 10))
