"""Folder tree widget (for file explorer mode)"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from .logger import get_logger

_logger = get_logger("ui_explorer_tree")


class FolderTreeWidget(QTreeWidget):
    """Widget that displays folder structure in tree form"""

    folder_selected = Signal(str)  # Signal when folder path is selected

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Folder"])
        self.setColumnCount(1)
        self.itemClicked.connect(self._on_item_clicked)
        self.setMinimumWidth(250)
        self.setMaximumWidth(500)

        _logger.debug("FolderTreeWidget initialized")

    def set_root_path(self, root_path: str) -> None:
        """Set root folder and build tree

        Args:
            root_path: Root folder path
        """
        try:
            self.clear()
            root_item = self._build_tree(root_path)
            self.addTopLevelItem(root_item)
            root_item.setExpanded(True)
            _logger.debug("tree built: root_path=%s", root_path)
        except Exception as ex:
            _logger.error("failed to set_root_path: %s", ex)

    def _build_tree(self, path: str) -> QTreeWidgetItem:
        """Recursively build folder tree

        Args:
            path: Current folder path

        Returns:
            QTreeWidgetItem: Tree item
        """
        try:
            path_obj = Path(path)
            name = path_obj.name or path
            item = QTreeWidgetItem([name])
            item.setData(0, Qt.UserRole, str(path))  # Store path

            # Recursively add subfolders
            try:
                sub_paths = sorted(path_obj.iterdir())
            except PermissionError:
                _logger.debug("permission denied: %s", path)
                return item

            for sub_path in sub_paths:
                try:
                    if sub_path.is_dir() and not sub_path.name.startswith("."):
                        sub_item = self._build_tree(str(sub_path))
                        item.addChild(sub_item)
                except (PermissionError, OSError):
                    continue

            return item
        except Exception as ex:
            _logger.debug("error building tree node: path=%s, error=%s", path, ex)
            item = QTreeWidgetItem([str(Path(path).name)])
            item.setData(0, Qt.UserRole, str(path))
            return item

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Emit signal when tree item is selected

        Args:
            item: Selected tree item
            column: Selected column (always 0)
        """
        try:
            path = item.data(0, Qt.UserRole)
            if path and Path(path).is_dir():
                self.folder_selected.emit(path)
                _logger.debug("folder selected: %s", path)
        except Exception as ex:
            _logger.debug("error on item click: %s", ex)
