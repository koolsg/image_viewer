"""Background worker to produce a sorted list of image files for a folder.

This avoids iterating the `QFileSystemModel` on the GUI thread which can block
when opening large folders.

Important: Qt may represent paths with forward slashes. This worker emits
absolute, normalized folder and file paths so downstream comparisons are stable.
"""

from PySide6.QtCore import QObject, Signal, Slot

from image_viewer.path_utils import abs_dir, abs_dir_str, abs_path_str


class DirectoryWorker(QObject):
    # Emits: folder_path, list_of_paths
    files_ready = Signal(str, list)

    @Slot(str)
    def run(self, folder_path: str) -> None:
        try:
            p = abs_dir(folder_path)
            if not p.is_dir():
                self.files_ready.emit(abs_dir_str(p), [])
                return

            exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
            files: list[str] = []
            # Use scandir-like iteration for performance
            for child in p.iterdir():
                try:
                    if not child.is_file():
                        continue
                    if child.suffix.lower() in exts:
                        files.append(abs_path_str(child))
                except Exception:
                    continue

            files.sort()
            self.files_ready.emit(abs_dir_str(p), files)
        except Exception:
            self.files_ready.emit(abs_dir_str(folder_path), [])
