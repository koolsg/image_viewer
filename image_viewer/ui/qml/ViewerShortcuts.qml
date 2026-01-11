pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window

Item {
    id: root
    property var backend

    Shortcut {
        sequence: "Escape"
        enabled: !!root.backend && !!root.backend.viewer && root.backend.viewer.viewMode && !(root.backend.crop && root.backend.crop.active)
        onActivated: {
            if (!root.backend) return
            root.backend.dispatch("closeView", null)
        }
    }

    Shortcut {
        sequence: "Return"
        enabled: !!root.backend && !!root.backend.viewer && root.backend.viewer.viewMode && !(root.backend.crop && root.backend.crop.active)
        onActivated: {
            if (!root.backend) return
            root.backend.dispatch("closeView", null)
        }
    }

    Shortcut {
        sequence: "C"
        enabled: !!root.backend && !!root.backend.viewer && root.backend.viewer.viewMode && !(root.backend.crop && root.backend.crop.active)
        onActivated: {
            if (!root.backend) return
            root.backend.dispatch("openCrop", null)
        }
    }

    Shortcut {
        sequence: "Delete"
        enabled: !!root.backend && !!root.backend.viewer && root.backend.viewer.viewMode && !(root.backend.crop && root.backend.crop.active)
        onActivated: {
            if (!root.backend || !root.backend.viewer) return
            var p = root.backend.viewer.currentPath
            if (!p) return
            // ViewWindow defines `showViewDeleteDialog(path)` and owns the actual
            // DeleteConfirmationDialog instance.
            var w = root.Window.window
            var key = "show" + "ViewDeleteDialog"
            var fn = w ? w[key] : null
            if (typeof fn === "function") {
                fn.call(w, p)
            }
        }
    }
}
