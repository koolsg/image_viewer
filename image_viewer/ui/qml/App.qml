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
    flags: Qt.Window | Qt.FramelessWindowHint

    // Python sets this immediately after loading the QML root.
    // Use `root.backend` (not the unqualified context name) to satisfy
    // `pragma ComponentBehavior: Bound` rules.
    property var backend: null

    property string explorerSelectedPath: ""
    property bool hqDownscaleEnabled: false

    Theme {
        id: theme
    }

    function qmlDebugSafe(msg) {
        // backend is injected as a context property before QML loads.
        try {
            if (root.backend) {
                root.backend.dispatch("log", { level: "debug", message: String(msg) })
                return
            }
        } catch (e) {
            // fall back to console if Python call fails
        }
        console.log(String(msg))
    }

    onActiveChanged: {
        if (active && root.backend && !root.backend.viewer.viewMode) {
            grid.forceActiveFocus()
        }
        if (active) root.qmlDebugSafe("Application active change: active=" + active)
    }

    function _openFolderDialogAtLastParent() {
        // Start the FolderDialog at the parent directory of the last opened folder.
        // QtQuick.Dialogs expects a file:/// URL.
        var base = (root.backend && root.backend.explorer && root.backend.explorer.currentFolder)
            ? ("" + root.backend.explorer.currentFolder)
            : "";
        if (!base) {
            folderDialog.open();
            return;
        }

        // Avoid regex literals here; qmllint can be picky about escapes.
        var p = base.split("\\").join("/");
        // trim trailing slashes
        while (p.length > 3 && p.endsWith("/")) p = p.slice(0, -1);
        var lastSlash = p.lastIndexOf("/");
        var parent = (lastSlash > 0) ? p.slice(0, lastSlash) : p;
        if (parent.endsWith(":")) parent = parent + "/";

        folderDialog.currentFolder = "file:///" + parent;
        folderDialog.open();
    }


    Window {
        id: viewWindow
        title: "View"
        visibility: (root.backend && root.backend.viewer && root.backend.viewer.viewMode) ? Window.FullScreen : Window.Hidden
        color: (root.backend && root.backend.settings) ? root.backend.settings.backgroundColor : theme.background

        onVisibleChanged: {
            root.qmlDebugSafe("viewWindow.onVisibleChanged: visible=" + visible)
            if (visible) {
                viewWindow.requestActivate()
                Qt.callLater(function() {
                    viewFocus.forceActiveFocus()
                    viewerPage.forceActiveFocus()
                })
            } else {
                root.qmlDebugSafe("viewWindow.onVisibleChanged: hiding, restoring main focus")
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
            root.qmlDebugSafe("viewWindow.onClosing requested")
            if (root.backend) root.backend.dispatch("closeView", null)
            close.accepted = false
        }





        DeleteConfirmationDialog {
            id: viewDeleteDialog
            theme: theme
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
                backend: root.backend
                theme: theme
                backgroundColor: (root.backend && root.backend.settings) ? root.backend.settings.backgroundColor : theme.background
                hqDownscaleEnabled: root.hqDownscaleEnabled
            }
        }
    }



    FolderDialog {
        id: folderDialog
        title: "Choose a folder"
        onAccepted: {
            if (!root.backend) return
            root.backend.dispatch("openFolder", { path: folderDialog.selectedFolder.toString() })
        }
    }

    ConvertWebPDialog {
        id: webpDialog
        backend: root.backend
        theme: theme
    }

    ColorDialog {
        id: bgColorDialog
        title: "Choose background color"
        onAccepted: {
            if (!root.backend) return
            root.backend.dispatch("setBackgroundColor", { color: bgColorDialog.selectedColor })
        }
    }

    MessageDialog {
        id: infoDialog
        title: "Info"
        text: ""
    }


    DeleteConfirmationDialog {
        id: deleteDialog
        theme: theme
    }

    function showDeleteDialog(title, text, info, payload) {
        deleteDialog.titleText = title
        deleteDialog.infoText = info
        deleteDialog.payload = (typeof payload === 'undefined') ? null : payload
        deleteDialog.open()
    }

    Dialog {
        id: renameDialog
        parent: root.contentItem
        modal: true
        focus: true
        title: "Rename"
        standardButtons: Dialog.Ok | Dialog.Cancel
        property string oldPath: ""
        property string initialName: ""  // Store the initial filename to populate

        // Keep the dialog centered (avoids "top-left corner" placement issues)
        x: Math.round(((parent ? parent.width : root.width) - width) / 2)
        y: Math.round(((parent ? parent.height : root.height) - height) / 2)

        //implicitHeight: 170

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 10

            // Top spacer ensures content sits below title bar regardless of platform
            //Item { Layout.preferredHeight: 20 }

            TextField {
                id: renameField
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                selectByMouse: true
                focus: true
                text: renameDialog.initialName  // Bind text to dialog property

                padding: 8
                font.pixelSize: 14

                color: theme.text
                selectionColor: theme.accent
                selectedTextColor: theme.surface
                cursorDelegate: Rectangle {
                    width: 1
                    color: theme.accent
                }
                background: Rectangle {
                    radius: theme.radiusSmall
                    color: theme.hover
                    border.color: theme.border
                    border.width: 1
                    implicitHeight: 36
                }

                Keys.onReturnPressed: function(event) {
                    // Pressing Enter confirms the rename (same as clicking OK)
                    renameDialog.accept()
                    event.accepted = true
                }
            }
        }

        onOpened: {
            // Focus + select full filename (including extension), Windows-style.
            renameDialog.forceActiveFocus()
            renameField.forceActiveFocus()
            Qt.callLater(function() { renameField.selectAll() })
        }

        onAccepted: {
            if (!root.backend) return
            if (!oldPath) return
            root.backend.dispatch("renameFile", { path: oldPath, newName: renameField.text })
        }
    }


    Component.onCompleted: {
        deleteDialog.acceptedWithPayload.connect(function(p) {
            if (!root.backend) return
            root.backend.dispatch("deleteFiles", { paths: (Array.isArray(p) ? p : [p]) })
        })

        viewDeleteDialog.acceptedWithPayload.connect(function(p) {
            if (!root.backend) return
            root.backend.dispatch("deleteFiles", { paths: (Array.isArray(p) ? p : [p]) })
        })


        Qt.callLater(function() {
            try {
                // For frameless window, showMaximized() works but we need to ensure
                // we can still restore.
                root.show()
                root.requestActivate()
                root.raise()
            } catch (e) {
                console.log("Failed to show on startup: " + e)
            }
        })
    }

    // --- Custom Title Bar & Window Management ---

    header: Column {
        Rectangle {
            id: customTitleBar
            width: parent.width
            height: 32
            color: theme.surface
            z: 1000
            layer.enabled: true // Cache as texture to prevent jitter during window drag

            DragHandler {
                id: dragHandler
                onActiveChanged: if (active) root.startSystemMove()
            }

            TapHandler {
                acceptedButtons: Qt.LeftButton
                onDoubleTapped: {
                    if (root.visibility === Window.Maximized) {
                        root.showNormal()
                    } else {
                        root.showMaximized()
                    }
                }
            }

            Label {
                id: titleLabel
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: root.title
                color: theme.text
                font.pixelSize: 12
            }

            // Window Controls
            Row {
                id: windowControls
                anchors.right: parent.right
                height: parent.height
                spacing: 0
                z: 10 // Ensure buttons are above the title bar's background handlers

                Button {
                    id: minBtn
                    width: 46
                    height: parent.height
                    flat: true
                    hoverEnabled: true
                    background: Rectangle {
                        color: minBtn.hovered ? theme.hover : "transparent"
                    }
                    contentItem: Text {
                        text: "—"
                        color: theme.text
                        font.pixelSize: 10
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: root.showMinimized()
                }

                Button {
                    id: maxBtn
                    width: 46
                    height: parent.height
                    flat: true
                    hoverEnabled: true
                    background: Rectangle {
                        color: maxBtn.hovered ? theme.hover : "transparent"
                    }
                    contentItem: Text {
                        text: root.visibility === Window.Maximized ? "❐" : "☐"
                        color: theme.text
                        font.pixelSize: 14
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (root.visibility === Window.Maximized) {
                            root.showNormal()
                        } else {
                            root.showMaximized()
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
                        color: closeBtn.hovered ? "#E81123" : "transparent"
                    }
                    contentItem: Text {
                        text: "✕"
                        color: closeBtn.hovered ? "#FFFFFF" : theme.text
                        font.pixelSize: 14
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: Qt.quit()
                }
            }

            // Bottom Border / Separator
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 3
                color: theme.border
            }
        }

        MenuBar {
            id: mainMenuBar
            width: parent.width
            background: Rectangle {
                color: theme.surface
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 3
                    color: theme.border
                }
            }

            delegate: MenuBarItem {
                id: menuBarItem
                contentItem: Text {
                    text: menuBarItem.text
                    font: menuBarItem.font
                    color: theme.text
                    horizontalAlignment: Text.AlignLeft
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
                background: Rectangle {
                    implicitWidth: 40
                    implicitHeight: 30
                    color: menuBarItem.highlighted ? theme.hover : "transparent"
                }
            }

            Menu {
                title: "File"
                MenuItem {
                    text: "Open Folder..."
                    onTriggered: root._openFolderDialogAtLastParent()
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
                    checked: root.backend ? root.backend.viewer.fitMode : true
                    onTriggered: {
                        if (!root.backend) return
                        root.backend.dispatch("setFitMode", { value: true })
                    }
                }

                MenuItem {
                    text: "Actual Size"
                    checkable: true
                    checked: root.backend ? !root.backend.viewer.fitMode : false
                    onTriggered: {
                        if (!root.backend) return
                        root.backend.dispatch("setZoom", { value: 1.0 })
                    }
                }

                MenuItem {
                    text: "High Quality Downscale (Slow)"
                    checkable: true
                    enabled: root.backend ? !root.backend.settings.fastViewEnabled : true
                    checked: root.hqDownscaleEnabled
                    onToggled: root.hqDownscaleEnabled = checked
                }

                MenuItem {
                    text: "Fast View"
                    checkable: true
                    checked: root.backend ? root.backend.settings.fastViewEnabled : false
                    onToggled: {
                        if (!root.backend) return
                        root.backend.dispatch("setFastViewEnabled", { value: checked })
                    }
                }

                Menu {
                    title: "Background"
                    MenuItem {
                        text: "Black"
                        checkable: true
                        checked: root.backend ? root.backend.settings.backgroundColor === "#000000" : false
                        onTriggered: if (root.backend) root.backend.dispatch("setBackgroundColor", { color: "#000000" })
                    }
                    MenuItem {
                        text: "White"
                        checkable: true
                        checked: root.backend ? root.backend.settings.backgroundColor === "#ffffff" : false
                        onTriggered: if (root.backend) root.backend.dispatch("setBackgroundColor", { color: "#ffffff" })
                    }
                    MenuItem {
                        text: "Custom..."
                        onTriggered: bgColorDialog.open()
                    }
                }

                MenuSeparator {}

                MenuItem {
                    text: "Zoom In"
                    onTriggered: if (root.backend) root.backend.dispatch("zoomBy", { factor: 1.25 })
                }
                MenuItem {
                    text: "Zoom Out"
                    onTriggered: if (root.backend) root.backend.dispatch("zoomBy", { factor: 0.8 })
                }

                MenuSeparator {}

                MenuItem {
                    text: "Explorer Mode"
                    checkable: true
                    checked: root.backend ? !root.backend.viewer.viewMode : true
                    onToggled: {
                        if (!root.backend) return
                        root.backend.dispatch("setViewMode", { value: !checked })
                    }
                }

                MenuItem {
                    text: "Refresh Explorer"
                    onTriggered: if (root.backend) root.backend.dispatch("refreshCurrentFolder", null)
                }

                Menu {
                    title: "Theme"
                    MenuItem {
                        text: "Deep Dark"
                        checkable: true
                        checked: theme.currentTheme === Theme.Dark
                        onTriggered: theme.currentTheme = Theme.Dark
                    }
                    MenuItem {
                        text: "Pure Light"
                        checkable: true
                        checked: theme.currentTheme === Theme.Light
                        onTriggered: theme.currentTheme = Theme.Light
                    }
                    MenuItem {
                        text: "Sweet Pastel"
                        checkable: true
                        checked: theme.currentTheme === Theme.Pastel
                        onTriggered: theme.currentTheme = Theme.Pastel
                    }
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
                title: "Settings"
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

        ToolBar {
            id: mainToolBar
            width: parent.width
            background: Rectangle {
                color: theme.surface
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: theme.border
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
                        color: theme.text
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: root._openFolderDialogAtLastParent()
                }

                Item { Layout.fillWidth: true }

                Label {
                    color: theme.text
                    font.bold: true
                    text: {
                        if (!root.backend) return ""
                        var files = root.backend.explorer ? root.backend.explorer.imageFiles : null
                        var total = files ? files.length : 0
                        var idx = root.backend.explorer ? root.backend.explorer.currentIndex : -1
                        if (total <= 0) return "No folder"
                        return (idx + 1) + " / " + total
                    }
                }

                ToolButton {
                    id: toggleViewBtn
                    text: root.backend && root.backend.viewer.viewMode ? "Back" : "View"
                    enabled: root.backend && (root.backend.explorer.imageFiles && root.backend.explorer.imageFiles.length > 0)
                    contentItem: Label {
                        text: toggleViewBtn.text
                        font: toggleViewBtn.font
                        color: toggleViewBtn.enabled ? theme.text : theme.textDim
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!root.backend) return
                        root.backend.dispatch("setViewMode", { value: !root.backend.viewer.viewMode })
                    }
                }
            }
        }
    }

    // --- Resize Handles ---

    MouseArea {
        id: topResize
        height: 6; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
        cursorShape: Qt.SizeVerCursor
        z: 1 // Keep below header content if possible
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.TopEdge)
    }
    MouseArea {
        id: bottomResize
        height: 6; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
        cursorShape: Qt.SizeVerCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.BottomEdge)
    }
    MouseArea {
        id: leftResize
        width: 6; anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
        cursorShape: Qt.SizeHorCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.LeftEdge)
    }
    MouseArea {
        id: rightResize
        width: 6; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
        cursorShape: Qt.SizeHorCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.RightEdge)
    }
    MouseArea {
        width: 10; height: 10; anchors.left: parent.left; anchors.top: parent.top
        cursorShape: Qt.SizeFDiagCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.TopEdge | Qt.LeftEdge)
    }
    MouseArea {
        width: 10; height: 10; anchors.right: parent.right; anchors.top: parent.top
        cursorShape: Qt.SizeBDiagCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.TopEdge | Qt.RightEdge)
    }
    MouseArea {
        width: 10; height: 10; anchors.left: parent.left; anchors.bottom: parent.bottom
        cursorShape: Qt.SizeBDiagCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.BottomEdge | Qt.LeftEdge)
    }
    MouseArea {
        width: 10; height: 10; anchors.right: parent.right; anchors.bottom: parent.bottom
        cursorShape: Qt.SizeFDiagCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.BottomEdge | Qt.RightEdge)
    }

    FocusScope {
        id: explorerPage
        anchors.fill: parent
        focus: true

        Rectangle {
            anchors.fill: parent
            color: root.backend ? root.backend.settings.backgroundColor : theme.background

            GridView {
                id: grid
                anchors.fill: parent
                anchors.margins: 12
                property int thumbVisualWidth: (root.backend && root.backend.settings) ? root.backend.settings.thumbnailWidth : 220
                property int minHSpacing: 6
                property int computedCols: Math.max(1, Math.floor(width / (thumbVisualWidth + minHSpacing)))
                property int hSpacing: Math.max(minHSpacing, Math.floor((width - (computedCols * thumbVisualWidth)) / Math.max(1, computedCols)))
                cellWidth: thumbVisualWidth + hSpacing
                cellHeight: Math.round((thumbVisualWidth + hSpacing) * 1.2)
                clip: true
                model: root.backend ? root.backend.explorer.imageModel : null
                currentIndex: root.backend ? root.backend.explorer.currentIndex : -1
                focus: true
                activeFocusOnTab: true

                // Selection state (QML-only)
                property var selectedIndices: []
                property int lastClickedIndex: -1
                property int _lastClickIndex: -1
                property real _lastClickAtMs: 0
                property int _doubleClickIntervalMs: 350
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
                    if (root.backend) {
                        root.backend.dispatch("setCurrentIndex", { index: idx })
                    }
                    if (idx >= 0 && root.backend && root.backend.explorer.imageFiles && idx < root.backend.explorer.imageFiles.length) {
                        root.explorerSelectedPath = root.backend.explorer.imageFiles[idx]
                    }
                }

                function setCurrentIndexOnly(idx) {
                    if (root.backend) {
                        root.backend.dispatch("setCurrentIndex", { index: idx })
                    }
                    if (idx >= 0 && root.backend && root.backend.explorer.imageFiles && idx < root.backend.explorer.imageFiles.length) {
                        root.explorerSelectedPath = root.backend.explorer.imageFiles[idx]
                    }
                }

                onCurrentIndexChanged: {
                    if (grid.dragSelecting || !grid.selectionSyncEnabled) return
                    if (root.backend && root.backend.explorer.currentIndex >= 0) {
                        grid.selectedIndices = [root.backend.explorer.currentIndex]
                        grid.lastClickedIndex = root.backend.explorer.currentIndex
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
                        } else {
                            // suppress sync during multi-select drag
                            grid.selectionSyncEnabled = false
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
                            var total = root.backend ? (root.backend.explorer.imageFiles ? root.backend.explorer.imageFiles.length : 0) : 0
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
                            mouse.accepted = true

                        } else {
                            // treat as click (no significant drag)
                            // Do grid selection based on click position
                            var cx = mouse.x + grid.contentX
                            var cy = mouse.y + grid.contentY
                            var cols = grid.computedCols || 1
                            var col = Math.floor(cx / grid.cellWidth)
                            var row = Math.floor(cy / grid.cellHeight)
                            if (col < 0 || row < 0) {
                                // click on empty area -> clear selection unless modifiers held
                                if (!(mouse.modifiers & Qt.ControlModifier) && !(mouse.modifiers & Qt.ShiftModifier)) {
                                    grid.selectedIndices = []
                                    if (root.backend) root.backend.dispatch("setCurrentIndex", { index: -1 })
                                    root.explorerSelectedPath = ""
                                }
                                grid._lastClickIndex = -1
                                grid._lastClickAtMs = 0
                            } else {
                                var idx = row * cols + col
                                var total = root.backend ? (root.backend.explorer.imageFiles ? root.backend.explorer.imageFiles.length : 0) : 0
                                if (idx >= 0 && idx < total) {
                                    var nowMs = Date.now()
                                    var isDouble = (idx === grid._lastClickIndex) && ((nowMs - grid._lastClickAtMs) <= grid._doubleClickIntervalMs)
                                    // Update click tracking even if modifiers are held.
                                    grid._lastClickIndex = idx
                                    grid._lastClickAtMs = nowMs

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
                                    }

                                    // Reliable double-click handling lives here because this overlay
                                    // receives the left clicks (delegate MouseArea does not).
                                    if (isDouble && root.backend) {
                                        root.qmlDebugSafe("[THUMB] DOUBLE-CLICK idx=" + idx)
                                        // Ensure currentIndex is set before switching view.
                                        root.backend.dispatch("setCurrentIndex", { index: idx })
                                        root.backend.dispatch("setViewMode", { value: true })
                                    }
                                }
                            }
                            // Consume left click; this overlay owns selection/click behavior.
                            mouse.accepted = true
                        }

                        grid.forceActiveFocus()
                        grid.selectionRectVisible = false
                        grid.selectionSyncEnabled = true
                    }
                }

                // visual selection rect (content coords -> view coords)
                Rectangle {
                    id: selectionRect
                    visible: grid.selectionRectVisible
                    color: theme.selection
                    border.color: theme.selectionBorder
                    border.width: 1
                    radius: 2
                    x: Math.min(grid.selectionRectX, grid.selectionRectX + grid.selectionRectW) - grid.contentX
                    y: Math.min(grid.selectionRectY, grid.selectionRectY + grid.selectionRectH) - grid.contentY
                    width: Math.abs(grid.selectionRectW)
                    height: Math.abs(grid.selectionRectH)
                    z: 100
                }

                Keys.onPressed: function(event) {
                    if (!root.backend) return

                    var total = root.backend.explorer.imageFiles ? root.backend.explorer.imageFiles.length : 0
                    var idx = (root.backend.explorer.currentIndex >= 0) ? root.backend.explorer.currentIndex : 0
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
                        if (root.backend.explorer.currentIndex >= 0) {
                            root.explorerSelectedPath = (root.backend.explorer.imageFiles && root.backend.explorer.currentIndex < root.backend.explorer.imageFiles.length)
                                ? root.backend.explorer.imageFiles[root.backend.explorer.currentIndex]
                                : root.explorerSelectedPath
                            root.backend.dispatch("setViewMode", { value: true })
                        }
                        event.accepted = true
                    }

                    // Ctrl+C - Copy selected files
                    if (event.key === Qt.Key_C && (event.modifiers & Qt.ControlModifier)) {
                        var sel = grid.selectedIndices || []
                        if (sel.length > 0 && root.backend && root.backend.explorer.imageFiles) {
                            var paths = []
                            for (var i = 0; i < sel.length; ++i) {
                                var id = sel[i]
                                if (id >= 0 && id < root.backend.explorer.imageFiles.length) {
                                    paths.push(root.backend.explorer.imageFiles[id])
                                }
                            }
                            if (paths.length > 0) root.backend.dispatch("copyFiles", { paths: paths })
                        }
                        event.accepted = true
                    }

                    // Ctrl+X - Cut selected files
                    if (event.key === Qt.Key_X && (event.modifiers & Qt.ControlModifier)) {
                        var sel = grid.selectedIndices || []
                        if (sel.length > 0 && root.backend && root.backend.explorer.imageFiles) {
                            var paths = []
                            for (var i = 0; i < sel.length; ++i) {
                                var id = sel[i]
                                if (id >= 0 && id < root.backend.explorer.imageFiles.length) {
                                    paths.push(root.backend.explorer.imageFiles[id])
                                }
                            }
                            if (paths.length > 0) root.backend.dispatch("cutFiles", { paths: paths })
                        }
                        event.accepted = true
                    }

                    // Ctrl+V - Paste files
                    if (event.key === Qt.Key_V && (event.modifiers & Qt.ControlModifier)) {
                        if (root.backend && root.backend.explorer.clipboardHasFiles) {
                            root.backend.dispatch("pasteFiles", null)
                        }
                        event.accepted = true
                    }

                    // Delete - Delete selected files (Explorer only)
                    if (event.key === Qt.Key_Delete) {
                        var sel = grid.selectedIndices || []
                        if (sel.length > 0 && root.backend && root.backend.explorer.imageFiles) {
                            var paths = []
                            for (var i = 0; i < sel.length; ++i) {
                                var id = sel[i]
                                if (id >= 0 && id < root.backend.explorer.imageFiles.length) {
                                    paths.push(root.backend.explorer.imageFiles[id])
                                }
                            }
                            if (paths.length > 0) {
                                var title = (paths.length === 1) ? "Delete File" : "Delete Files"
                                var info = (paths.length === 1) ? (paths[0].replace(/^.*[\\/]/, "") + "\n\nIt will be moved to Recycle Bin.") : (paths.length + " files will be moved to Recycle Bin.")
                                root.showDeleteDialog(title, "", info, paths)
                            }
                        }
                        event.accepted = true
                        return
                    }

                    // F2 - Rename selected file (Explorer only, single selection required)
                    if (event.key === Qt.Key_F2) {
                        var sel = grid.selectedIndices || []
                        if (sel.length === 1 && root.backend && root.backend.explorer.imageFiles) {
                            var idx = sel[0]
                            if (idx >= 0 && idx < root.backend.explorer.imageFiles.length) {
                                var selPath = root.backend.explorer.imageFiles[idx]
                                renameDialog.oldPath = selPath
                                renameDialog.initialName = selPath.replace(/^.*[\\/]/, "")
                                renameDialog.open()
                            }
                        }
                        event.accepted = true
                        return
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
                        radius: theme.radiusMedium
                        color: (grid.selectedIndices.indexOf(delegateRoot.index) !== -1) ? theme.selection : theme.surface
                        border.color: (grid.selectedIndices.indexOf(delegateRoot.index) !== -1) ? theme.selectionBorder : theme.border
                        border.width: 1

                        MouseArea {
                            anchors.fill: parent
                            acceptedButtons: Qt.RightButton

                            onClicked: function(mouse) {
                                if (mouse.button === Qt.RightButton) {
                                    grid.setSelectionTo(delegateRoot.index)
                                    ctxMenu.popup(mouse.x, mouse.y)
                                }
                            }
                        }

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
                                radius: theme.radiusSmall
                                color: theme.background

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
                                color: theme.text
                                text: delegateRoot.name
                                wrapMode: Text.Wrap
                                font.pixelSize: 13
                            }
                            Text {
                                Layout.fillWidth: true
                                color: theme.textDim
                                font.pixelSize: 11
                                text: [ (delegateRoot.name && delegateRoot.name.indexOf('.') !== -1) ? delegateRoot.name.split('.').pop().toUpperCase() : null, delegateRoot.resolutionText, delegateRoot.sizeText ].filter(Boolean).join(" | ")
                            }
                            Label {
                                Layout.fillWidth: true
                                color: theme.textDim
                                opacity: 0.7
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
                                    if (!root.backend) return
                                    root.backend.dispatch("setCurrentIndex", { index: delegateRoot.index })
                                    root.backend.dispatch("setViewMode", { value: true })
                                }
                            }
                            MenuSeparator {}
                            MenuItem {
                                text: grid.selectedIndices.length > 1 ? "Copy " + grid.selectedIndices.length + " files" : "Copy"
                                onTriggered: {
                                    if (!root.backend) return
                                    if (grid.selectedIndices.length > 0 && root.backend.explorer.imageFiles) {
                                        var paths = []
                                        for (var i = 0; i < grid.selectedIndices.length; ++i) {
                                            var idx = grid.selectedIndices[i]
                                            if (idx >= 0 && idx < root.backend.explorer.imageFiles.length) {
                                                paths.push(root.backend.explorer.imageFiles[idx])
                                            }
                                        }
                            if (paths.length > 0) {
                                root.backend.dispatch("copyFiles", { paths: paths })
                            }
                                    }
                                }
                            }
                            MenuItem {
                                text: grid.selectedIndices.length > 1 ? "Cut " + grid.selectedIndices.length + " files" : "Cut"
                                onTriggered: {
                                    if (!root.backend) return
                                    if (grid.selectedIndices.length > 0 && root.backend.explorer.imageFiles) {
                                        var paths = []
                                        for (var i = 0; i < grid.selectedIndices.length; ++i) {
                                            var idx = grid.selectedIndices[i]
                                            if (idx >= 0 && idx < root.backend.explorer.imageFiles.length) {
                                                paths.push(root.backend.explorer.imageFiles[idx])
                                            }
                                        }
                                        if (paths.length > 0) {
                                            root.backend.dispatch("cutFiles", { paths: paths })
                                        }
                                    }
                                }
                            }
                            MenuItem {
                                text: "Paste"
                                enabled: root.backend && root.backend.explorer.clipboardHasFiles
                                onTriggered: if (root.backend) root.backend.dispatch("pasteFiles", null)
                            }
                            MenuItem {
                                text: "Rename"
                                onTriggered: {
                                    renameDialog.oldPath = delegateRoot.path
                                    renameDialog.initialName = delegateRoot.name
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
                                onTriggered: if (root.backend) root.backend.dispatch("copyText", { text: delegateRoot.path })
                            }
                            MenuItem {
                                text: "Reveal in Explorer"
                                onTriggered: if (root.backend) root.backend.dispatch("revealInExplorer", { path: delegateRoot.path })
                            }
                        }


                    }
                }
            }
        }
    }
}
