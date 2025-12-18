import pytest
import tempfile
from pathlib import Path

from image_viewer.crop import apply_crop_to_file, validate_crop_bounds, _get_pyvips_module


def test_validate_crop_bounds():
    # Test valid crop bounds
    assert validate_crop_bounds(400, 300, (50, 50, 100, 100)) is True
    assert validate_crop_bounds(100, 100, (0, 0, 50, 50)) is True

    # Test invalid crop bounds
    assert validate_crop_bounds(400, 300, (-10, 50, 100, 100)) is False  # negative left
    assert validate_crop_bounds(400, 300, (50, -10, 100, 100)) is False  # negative top
    assert validate_crop_bounds(400, 300, (50, 50, 0, 100)) is False    # zero width
    assert validate_crop_bounds(400, 300, (50, 50, 100, 0)) is False    # zero height
    assert validate_crop_bounds(400, 300, (350, 50, 100, 100)) is False  # exceeds width
    assert validate_crop_bounds(400, 300, (50, 250, 100, 100)) is False  # exceeds height


def test_apply_crop_to_file():
    # Create a temporary image file for testing
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
        # Create a simple test image using pyvips if available
        try:
            pyvips = _get_pyvips_module()
            # Create a 100x100 test image
            img = pyvips.Image.black(100, 100, bands=3)
            img.write_to_file(tmp_file.name)
        except Exception:
            pytest.skip("pyvips not available for test image creation")

        tmp_path = Path(tmp_file.name)

        # Test applying crop
        output_path = tmp_path.parent / f"{tmp_path.stem}_cropped{tmp_path.suffix}"
        try:
            result_path = apply_crop_to_file(str(tmp_path), (10, 10, 50, 50), str(output_path))

            # Verify the output file was created
            assert Path(result_path).exists()
            assert result_path == str(output_path)

        finally:
            # Clean up - use try/except to handle permission errors on Windows
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
                if output_path.exists():
                    output_path.unlink()
            except (OSError, PermissionError):
                # Skip cleanup on permission errors (common on Windows)
                pass


def test_get_pyvips_module_raises_when_unavailable(monkeypatch):
    # Ensure _get_pyvips_module raises ImportError if pyvips is not available
    import image_viewer.crop as crop_mod

    # Temporarily hide pyvips
    original_pyvips = getattr(crop_mod, 'pyvips', None)
    monkeypatch.setattr(crop_mod, "pyvips", None)

    with pytest.raises(ImportError, match="pyvips is not available"):
        crop_mod._get_pyvips_module()

    # Restore original pyvips
    if original_pyvips is not None:
        monkeypatch.setattr(crop_mod, "pyvips", original_pyvips)
