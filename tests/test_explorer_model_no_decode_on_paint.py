import pytest

PySide6 = pytest.importorskip("PySide6")  # noqa: F401

from PySide6.QtCore import Qt

from image_viewer.image_engine.explorer_model import ExplorerTableModel


class _EngineThatMustNotDecode:
    """Minimal engine stub.

    ExplorerTableModel must NOT trigger thumbnail decode requests from
    DecorationRole/painters.
    """

    def request_thumbnail(self, *_args, **_kwargs):  # noqa: ANN001
        raise AssertionError("ExplorerTableModel attempted to request a thumbnail during paint")


def test_explorer_model_decoration_role_does_not_request_thumbnail(tmp_path) -> None:
    engine = _EngineThatMustNotDecode()
    model = ExplorerTableModel(engine)

    f = tmp_path / "example.webp"
    f.write_bytes(b"not an image; just needs a path")

    model._on_entries_changed(
        str(tmp_path),
        [
            {
                "path": str(f),
                "name": f.name,
                "suffix": f.suffix,
                "size": f.stat().st_size,
                "mtime_ms": int(f.stat().st_mtime * 1000),
                "is_image": True,
            }
        ],
    )

    idx = model.index(0, model.COL_NAME)

    # Should return either a QIcon (OS icon fallback) or None, but must not
    # trigger decoding.
    _ = model.data(idx, Qt.ItemDataRole.DecorationRole)


def test_explorer_model_uses_thumb_bytes_without_requesting_decode(tmp_path) -> None:
    engine = _EngineThatMustNotDecode()
    model = ExplorerTableModel(engine)

    f = tmp_path / "example.png"
    f.write_bytes(b"fake")

    model._on_entries_changed(
        str(tmp_path),
        [
            {
                "path": str(f),
                "name": f.name,
                "suffix": f.suffix,
                "size": f.stat().st_size,
                "mtime_ms": int(f.stat().st_mtime * 1000),
                "is_image": True,
            }
        ],
    )

    # Feed a known-good tiny PNG, so QPixmap can load it.
    tiny_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x89\x81\x8f\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    # Model keys are db_key(path); easiest is to call internal handler which does the keying.
    model._on_thumb_rows([{"path": str(f), "thumbnail": tiny_png, "width": 1, "height": 1}])

    idx = model.index(0, model.COL_NAME)
    icon = model.data(idx, Qt.ItemDataRole.DecorationRole)

    # Should successfully build an icon from bytes.
    assert icon is not None
