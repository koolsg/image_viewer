from pathlib import Path
import sys
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication

# Ensure repo root
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from image_viewer.image_viewer import explorer_mode_operations as explorer_ops
from image_viewer.file_operations import show_delete_confirmation


def test_explorer_delete_confirmation_shows_filename(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])

    captured = {}

    def fake_show(parent, title, text, info):
        captured['title'] = title
        captured['text'] = text
        captured['info'] = info
        return False  # simulate user cancel

    monkeypatch.setattr('image_viewer.explorer_mode_operations.show_delete_confirmation', fake_show)

    parent_widget = SimpleNamespace()
    p = tmp_path / "file1.jpg"
    p.write_text("dummy")

    # Test single delete
    success, failed = explorer_ops.delete_files_to_recycle_bin([str(p)], parent_widget)
    assert 'file1.jpg' in captured['info']
    assert captured['title'] == 'Delete File'
    assert captured['text'] == 'Delete this file?'


def test_explorer_delete_confirmation_shows_count(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])

    captured = {}

    def fake_show(parent, title, text, info):
        captured['title'] = title
        captured['text'] = text
        captured['info'] = info
        return False  # simulate user cancel

    monkeypatch.setattr('image_viewer.explorer_mode_operations.show_delete_confirmation', fake_show)

    parent_widget = SimpleNamespace()
    p1 = tmp_path / "file1.jpg"
    p1.write_text("dummy")
    p2 = tmp_path / "file2.jpg"
    p2.write_text("dummy")

    # Test multi-delete
    success, failed = explorer_ops.delete_files_to_recycle_bin([str(p1), str(p2)], parent_widget)
    assert 'file1.jpg' not in captured['info']
    assert 'file2.jpg' not in captured['info']
    assert captured['title'] == 'Delete Files'
    assert 'Delete 2 item' in captured['text']
