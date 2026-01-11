from __future__ import annotations

import os
import tempfile

import pytest

import image_viewer.crop.crop as crop_mod


class _FakeImage:
    def __init__(self, width: int, height: int, path: str):
        self.width = width
        self.height = height
        self._path = path

    def crop(self, left: int, top: int, width: int, height: int):
        class _Cropped:
            def __init__(self, out_path: str):
                self._out = out_path

            def write_to_file(self, p: str):
                with open(p, "wb") as f:
                    f.write(b"CROPPED")

        return _Cropped(self._path + ".cropped")


class _FakePyvips:
    def __init__(self, width: int, height: int, path: str):
        self._width = width
        self._height = height
        self._path = path

    def Image(self):
        return self

    def new_from_file(self, path: str, access: str = "sequential"):
        return _FakeImage(self._width, self._height, path)


def test_apply_crop_to_file_happy(tmp_path, monkeypatch):
    # Create a fake source file; our fake pyvips doesn't read it, but ensures path is passed.
    src = tmp_path / "src.png"
    src.write_bytes(b"PNGDATA")

    # pyvips.Image.new_from_file(...) is how the real module is used; provide
    # a shim compatible with that API.
    class _Shim:
        Image = type("I", (), {"new_from_file": staticmethod(lambda p, access="sequential": _FakeImage(100, 80, p))})

    monkeypatch.setattr(crop_mod, "pyvips", _Shim)

    out = tmp_path / "out.png"
    result = crop_mod.apply_crop_to_file(str(src), (10, 10, 20, 20), str(out))

    assert result == str(out)
    assert out.exists()
    assert out.read_bytes() == b"CROPPED"


def test_validate_crop_bounds():
    assert crop_mod.validate_crop_bounds(100, 80, (0, 0, 100, 80))
    assert not crop_mod.validate_crop_bounds(100, 80, (-1, 0, 10, 10))
    assert not crop_mod.validate_crop_bounds(100, 80, (0, 0, 0, 10))
    assert not crop_mod.validate_crop_bounds(100, 80, (90, 0, 20, 10))
