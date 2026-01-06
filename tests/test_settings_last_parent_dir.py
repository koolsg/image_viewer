from pathlib import Path

from image_viewer.settings_manager import SettingsManager


def test_last_parent_dir_stores_and_reads(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    settings_file = cfg / "settings.json"

    sm = SettingsManager(str(settings_file))

    # Save a directory
    sm.set("last_parent_dir", str(cfg))
    assert sm.last_parent_dir == str(cfg)

    # Save a file path -> last_parent_dir should return the parent dir
    f = cfg / "file.txt"
    f.write_text("hi")
    sm.set("last_parent_dir", str(f))
    assert sm.last_parent_dir == str(cfg)

    # Save non-existent path -> property returns None
    sm.set("last_parent_dir", str(cfg / "nope"))
    assert sm.last_parent_dir is None
