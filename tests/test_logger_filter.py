from image_viewer.logger import setup_logger
import sys


def test_setup_logger_installs_filtered_stderr():
    # Ensure setup_logger can be called and that the stderr wrapper marks itself
    # as installed via the _filtered_by_image_viewer flag
    setup_logger()
    assert getattr(sys.stderr, "_filtered_by_image_viewer", False) is True
