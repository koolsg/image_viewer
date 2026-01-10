pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: root
    property var backend

    Shortcut {
        sequence: "Escape"
        enabled: !!root.backend && !!root.backend.viewer && root.backend.viewer.viewMode
        onActivated: {
            if (!root.backend) return
            root.backend.dispatch("closeView", null)
        }
    }

    Shortcut {
        sequence: "Return"
        enabled: !!root.backend && !!root.backend.viewer && root.backend.viewer.viewMode
        onActivated: {
            if (!root.backend) return
            root.backend.dispatch("closeView", null)
        }
    }
}
