/*
 AppHeader.qml — 프레임리스 윈도우용 커스텀 타이틀바/헤더 및 메뉴를 구현하는 컴포넌트.
 이 파일은 창 이동/더블클릭/창 컨트롤(최소/최대/닫기)과 상단 리사이즈 핸들을 포함하여, 플랫폼별 헤더 동작을 캡슐화합니다.
*/

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts

Column {
    id: root

    // The owning ApplicationWindow (App.qml)
    property var app
    property var theme
    // AppDialogs instance from App.qml
    property var dialogs

    width: root.app ? root.app.width : 0

    Rectangle {
        id: customTitleBar
        width: parent.width
        height: 32
        color: root.theme.surface
        z: 1000

        // NOTE (Windows): Enabling a layer here can cause visible trailing/lag during
        // startSystemMove() window drags (the title bar appears to "chase" the window).
        layer.enabled: false

        Item {
            id: dragRegion
            anchors.left: parent.left
            anchors.right: windowControls.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom

            DragHandler {
                id: dragHandler
                acceptedButtons: Qt.LeftButton
                enabled: !!root.app && root.app._inputReady
                onActiveChanged: if (active && root.app) root.app.startSystemMove()
            }

            TapHandler {
                acceptedButtons: Qt.LeftButton
                onDoubleTapped: {
                    if (!root.app) return
                    if (root.app.visibility === Window.Maximized) {
                        root.app.showNormal()
                    } else {
                        root.app.showMaximized()
                    }
                }
            }

            Label {
                id: titleLabel
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: root.app ? root.app.title : ""
                color: root.theme.text
                font.pixelSize: 12
            }
        }

        Row {
            id: windowControls
            anchors.right: parent.right
            height: parent.height
            spacing: 0
            z: 10

            Button {
                id: minBtn
                width: 46
                height: parent.height
                flat: true
                hoverEnabled: true
                background: Rectangle {
                    anchors.fill: parent
                    color: minBtn.hovered ? root.theme.hover : "transparent"
                }
                contentItem: Text {
                    anchors.fill: parent
                    text: "—"
                    color: root.theme.text
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: if (root.app) root.app.showMinimized()
            }

            Button {
                id: maxBtn
                width: 46
                height: parent.height
                flat: true
                hoverEnabled: true
                background: Rectangle {
                    anchors.fill: parent
                    color: maxBtn.hovered ? root.theme.hover : "transparent"
                }
                contentItem: Text {
                    anchors.fill: parent
                    text: root.app && root.app.visibility === Window.Maximized ? "❐" : "☐"
                    color: root.theme.text
                    font.pixelSize: 14
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: {
                    if (!root.app) return
                    if (root.app.visibility === Window.Maximized) {
                        root.app.showNormal()
                    } else {
                        root.app.showMaximized()
                    }
                }
            }

            Button {
                id: closeBtn
                width: 46
                height: parent.height
                flat: true
                hoverEnabled: true
                background: Rectangle {
                    anchors.fill: parent
                    color: closeBtn.hovered ? "#E81123" : "transparent"
                }
                contentItem: Text {
                    anchors.fill: parent
                    text: "✕"
                    color: closeBtn.hovered ? "#FFFFFF" : root.theme.text
                    font.pixelSize: 14
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: Qt.quit()
            }
        }

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 3
            color: root.theme.border
        }

        // Top-edge resize handles must live in the header tree.
        // IMPORTANT: In ApplicationWindow, Overlay.overlay is aligned to the *content area*
        // (below `header:`). If we anchor the top resize handle to Overlay.overlay.top,
        // it will appear under the header instead of at the true window top edge.
        MouseArea {
            id: topResizeHeader
            height: 6
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            cursorShape: Qt.SizeVerCursor
            enabled: !!root.app && root.app.visibility !== Window.Maximized
            z: 100
            onPressed: if (root.app) root.app.startSystemResize(Qt.TopEdge)
        }
        MouseArea {
            id: topLeftResizeHeader
            width: 10
            height: 10
            anchors.left: parent.left
            anchors.top: parent.top
            cursorShape: Qt.SizeFDiagCursor
            enabled: !!root.app && root.app.visibility !== Window.Maximized
            z: 101
            onPressed: if (root.app) root.app.startSystemResize(Qt.TopEdge | Qt.LeftEdge)
        }
        MouseArea {
            id: topRightResizeHeader
            width: 10
            height: 10
            anchors.right: parent.right
            anchors.top: parent.top
            cursorShape: Qt.SizeBDiagCursor
            enabled: !!root.app && root.app.visibility !== Window.Maximized
            z: 101
            onPressed: if (root.app) root.app.startSystemResize(Qt.TopEdge | Qt.RightEdge)
        }
    }

    // Menu row directly under the title bar (MenuTest-style)
    MenuBar {
        id: mainMenuBar
        width: parent.width
        implicitHeight: 30
        height: implicitHeight
        z: 2000
        background: Rectangle {
            color: root.theme.surface
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 3
                color: root.theme.border
            }
        }

        // Keep menus simple and robust; backend commands are dispatched from the app.
        Menu {
            title: "File"
            MenuItem {
                text: "Open Folder..."
                onTriggered: if (root.app) root.app._openFolderDialogAtLastParent()
            }
            MenuSeparator {}
            MenuItem {
                text: "Exit"
                onTriggered: Qt.quit()
            }
        }

        Menu {
            title: "View"

            MenuItem {
                text: "Fit to Screen"
                checkable: true
                checked: root.app && root.app.backend ? root.app.backend.viewer.fitMode : true
                onTriggered: {
                    if (!root.app || !root.app.backend) return
                    root.app.backend.dispatch("setFitMode", { value: true })
                }
            }

            MenuItem {
                text: "Actual Size"
                checkable: true
                checked: root.app && root.app.backend ? !root.app.backend.viewer.fitMode : false
                onTriggered: {
                    if (!root.app || !root.app.backend) return
                    root.app.backend.dispatch("setZoom", { value: 1.0 })
                }
            }

            MenuItem {
                text: "High Quality Downscale (Slow)"
                checkable: true
                enabled: root.app && root.app.backend ? !root.app.backend.settings.fastViewEnabled : true
                checked: root.app ? root.app.hqDownscaleEnabled : false
                onToggled: if (root.app) root.app.hqDownscaleEnabled = checked
            }

            MenuItem {
                text: "Fast View"
                checkable: true
                checked: root.app && root.app.backend ? root.app.backend.settings.fastViewEnabled : false
                onToggled: {
                    if (!root.app || !root.app.backend) return
                    root.app.backend.dispatch("setFastViewEnabled", { value: checked })
                }
            }

            MenuSeparator {}

            MenuItem {
                text: "Zoom In"
                onTriggered: if (root.app && root.app.backend) root.app.backend.dispatch("zoomBy", { factor: 1.25 })
            }
            MenuItem {
                text: "Zoom Out"
                onTriggered: if (root.app && root.app.backend) root.app.backend.dispatch("zoomBy", { factor: 0.8 })
            }

            MenuSeparator {}

            MenuItem {
                text: "Explorer Mode"
                checkable: true
                checked: root.app && root.app.backend ? !root.app.backend.viewer.viewMode : true
                onToggled: {
                    if (!root.app || !root.app.backend) return
                    root.app.backend.dispatch("setViewMode", { value: !checked })
                }
            }

            MenuItem {
                text: "Refresh Explorer"
                onTriggered: if (root.app && root.app.backend) root.app.backend.dispatch("refreshCurrentFolder", null)
            }
        }

        Menu {
            title: "Tools"
            MenuItem {
                text: "Trim..."
                onTriggered: {
                    if (!root.dialogs) return
                    root.dialogs.showInfo("Trim", "Trim workflow is not migrated to QML yet.")
                }
            }
            MenuItem {
                text: "Convert to WebP..."
                onTriggered: if (root.dialogs) root.dialogs.openWebPDialog()
            }
        }

        Menu {
            title: "Settings"
            MenuItem {
                text: "Preferences..."
                onTriggered: {
                    if (!root.dialogs) return
                    root.dialogs.showInfo("Preferences", "Preferences UI is not migrated to QML yet.")
                }
            }
        }
    }

    ToolBar {
        id: mainToolBar
        width: root.app ? root.app.width : 0
        background: Rectangle {
            color: root.theme.surface
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: root.theme.border
            }
        }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            spacing: 8

            ToolButton {
                id: openFolderBtn
                text: "Open Folder"
                contentItem: Label {
                    text: openFolderBtn.text
                    font: openFolderBtn.font
                    color: root.theme.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: if (root.app) root.app._openFolderDialogAtLastParent()
            }

            Item { Layout.fillWidth: true }

            Label {
                color: root.theme.text
                font.bold: true
                text: {
                    if (!root.app || !root.app.backend) return ""
                    var files = root.app.backend.explorer ? root.app.backend.explorer.imageFiles : null
                    var total = files ? files.length : 0
                    var idx = root.app.backend.explorer ? root.app.backend.explorer.currentIndex : -1
                    if (total <= 0) return "No folder"
                    return (idx + 1) + " / " + total
                }
            }

            ToolButton {
                id: toggleViewBtn
                text: root.app && root.app.backend && root.app.backend.viewer.viewMode ? "Back" : "View"
                enabled: root.app && root.app.backend && (root.app.backend.explorer.imageFiles && root.app.backend.explorer.imageFiles.length > 0)
                contentItem: Label {
                    text: toggleViewBtn.text
                    font: toggleViewBtn.font
                    color: toggleViewBtn.enabled ? root.theme.text : root.theme.textDim
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: {
                    if (!root.app || !root.app.backend) return
                    root.app.backend.dispatch("setViewMode", { value: !root.app.backend.viewer.viewMode })
                }
            }
        }
    }
}
