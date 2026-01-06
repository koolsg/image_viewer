pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "."

ApplicationWindow {
    id: root
    width: 1400
    height: 900
    visible: true
    title: "Image Viewer"

    property var main: null
    property string explorerSelectedPath: ""
    property bool hqDownscaleEnabled: false

    onActiveChanged: {
        if (active && !root.main?.viewMode) {
            grid.forceActiveFocus()
        }
    }


    Window {
        id: viewWindow
        title: "View"
        visibility: (!!root.main && !!root.main.viewMode) ? Window.FullScreen : Window.Hidden
        color: root.main ? root.main.backgroundColor : "#1a1a1a"

        onVisibleChanged: {
            if (root.main) root.main.qmlDebug("viewWindow.onVisibleChanged: visible=" + visible)
            if (visible) {
                viewWindow.requestActivate()
                Qt.callLater(function() {
                    viewFocus.forceActiveFocus()
                    viewerPage.forceActiveFocus()
                })
            } else {
                if (root.main) root.main.qmlDebug("viewWindow.onVisibleChanged: hiding, restoring main focus")
                root.requestActivate()
                root.raise()
                Qt.callLater(function() {
                    root.requestActivate()
                    if (grid) {
                        grid.forceActiveFocus()
                    }
                })
            }
        }

        onClosing: function(close) {
            if (root.main) root.main.qmlDebug("viewWindow.onClosing requested")
            if (root.main) root.main.closeView()
            close.accepted = false
        }





        DeleteConfirmationDialog {
            id: viewDeleteDialog
            theme: "dark"
        }

        function showViewDeleteDialog(path) {
            viewDeleteDialog.titleText = "Delete File"
            viewDeleteDialog.infoText = (path ? (path.replace(/^.*[\\/]/, "") + "\n\nIt will be moved to Recycle Bin.") : "")
            viewDeleteDialog.payload = (typeof path === 'undefined') ? null : path
            viewDeleteDialog.open()
        }

        FocusScope {
            id: viewFocus
            anchors.fill: parent
            focus: true

            ViewerPage {
                id: viewerPage
                anchors.fill: parent
                main: root.main
                backgroundColor: root.main ? root.main.backgroundColor : "#1a1a1a"
                hqDownscaleEnabled: root.hqDownscaleEnabled
            }
        }
    }

    menuBar: MenuBar {
        Menu {
            title: "&File"
            MenuItem {
                text: "Open Folder..."
                onTriggered: if (root.main) root.main.openFolder()
            }
            MenuSeparator {}
            MenuItem {
                text: "Exit"
                onTriggered: Qt.quit()
            }
        }

        Menu {
            title: "&View"

            MenuItem {
                text: "Fit to Screen"
                checkable: true
                checked: root.main ? root.main.fitMode : true
                onTriggered: {
                    if (!root.main) return
                    root.main.fitMode = true
                }
            }

            MenuItem {
                text: "Actual Size"
                checkable: true
                checked: root.main ? !root.main.fitMode : false
                onTriggered: {
                    if (!root.main) return
                    root.main.fitMode = false
                    root.main.zoom = 1.0
                }
            }

            MenuItem {
                text: "High Quality Downscale (Slow)"
                checkable: true
                enabled: root.main ? !root.main.fastViewEnabled : true
                checked: root.hqDownscaleEnabled
                onToggled: root.hqDownscaleEnabled = checked
            }

            MenuItem {
                text: "Fast View"
                checkable: true
                checked: root.main ? root.main.fastViewEnabled : false
                onToggled: {
                    if (!root.main) return
                    root.main.fastViewEnabled = checked
                }
            }

            Menu {
                title: "Background"
                MenuItem {
                    text: "Black"
                    checkable: true
                    checked: root.main ? root.main.backgroundColor === "#000000" : false
                    onTriggered: if (root.main) root.main.backgroundColor = "#000000"
                }
                MenuItem {
                    text: "White"
                    checkable: true
                    checked: root.main ? root.main.backgroundColor === "#ffffff" : false
                    onTriggered: if (root.main) root.main.backgroundColor = "#ffffff"
                }
                MenuItem {
                    text: "Custom..."
                    onTriggered: bgColorDialog.open()
                }
            }

            MenuSeparator {}

            MenuItem {
                text: "Zoom In"
                onTriggered: if (root.main) root.main.zoom = (root.main.zoom || 1.0) * 1.25
            }
            MenuItem {
                text: "Zoom Out"
                onTriggered: if (root.main) root.main.zoom = (root.main.zoom || 1.0) / 1.25
            }

            MenuSeparator {}

            MenuItem {
                text: "Explorer Mode"
                checkable: true
                checked: root.main ? !root.main.viewMode : true
                onToggled: {
                    if (!root.main) return
                    root.main.viewMode = !checked
                }
            }

            MenuItem {
                text: "Refresh Explorer"
                onTriggered: if (root.main) root.main.refreshCurrentFolder()
            }
        }

        Menu {
            title: "Tools"
            MenuItem {
                text: "Trim..."
                onTriggered: {
                    infoDialog.title = "Trim"
                    infoDialog.text = "Trim workflow is not migrated to QML yet."
                    infoDialog.open()
                }
            }
            MenuItem {
                text: "Convert to WebP..."
                onTriggered: {
                    webpDialog.open()
                }
            }
        }

        Menu {
            title: "&Settings"
            MenuItem {
                text: "Preferences..."
                onTriggered: {
                    infoDialog.title = "Preferences"
                    infoDialog.text = "Preferences UI is not migrated to QML yet."
                    infoDialog.open()
                }
            }
        }
    }

    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            spacing: 8

            ToolButton {
                text: "Open Folder"
                onClicked: folderDialog.open()
            }

            Item { Layout.fillWidth: true }

            Label {
                text: {
                    if (!root.main) return ""
                    var total = root.main.imageFiles ? root.main.imageFiles.length : 0
                    var idx = root.main.currentIndex
                    if (total <= 0) return "No folder"
                    return (idx + 1) + " / " + total
                }
            }

            ToolButton {
                text: root.main && root.main.viewMode ? "Back" : "View"
                enabled: root.main && (root.main.imageFiles && root.main.imageFiles.length > 0)
                onClicked: {
                    if (!root.main) return
                    root.main.viewMode = !root.main.viewMode
                }
            }
        }
    }

    FolderDialog {
        id: folderDialog
        title: "Choose a folder"
        onAccepted: {
            if (!root.main) return

            root.main.openFolder(folderDialog.selectedFolder.toString())
        }
    }

    ConvertWebPDialog {
        id: webpDialog
        main: root.main
    }

    ColorDialog {
        id: bgColorDialog
        title: "Choose background color"
        onAccepted: {
            if (!root.main) return

            root.main.setBackgroundColor(bgColorDialog.selectedColor)
        }
    }

    MessageDialog {
        id: infoDialog
        title: "Info"
        text: ""
    }


    DeleteConfirmationDialog {
        id: deleteDialog
        theme: "dark"
    }

    function showDeleteDialog(title, text, info, payload) {
        deleteDialog.titleText = title
        deleteDialog.infoText = info
        deleteDialog.payload = (typeof payload === 'undefined') ? null : payload
        deleteDialog.open()
    }

    Dialog {
        id: renameDialog
        modal: true
        title: "Rename"
        standardButtons: Dialog.Ok | Dialog.Cancel
        property string oldPath: ""

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 10

            Label { text: "New name:"; color: "white" }
            TextField {
                id: renameField
                Layout.fillWidth: true
                selectByMouse: true
                focus: true
            }
        }

        onOpened: {
            renameField.forceActiveFocus()
            renameField.selectAll()
        }

        onAccepted: {
            if (!root.main) return
            if (!oldPath) return
            root.main.renameFile(oldPath, renameField.text)
        }
    }


    Component.onCompleted: {
        deleteDialog.acceptedWithPayload.connect(function(p) {
            if (root.main && typeof root.main.performDelete === 'function') {
                root.main.performDelete(p)
            }
        })

        viewDeleteDialog.acceptedWithPayload.connect(function(p) {
            if (root.main && typeof root.main.performDelete === 'function') {
                root.main.performDelete(p)
            }
        })


        Qt.callLater(function() {
            try {
                root.showMaximized()
                root.requestActivate()
                root.raise()
            } catch (e) {
                console.log("Failed to maximize on startup: " + e)
            }
        })
    }




    FocusScope {
        id: explorerPage
        anchors.fill: parent
        focus: true

        Rectangle {
            anchors.fill: parent
            color: root.main ? root.main.backgroundColor : "#121212"

            GridView {
                id: grid
                anchors.fill: parent
                anchors.margins: 12
                property int thumbVisualWidth: root.main ? (root.main.thumbnailWidth ? root.main.thumbnailWidth : 220) : 220
                property int minHSpacing: 6
                property int computedCols: Math.max(1, Math.floor(width / (thumbVisualWidth + minHSpacing)))
                property int hSpacing: Math.max(minHSpacing, Math.floor((width - (computedCols * thumbVisualWidth)) / Math.max(1, computedCols)))
                cellWidth: thumbVisualWidth + hSpacing
                cellHeight: Math.round((thumbVisualWidth + hSpacing) * 1.2)
                clip: true
                model: root.main ? root.main.imageModel : null
                currentIndex: root.main ? root.main.currentIndex : -1
                focus: true
                activeFocusOnTab: true

                // Selection state (QML-only)
                property var selectedIndices: []
                property int lastClickedIndex: -1
                property bool selectionRectVisible: false
                property real selectionRectX: 0
                property real selectionRectY: 0
                property real selectionRectW: 0
                property real selectionRectH: 0
                property bool dragSelecting: false
                property real pressX: 0
                property real pressY: 0
                property bool selectionSyncEnabled: true

                function setSelectionTo(idx) {
                    grid.selectedIndices = (idx >= 0) ? [idx] : []
                    grid.lastClickedIndex = idx
                    root.main.currentIndex = idx
                    if (idx >= 0 && root.main && root.main.imageFiles && idx < root.main.imageFiles.length) {
                        root.explorerSelectedPath = root.main.imageFiles[idx]
                    }
                }

                function setCurrentIndexOnly(idx) {
                    root.main.currentIndex = idx
                    if (idx >= 0 && root.main && root.main.imageFiles && idx < root.main.imageFiles.length) {
                        root.explorerSelectedPath = root.main.imageFiles[idx]
                    }
                }

                onCurrentIndexChanged: {
                    if (grid.dragSelecting || !grid.selectionSyncEnabled) return
                    if (root.main && root.main.currentIndex >= 0) {
                        grid.selectedIndices = [root.main.currentIndex]
                        grid.lastClickedIndex = root.main.currentIndex
                    }
                }

                // Overlay mouse area: any drag starts selection and disables scrolling
                MouseArea {
                    id: selectionMouse
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton
                    hoverEnabled: true

                    onPressed: function(mouse) {
                        // capture start (content coordinates)
                        grid.dragSelecting = false
                        grid.selectionRectVisible = true
                        grid.pressX = mouse.x
                        grid.pressY = mouse.y
                        grid.selectionRectX = mouse.x + grid.contentX
                        grid.selectionRectY = mouse.y + grid.contentY
                        grid.selectionRectW = 0
                        grid.selectionRectH = 0

                        // block GridView scrolling while dragging selection
                        grid.interactive = false

                        // prepare selection behavior: clear unless ctrl/shift held
                        if (!(mouse.modifiers & Qt.ControlModifier) && !(mouse.modifiers & Qt.ShiftModifier)) {
                            grid.selectedIndices = []
                        }
                    }

                    onPositionChanged: function(mouse) {
                        var dx = mouse.x - grid.pressX
                        var dy = mouse.y - grid.pressY
                        // small movement -> not a dragSelect yet
                        if (!grid.dragSelecting && Math.abs(dx) + Math.abs(dy) > 6) {
                            grid.dragSelecting = true
                        }

                        if (grid.dragSelecting) {
                            var cx = mouse.x + grid.contentX
                            var cy = mouse.y + grid.contentY
                            grid.selectionRectW = cx - grid.selectionRectX
                            grid.selectionRectH = cy - grid.selectionRectY
                        }
                    }

                    onReleased: function(mouse) {
                        grid.interactive = true
                        var dx = mouse.x - grid.pressX
                        var dy = mouse.y - grid.pressY

                        if (grid.dragSelecting) {
                            // finalize rectangular selection (content coordinates)
                            grid.selectionRectVisible = false
                            grid.dragSelecting = false

                            var x1 = Math.min(grid.selectionRectX, grid.selectionRectX + grid.selectionRectW)
                            var y1 = Math.min(grid.selectionRectY, grid.selectionRectY + grid.selectionRectH)
                            var x2 = Math.max(grid.selectionRectX, grid.selectionRectX + grid.selectionRectW)
                            var y2 = Math.max(grid.selectionRectY, grid.selectionRectY + grid.selectionRectH)

                            // use cell math for reliable hit detection
                            var total = root.main ? (root.main.imageFiles ? root.main.imageFiles.length : 0) : 0
                            var cols = grid.computedCols || 1
                            var newSel = grid.selectedIndices.slice()
                            for (var i = 0; i < total; ++i) {
                                var col = i % cols
                                var row = Math.floor(i / cols)
                                var ix = col * grid.cellWidth
                                var iy = row * grid.cellHeight
                                var iw = grid.cellWidth
                                var ih = grid.cellHeight

                                // check overlap
                                if (!(ix > x2 || (ix + iw) < x1 || iy > y2 || (iy + ih) < y1)) {
                                    if (newSel.indexOf(i) === -1) newSel.push(i)
                                }
                            }
                            grid.selectedIndices = newSel

                            // set currentIndex to last selected
                            if (grid.selectedIndices.length > 0) {
                                var last = grid.selectedIndices[grid.selectedIndices.length - 1]
                                grid.selectionSyncEnabled = false
                                grid.setCurrentIndexOnly(last)
                                grid.lastClickedIndex = last
                                Qt.callLater(function() { grid.selectionSyncEnabled = true })
                            }

                        } else {
                            // treat as click (no significant drag)
                            var cx = mouse.x + grid.contentX
                            var cy = mouse.y + grid.contentY
                            var cols = grid.computedCols || 1
                            var col = Math.floor(cx / grid.cellWidth)
                            var row = Math.floor(cy / grid.cellHeight)
                            if (col < 0 || row < 0) {
                                // click on empty area -> clear selection unless modifiers held
                                if (!(mouse.modifiers & Qt.ControlModifier) && !(mouse.modifiers & Qt.ShiftModifier)) {
                                    grid.selectedIndices = []
                                    root.main.currentIndex = -1
                                    root.explorerSelectedPath = ""
                                }
                            } else {
                                var idx = row * cols + col
                                var total = root.main ? (root.main.imageFiles ? root.main.imageFiles.length : 0) : 0
                                if (idx >= 0 && idx < total) {
                                    if (mouse.modifiers & Qt.ShiftModifier && grid.lastClickedIndex >= 0) {
                                        var a = Math.min(grid.lastClickedIndex, idx)
                                        var b = Math.max(grid.lastClickedIndex, idx)
                                        var newSel = grid.selectedIndices.slice()
                                        for (var i = a; i <= b; ++i) {
                                            if (newSel.indexOf(i) === -1) newSel.push(i)
                                        }
                                        grid.selectedIndices = newSel
                                        grid.lastClickedIndex = idx
                                        grid.selectionSyncEnabled = false
                                        grid.setCurrentIndexOnly(idx)
                                        Qt.callLater(function() { grid.selectionSyncEnabled = true })
                                        grid.positionViewAtIndex(idx, GridView.Visible)
                                    } else if (mouse.modifiers & Qt.ControlModifier) {
                                        var newSel = grid.selectedIndices.slice()
                                        var p = newSel.indexOf(idx)
                                        if (p === -1) newSel.push(idx)
                                        else newSel.splice(p, 1)
                                        grid.selectedIndices = newSel
                                        grid.lastClickedIndex = idx
                                        grid.selectionSyncEnabled = false
                                        grid.setCurrentIndexOnly(idx)
                                        Qt.callLater(function() { grid.selectionSyncEnabled = true })
                                        grid.positionViewAtIndex(idx, GridView.Visible)
                                    } else {
                                        grid.setSelectionTo(idx)
                                        grid.selectionRectVisible = false
                                        return
                                    }
                                }
                            }
                        }

                        grid.forceActiveFocus()
                        grid.selectionRectVisible = false
                    }
                }

                // visual selection rect (content coords -> view coords)
                Rectangle {
                    visible: grid.selectionRectVisible
                    color: "#4a8ad4"
                    opacity: 0.25
                    border.color: "#4a8ad4"
                    border.width: 1
                    x: grid.selectionRectX - grid.contentX
                    y: grid.selectionRectY - grid.contentY
                    width: Math.abs(grid.selectionRectW)
                    height: Math.abs(grid.selectionRectH)
                    z: 100
                }

                Keys.onPressed: function(event) {
                    if (!root.main) return

                    var total = root.main.imageFiles ? root.main.imageFiles.length : 0
                    var idx = (root.main.currentIndex >= 0) ? root.main.currentIndex : 0
                    var cols = grid.computedCols || 1

                    // Arrow key navigation within the grid
                    if (event.key === Qt.Key_Left) {
                        if (idx > 0) {
                            idx = Math.max(0, idx - 1)
                            grid.setSelectionTo(idx)
                            grid.positionViewAtIndex(idx, GridView.Visible)
                        }
                        event.accepted = true
                        return
                    }

                    if (event.key === Qt.Key_Right) {
                        if (idx < total - 1) {
                            idx = Math.min(total - 1, idx + 1)
                            grid.setSelectionTo(idx)
                            grid.positionViewAtIndex(idx, GridView.Visible)
                        }
                        event.accepted = true
                        return
                    }

                    if (event.key === Qt.Key_Up) {
                        if (idx > 0) {
                            idx = Math.max(0, idx - cols)
                            grid.setSelectionTo(idx)
                            grid.positionViewAtIndex(idx, GridView.Visible)
                        }
                        event.accepted = true
                        return
                    }

                    if (event.key === Qt.Key_Down) {
                        if (idx < total - 1) {
                            idx = Math.min(total - 1, idx + cols)
                            grid.setSelectionTo(idx)
                            grid.positionViewAtIndex(idx, GridView.Visible)
                        }
                        event.accepted = true
                        return
                    }

                    // Enter opens viewer for the current selection
                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        if (root.main.currentIndex >= 0) {
                            root.explorerSelectedPath = (root.main.imageFiles && root.main.currentIndex < root.main.imageFiles.length)
                                ? root.main.imageFiles[root.main.currentIndex]
                                : root.explorerSelectedPath
                            root.main.viewMode = true
                        }
                        event.accepted = true
                    }
                }



                delegate: Item {
                    id: delegateRoot
                    required property int index
                    required property string path
                    required property string name
                    required property string sizeText
                    required property string mtimeText
                    required property string resolutionText
                    required property string thumbUrl

                    width: grid.cellWidth
                    height: grid.cellHeight

                    Rectangle {
                        id: card

                        width: grid.thumbVisualWidth
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.top: parent.top
                        anchors.topMargin: 6
                        anchors.bottomMargin: 6
                        height: parent.height - 12
                        radius: 8
                        color: (grid.selectedIndices.indexOf(delegateRoot.index) !== -1) ? "#2a3b52" : "#1a1a1a"
                        border.color: (grid.selectedIndices.indexOf(delegateRoot.index) !== -1) ? "#6aa9ff" : "#2a2a2a"
                        border.width: 1

                        ToolTip.visible: false
                        ToolTip.delay: 300
                        ToolTip.text: [delegateRoot.name, [delegateRoot.resolutionText, delegateRoot.sizeText].filter(Boolean).join(" | ")].filter(Boolean).join("\n")

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 6

                            Rectangle {
                                Layout.fillWidth: true


                                Layout.preferredHeight: Math.round(grid.thumbVisualWidth * 0.76)
                                radius: 6
                                color: "#0f0f0f"

                                Image {
                                    id: thumb
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    fillMode: Image.PreserveAspectFit
                                    asynchronous: true
                                    cache: false
                                    smooth: true
                                    mipmap: true
                                    source: delegateRoot.thumbUrl
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                color: "white"
                                text: delegateRoot.name
                                wrapMode: Text.Wrap
                                font.pixelSize: 13
                            }
                            Text {
                                Layout.fillWidth: true
                                color: "#b0b0b0"
                                font.pixelSize: 11
                                text: [ (delegateRoot.name && delegateRoot.name.indexOf('.') !== -1) ? delegateRoot.name.split('.').pop().toUpperCase() : null, delegateRoot.resolutionText, delegateRoot.sizeText ].filter(Boolean).join(" | ")
                            }
                            Label {
                                Layout.fillWidth: true
                                color: "#7f7f7f"
                                font.pixelSize: 10
                                text: delegateRoot.mtimeText
                                elide: Text.ElideRight
                            }

                            Item { Layout.fillHeight: true }
                        }

                        Menu {
                            id: ctxMenu
                            MenuItem {
                                text: "Open"
                                onTriggered: {
                                    if (!root.main) return
                                    root.main.currentIndex = delegateRoot.index
                                    root.main.viewMode = true
                                }
                            }
                            MenuSeparator {}
                            MenuItem {
                                text: "Copy"
                                onTriggered: if (root.main) root.main.copyFiles(delegateRoot.path)
                            }
                            MenuItem {
                                text: "Cut"
                                onTriggered: if (root.main) root.main.cutFiles(delegateRoot.path)
                            }
                            MenuItem {
                                text: "Paste"
                                enabled: root.main && root.main.clipboardHasFiles
                                onTriggered: if (root.main) root.main.pasteFiles()
                            }
                            MenuItem {
                                text: "Rename"
                                onTriggered: {
                                    renameDialog.oldPath = delegateRoot.path
                                    renameField.text = delegateRoot.name
                                    renameDialog.open()
                                }
                            }
                            MenuItem {
                                text: "Delete"
                                onTriggered: {
                                    root.showDeleteDialog(
                                        "Delete File",
                                        "Delete this file?",
                                        delegateRoot.name + "\n\nIt will be moved to Recycle Bin.",
                                        delegateRoot.path
                                    )
                                }
                            }
                            MenuSeparator {}
                            MenuItem {
                                text: "Copy path"
                                onTriggered: if (root.main) root.main.copyText(delegateRoot.path)
                            }
                            MenuItem {
                                text: "Reveal in Explorer"
                                onTriggered: if (root.main) root.main.revealInExplorer(delegateRoot.path)
                            }
                        }


                    }
                }
            }
        }
    }
}
