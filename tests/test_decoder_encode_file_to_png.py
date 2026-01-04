import pytest

pytest.importorskip("pyvips")

from pathlib import Path
from image_viewer.image_engine.decoder import encode_image_to_png
import pyvips


def test_encode_image_file_to_png(tmp_path: Path):
    # Create a small RGB image using pyvips and write to disk
    w, h = 7, 5
    r = pyvips.Image.black(w, h)
    g = pyvips.Image.black(w, h)
    b = pyvips.Image.black(w, h)
    # Fill channels with simple gradients
    r = r + 50
    g = g + 100
    b = b + 150
    img = r.bandjoin(g)
    img = img.bandjoin(b)

    infile = tmp_path / "in.png"
    img.write_to_file(str(infile))

    path, out, err = encode_image_to_png(str(infile), target_width=3, target_height=None)
    assert path == str(infile)
    assert err is None
    assert out is not None
    assert isinstance(out, (bytes, bytearray))
    assert bytes(out).startswith(b"\x89PNG")
