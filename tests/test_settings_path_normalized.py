from pathlib import Path
import tempfile

from image_viewer.settings_manager import SettingsManager
from image_viewer.path_utils import abs_path_str


def test_settings_path_is_normalized(tmp_path):
    # Create a temp directory and construct a forward-slash style path
    cfg_dir = tmp_path / "somecfg"
    cfg_dir.mkdir()
    forward_slash_path = str(cfg_dir).replace("\\", "/") + "/settings.json"

    sm = SettingsManager(forward_slash_path)

    # The stored settings_path must be normalized via abs_path_str
    assert sm.settings_path == abs_path_str(forward_slash_path)
