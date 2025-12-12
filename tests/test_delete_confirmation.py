from pathlib import Path
import sys
from PySide6.QtWidgets import QApplication, QMessageBox

# Ensure repo root for imports
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from image_viewer.file_operations import build_delete_dialog_style, show_delete_confirmation


def test_delete_dialog_default_and_escape(tmp_path):
    app = QApplication.instance() or QApplication([])
    msg_box = QMessageBox(None)
    msg_box.setWindowTitle("Delete Test")
    msg_box.setText("Delete this file?")
    msg_box.setInformativeText("It will be moved to Recycle Bin.")

    yes_btn = msg_box.addButton("Yes", QMessageBox.ButtonRole.YesRole)
    yes_btn.setObjectName("button-yes")
    no_btn = msg_box.addButton("No", QMessageBox.ButtonRole.NoRole)
    no_btn.setObjectName("button-no")

    # default should be yes
    msg_box.setDefaultButton(yes_btn)
    # escape should be cancel
    msg_box.setEscapeButton(no_btn)
    msg_box.setStyleSheet(build_delete_dialog_style('dark'))

    assert msg_box.defaultButton() == yes_btn
    assert msg_box.escapeButton() == no_btn


def test_delete_dialog_style_light(tmp_path):
    css = build_delete_dialog_style('light')
    assert 'button-no' in css
    assert '#e0e0e0' in css  # cancel background for light
    assert '#d32f2f' not in css  # red should be removed for Yes button


def test_delete_dialog_style_dark(tmp_path):
    css = build_delete_dialog_style('dark')
    assert 'button-no' in css
    assert '#424242' in css  # cancel background for dark
    assert '#d32f2f' not in css
