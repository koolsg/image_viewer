pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: root

    // Minimal explorer-local shortcuts (file operations and open)
    property var app
    property var backend
    property var grid
    property var dialogs

    function _collectSelectedPaths() {
        var sel = (root.grid && root.grid.selectedIndices) ? root.grid.selectedIndices : []
        var paths = []
        if (!root.backend || !root.backend.explorer || !root.backend.explorer.imageFiles) return paths
        for (var i = 0; i < sel.length; ++i) {
            var id = sel[i]
            if (id >= 0 && id < root.backend.explorer.imageFiles.length) {
                paths.push(root.backend.explorer.imageFiles[id])
            }
        }
        return paths
    }

    Shortcut {
        sequence: "Return"
        enabled: !!root.backend && !(root.backend.viewer && root.backend.viewer.viewMode)
        onActivated: {
            if (!root.backend) return
            var idx = (root.backend.explorer.currentIndex >= 0) ? root.backend.explorer.currentIndex : -1
            if (idx >= 0 && root.backend.explorer.imageFiles && idx < root.backend.explorer.imageFiles.length) {
                root.app.explorerSelectedPath = root.backend.explorer.imageFiles[idx]
                root.backend.dispatch("setViewMode", { value: true })
            }
        }
    }

    Shortcut {
        sequence: "Delete"
        enabled: !!root.backend && !(root.backend.viewer && root.backend.viewer.viewMode)
        onActivated: {
            var paths = root._collectSelectedPaths()
            if (paths.length > 0) {
                var title = (paths.length === 1) ? "Delete File" : "Delete Files"
                var info = (paths.length === 1) ? (paths[0].replace(/^.*[\\/]/, "") + "\n\nIt will be moved to Recycle Bin.") : (paths.length + " files will be moved to Recycle Bin.")
                if (root.app) root.app.showDeleteDialog(title, "", info, paths)
            }
        }
    }

    Shortcut {
        sequence: "F2"
        enabled: !!root.backend && !(root.backend.viewer && root.backend.viewer.viewMode)
        onActivated: {
            var sel = (root.grid && root.grid.selectedIndices) ? root.grid.selectedIndices : []
            if (sel.length === 1 && root.backend && root.backend.explorer.imageFiles) {
                var idx = sel[0]
                if (idx >= 0 && idx < root.backend.explorer.imageFiles.length) {
                    var selPath = root.backend.explorer.imageFiles[idx]
                    if (root.dialogs) root.dialogs.openRenameDialog(selPath, selPath.replace(/^.*[\\/]/, ""))
                }
            }
        }
    }

    Shortcut {
        sequence: "Ctrl+C"
        enabled: !!root.backend && !(root.backend.viewer && root.backend.viewer.viewMode)
        onActivated: {
            var paths = root._collectSelectedPaths()
            if (paths.length > 0) root.backend.dispatch("copyFiles", { paths: paths })
        }
    }

    Shortcut {
        sequence: "Ctrl+X"
        enabled: !!root.backend && !(root.backend.viewer && root.backend.viewer.viewMode)
        onActivated: {
            var paths = root._collectSelectedPaths()
            if (paths.length > 0) root.backend.dispatch("cutFiles", { paths: paths })
        }
    }

    Shortcut {
        sequence: "Ctrl+V"
        enabled: !!root.backend && !(root.backend.viewer && root.backend.viewer.viewMode)
        onActivated: {
            if (root.backend && root.backend.explorer && root.backend.explorer.clipboardHasFiles) {
                root.backend.dispatch("pasteFiles", null)
            }
        }
    }
}
