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
    title: "Image Viewer (QML)"

    // Set from Python via rootObject().setProperty("main", ...)
    property var main: null

    // Track explorer selection for shortcuts/actions (avoid relying on GridView.currentItem typing).
    property string explorerSelectedPath: ""

    // Viewer-only rendering toggle (QML equivalent of legacy "HQ downscale" checkbox).
    // In the QML renderer this maps to mipmap sampling, not pyvips downscaling.
    property bool hqDownscaleEnabled: false

    // When main window becomes active again, restore focus to grid.
    onActiveChanged: {
        if (active && !root.main?.viewMode) {
            grid.forceActiveFocus()
        }
    }

    Action {
        id: actionOpenFolder
        text: "Open Folder..."
        shortcut: StandardKey.Open
        onTriggered: folderDialog.open()
    }

    Action {
        id: actionExit
        text: "Exit"
        shortcut: "Alt+F4"
        onTriggered: Qt.quit()
    }

    Action {
        id: actionZoomIn
        text: "Zoom In"
        shortcut: StandardKey.ZoomIn
        onTriggered: {
            if (!root.main) return
            root.main.fitMode = false
            root.main.zoom = Math.max(0.05, Math.min(20.0, root.main.zoom * 1.25))
        }
    }

    Action {
        id: actionZoomOut
        text: "Zoom Out"
        shortcut: StandardKey.ZoomOut
        onTriggered: {
            if (!root.main) return
            root.main.fitMode = false
            root.main.zoom = Math.max(0.05, Math.min(20.0, root.main.zoom * 0.75))
        }
    }

    Action {
        id: actionRefreshExplorer
        text: "Refresh Explorer"
        shortcut: "F5"
        onTriggered: if (root.main) root.main.refreshCurrentFolder()
    }

    // Separate fullscreen viewer window (always fullscreen when opened).
    Window {
        id: viewWindow
        title: "View"
        // IMPORTANT: do not assign to `visibility` from handlers, or the binding will be broken
        // and Python's closeView() (which flips main.viewMode) won't be able to hide this window.
        visibility: (!!root.main && !!root.main.viewMode) ? Window.FullScreen : Window.Hidden
        color: root.main ? root.main.backgroundColor : "#1a1a1a"

        onVisibleChanged: {
            if (visible) {
                // Request window activation and focus.
                viewWindow.requestActivate()
                Qt.callLater(function() {
                    viewFocus.forceActiveFocus()
                    viewerPage.forceActiveFocus()
                })
            } else {
                // When hiding view window, activate main window and restore focus to grid.
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
            // Keep backend state as the source of truth.
            if (root.main) root.main.closeView()
            // Prevent double-close races; backend will flip viewMode which hides this window.
            close.accepted = false
        }

        // Viewer-only shortcuts live on the viewer window so they work reliably
        // even when the ApplicationWindow is not the active window.
        Shortcut {
            // Try both spellings; Qt docs and examples commonly use "Escape".
            sequences: ["Escape", "Esc"]
            context: Qt.WindowShortcut
            enabled: !!root.main && !!root.main.viewMode
            onActivated: {
                if (!root.main) return
                root.main.qmlDebug("viewWindow Shortcut activated: Escape")
                root.main.closeView()
            }
        }
        Shortcut {
            sequences: ["Return", "Enter"]
            context: Qt.WindowShortcut
            enabled: !!root.main && !!root.main.viewMode
            onActivated: {
                if (!root.main) return
                root.main.qmlDebug("viewWindow Shortcut activated: Return/Enter")
                root.main.closeView()
            }
        }
        Shortcut {
            sequence: "Left"
            context: Qt.WindowShortcut
            onActivated: if (root.main) root.main.prevImage()
        }
        Shortcut {
            sequence: "Right"
            context: Qt.WindowShortcut
            onActivated: if (root.main) root.main.nextImage()
        }
        Shortcut {
            sequence: "Home"
            context: Qt.WindowShortcut
            onActivated: if (root.main) root.main.firstImage()
        }
        Shortcut {
            sequence: "End"
            context: Qt.WindowShortcut
            onActivated: if (root.main) root.main.lastImage()
        }

        // Legacy parity: space snaps to global view (fit).
        Shortcut {
            sequence: "Space"
            context: Qt.WindowShortcut
            onActivated: viewerPage.snapToGlobalView()
        }

        // Legacy parity: up/down zoom.
        Shortcut {
            sequence: "Up"
            context: Qt.WindowShortcut
            onActivated: viewerPage.zoomBy(1.25)
        }
        Shortcut {
            sequence: "Down"
            context: Qt.WindowShortcut
            onActivated: viewerPage.zoomBy(0.75)
        }

        // Also support standard zoom keys in the viewer window (Ctrl+= / Ctrl+-).
        Shortcut {
            sequences: [ StandardKey.ZoomIn ]
            context: Qt.WindowShortcut
            onActivated: viewerPage.zoomBy(1.25)
        }
        Shortcut {
            sequences: [ StandardKey.ZoomOut ]
            context: Qt.WindowShortcut
            onActivated: viewerPage.zoomBy(0.75)
        }
        Shortcut {
            sequence: "F"
            context: Qt.WindowShortcut
            onActivated: viewerPage.snapToGlobalView()
        }
        Shortcut {
            sequence: "1"
            context: Qt.WindowShortcut
            onActivated: {
                if (!root.main) return
                root.main.fitMode = false
                root.main.zoom = 1.0
            }
        }
        Shortcut {
            sequences: [ StandardKey.Copy ]
            context: Qt.WindowShortcut
            onActivated: {
                if (!root.main) return
                if (root.main.currentPath) root.main.copyText(root.main.currentPath)
            }
        }

        // Delete in view mode (with confirmation).
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

        Shortcut {
            sequence: "Delete"
            context: Qt.WindowShortcut
            onActivated: {
                if (!root.main) return
                var p = root.main.currentPath
                if (!p) return
                viewWindow.showViewDeleteDialog(p)
            }
        }

        // Fallback key handling: even if Shortcuts don't trigger (IME/focus quirks),
        // make sure the user can always exit view mode.
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
            MenuItem { action: actionOpenFolder }
            MenuSeparator {}
            MenuItem { action: actionExit }
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

            MenuItem { action: actionZoomIn }
            MenuItem { action: actionZoomOut }

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
                action: actionRefreshExplorer
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
            // Pass URL string; Python normalizes file:// URLs to local paths.
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
            // QML passes a QColor; Python converts & persists.
            root.main.setBackgroundColor(bgColorDialog.selectedColor)
        }
    }

    MessageDialog {
        id: infoDialog
        title: "Info"
        text: ""
    }

    // Delete confirmation dialog implemented in QML (replacement for DeleteConfirmationDialog)
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

    // Forward dialog acceptance to Python Main which will perform deletion
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
    }

    // --- Global shortcuts ---
    Shortcut {
        sequences: [ StandardKey.Open ]
        context: Qt.ApplicationShortcut
        onActivated: folderDialog.open()
    }

    Shortcut {
        sequence: "Ctrl+,"
        context: Qt.ApplicationShortcut
        onActivated: {
            infoDialog.title = "Preferences"
            infoDialog.text = "Preferences UI is not migrated to QML yet."
            infoDialog.open()
        }
    }
    Shortcut {
        sequences: [ StandardKey.Copy ]
        context: Qt.ApplicationShortcut
        onActivated: {
            if (!root.main) return
            // Explorer-only: viewer copy is handled by the view window.
            if (root.main.viewMode) return
            var p = root.explorerSelectedPath
            if (p) root.main.copyFiles(p)
        }
    }

    Shortcut {
        sequences: [ StandardKey.Cut ]
        context: Qt.ApplicationShortcut
        onActivated: {
            if (!root.main) return
            if (root.main.viewMode) return
            var p = root.explorerSelectedPath
            if (p) root.main.cutFiles(p)
        }
    }

    Shortcut {
        sequences: [ StandardKey.Paste ]
        context: Qt.ApplicationShortcut
        onActivated: {
            if (!root.main) return
            if (root.main.viewMode) return
            root.main.pasteFiles()
        }
    }

    Shortcut {
        sequence: "Delete"
        context: Qt.ApplicationShortcut
        onActivated: {
            if (!root.main) return
            if (root.main.viewMode) return
            var p = root.explorerSelectedPath
            if (!p) return
            root.showDeleteDialog("Delete File", "Delete this file?", p + "\n\nIt will be moved to Recycle Bin.", p)
        }
    }

    Shortcut {
        sequence: "F2"
        context: Qt.ApplicationShortcut
        onActivated: {
            if (!root.main) return
            if (root.main.viewMode) return
            var p = root.explorerSelectedPath
            if (!p) return
            renameDialog.oldPath = p
            // Prefill with current basename
            renameField.text = p.replace(/^.*[\\/]/, "")
            renameDialog.open()
        }
    }

    // Explorer (Grid) is always shown in the main window.
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
                cellWidth: 220
                cellHeight: 270
                clip: true
                model: root.main ? root.main.imageModel : null
                currentIndex: root.main ? root.main.currentIndex : -1
                focus: true
                activeFocusOnTab: true

                Keys.onPressed: function(event) {
                    if (!root.main) return
                    if (root.main.viewMode) return

                    function updateSelection(newIdx) {
                        if (newIdx < 0 || newIdx === root.main.currentIndex) return
                        // Only update main.currentIndex; grid.currentIndex follows via binding.
                        root.main.currentIndex = newIdx
                        if (root.main.imageFiles && newIdx >= 0 && newIdx < root.main.imageFiles.length) {
                            root.explorerSelectedPath = root.main.imageFiles[newIdx]
                        }
                    }

                    var cols = Math.max(1, Math.floor(grid.width / grid.cellWidth))
                    if (event.key === Qt.Key_Right) {
                        updateSelection(Math.min(grid.count - 1, root.main.currentIndex + 1))
                        event.accepted = true
                    } else if (event.key === Qt.Key_Left) {
                        updateSelection(Math.max(0, root.main.currentIndex - 1))
                        event.accepted = true
                    } else if (event.key === Qt.Key_Down) {
                        updateSelection(Math.min(grid.count - 1, root.main.currentIndex + cols))
                        event.accepted = true
                    } else if (event.key === Qt.Key_Up) {
                        updateSelection(Math.max(0, root.main.currentIndex - cols))
                        event.accepted = true
                    } else if (event.key === Qt.Key_Home) {
                        updateSelection(0)
                        event.accepted = true
                    } else if (event.key === Qt.Key_End) {
                        updateSelection(Math.max(0, grid.count - 1))
                        event.accepted = true
                    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        if (root.main.currentIndex >= 0) {
                            root.explorerSelectedPath = (root.main.imageFiles && root.main.currentIndex < root.main.imageFiles.length)
                                ? root.main.imageFiles[root.main.currentIndex]
                                : root.explorerSelectedPath
                            root.main.viewMode = true
                            event.accepted = true
                        }
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
                        anchors.fill: parent
                        anchors.margins: 6
                        radius: 8
                        color: (delegateRoot.index === grid.currentIndex) ? "#2a3b52" : "#1a1a1a"
                        border.color: (delegateRoot.index === grid.currentIndex) ? "#6aa9ff" : "#2a2a2a"
                        border.width: 1

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 6

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 160
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

                            Label {
                                Layout.fillWidth: true
                                color: "white"
                                text: delegateRoot.name
                                elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                color: "#b0b0b0"
                                font.pixelSize: 11
                                text: [delegateRoot.resolutionText, delegateRoot.sizeText].filter(Boolean).join(" | ")
                                elide: Text.ElideRight
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

                        MouseArea {
                            anchors.fill: parent
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onClicked: function(mouse) {
                                if (!root.main) return
                                root.main.currentIndex = delegateRoot.index
                                root.explorerSelectedPath = delegateRoot.path
                                if (mouse.button === Qt.RightButton) {
                                    ctxMenu.popup()
                                } else {
                                    // Single click selects; double click opens.
                                }
                            }
                            onDoubleClicked: {
                                if (!root.main) return
                                root.main.currentIndex = delegateRoot.index
                                root.explorerSelectedPath = delegateRoot.path
                                root.main.viewMode = true
                            }
                        }
                    }
                }
            }
        }
    }
}
