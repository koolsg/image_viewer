"""Background worker to produce a sorted list of image files for a folder.

This avoids iterating the `QFileSystemModel` on the GUI thread which can block
when opening large folders.
"""

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


class DirectoryWorker(QObject):
    # Emits: folder_path, list_of_paths
    files_ready = Signal(str, list)

    @Slot(str)
    def run(self, folder_path: str) -> None:
        try:
            p = Path(folder_path)
            try:
                p = p.resolve()
            except Exception:
                p = p.absolute()
            if not p.is_dir():
                self.files_ready.emit(str(p), [])
                return

            exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
            files: list[str] = []
            # Use scandir-like iteration for performance
            for child in p.iterdir():
                try:
                    if not child.is_file():
                        continue
                    if child.suffix.lower() in exts:
                        try:
                            files.append(str(child.resolve()))
                        except Exception:
                            files.append(str(child.absolute()))
                except Exception:
                    continue

            files.sort()
            self.files_ready.emit(folder_path, files)
        except Exception:
            self.files_ready.emit(folder_path, [])
