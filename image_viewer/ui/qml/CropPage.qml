/*
 CropPage.qml — QML crop mode UI (normalized crop rect + non-destructive preview + pan).

 Contract:
 - All authoritative crop state lives in `backend.crop` (CropState).
 - QML proposes rect updates via `backend.dispatch("cropSetRect", {...})`.
 - Crop rect is normalized (0..1) relative to the full image.
*/

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Window
import "."

Item {
    id: root

    required property var backend
    required property Theme theme

    focus: true

    function _clamp(v, lo, hi) {
        return Math.max(lo, Math.min(hi, v))
    }

    function _fitScale() {
        if (!root.backend) return 1.0
        if (img.status !== Image.Ready) return 1.0
        if (img.sourceSize.width <= 0 || img.sourceSize.height <= 0) return 1.0
        var sx = canvas.width / img.sourceSize.width
        var sy = canvas.height / img.sourceSize.height
        return Math.min(sx, sy)
    }

    // Keyboard-driven pan mode: hold Space.
    property bool panMode: false

    Keys.onPressed: function(ev) {
        if (ev.key === Qt.Key_Space) {
            root.panMode = true
            ev.accepted = true
            return
        }
        if (ev.key === Qt.Key_Escape) {
            if (!root.backend || !root.backend.crop) return
            if (root.backend.crop.previewEnabled) {
                root.backend.dispatch("cropSetPreview", { value: false })
            } else {
                root.backend.dispatch("closeCrop", null)
            }
            ev.accepted = true
            return
        }
        if (ev.key === Qt.Key_Return || ev.key === Qt.Key_Enter) {
            if (!root.backend || !root.backend.crop) return
            root.backend.dispatch("cropSetPreview", { value: !root.backend.crop.previewEnabled })
            ev.accepted = true
            return
        }
    }

    Keys.onReleased: function(ev) {
        if (ev.key === Qt.Key_Space) {
            root.panMode = false
            ev.accepted = true
            return
        }
    }

    MessageDialog {
        id: messageDialog
        title: ""
        text: ""
    }

    Connections {
        target: root.backend

        function onTaskEvent(ev) {
            if (!ev || ev.name !== "cropSave") return

            if (ev.state === "error") {
                messageDialog.title = "Crop save error"
                messageDialog.text = String(ev.message || "")
                messageDialog.open()
                return
            }

            if (ev.state === "finished") {
                messageDialog.title = "Crop saved"
                messageDialog.text = "Saved to:\n" + String(ev.outputPath || "")
                messageDialog.open()
                return
            }
        }
    }

    FileDialog {
        id: saveDialog
        title: "Save cropped image"
        fileMode: FileDialog.SaveFile
        nameFilters: ["Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)", "All files (*)"]
        onAccepted: {
            if (!root.backend) return
            root.backend.dispatch("cropSaveAs", { outputPath: saveDialog.selectedFile.toString() })
        }
    }

    Rectangle {
        anchors.fill: parent
        color: (root.backend && root.backend.settings) ? root.backend.settings.backgroundColor : root.theme.background

        RowLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 16

            // --- Left: aspect presets ---
            Rectangle {
                Layout.preferredWidth: 200
                Layout.fillHeight: true
                radius: root.theme.radiusMedium
                color: root.theme.surface
                border.color: root.theme.border
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 10

                    Label {
                        text: "Crop"
                        font.pixelSize: 18
                        font.bold: true
                        color: root.theme.text
                    }

                    Label {
                        text: "Aspect"
                        font.bold: true
                        color: root.theme.text
                    }

                    Button {
                        text: "Free"
                        onClicked: root.backend && root.backend.dispatch("cropSetAspect", { ratio: 0 })
                    }

                    Button {
                        text: "1 : 1"
                        onClicked: root.backend && root.backend.dispatch("cropSetAspect", { ratio: 1.0 })
                    }

                    Button {
                        text: "4 : 3"
                        onClicked: root.backend && root.backend.dispatch("cropSetAspect", { ratio: 4.0 / 3.0 })
                    }

                    Button {
                        text: "16 : 9"
                        onClicked: root.backend && root.backend.dispatch("cropSetAspect", { ratio: 16.0 / 9.0 })
                    }

                    Item { Layout.fillHeight: true }

                    Label {
                        text: root.panMode ? "Pan: ON (Space)" : "Pan: hold Space"
                        color: root.panMode ? root.theme.accent : root.theme.textDim
                        wrapMode: Text.WordWrap
                    }
                }
            }

            // --- Center: crop canvas ---
            Rectangle {
                id: canvas
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: root.theme.radiusMedium
                color: Qt.rgba(0, 0, 0, 0.15)
                border.color: root.theme.border
                border.width: 1
                clip: true

                Flickable {
                    id: flick
                    anchors.fill: parent
                    clip: true
                    interactive: false
                    contentWidth: img.width
                    contentHeight: img.height

                    function clampContent() {
                        contentX = root._clamp(contentX, 0, Math.max(0, contentWidth - width))
                        contentY = root._clamp(contentY, 0, Math.max(0, contentHeight - height))
                    }

                    Item {
                        id: content
                        width: img.width
                        height: img.height

                        Image {
                            id: img
                            anchors.fill: parent
                            asynchronous: true
                            cache: false
                            smooth: true
                            fillMode: Image.Stretch

                            // Scale is expressed by changing width/height of this item.
                            // This keeps overlay math simple and stable.
                            width: {
                                if (status !== Image.Ready) return canvas.width
                                var base = Math.max(1, sourceSize.width)
                                var s = (root.backend && root.backend.crop)
                                    ? (root.backend.crop.fitMode ? root._fitScale() : root.backend.crop.zoom)
                                    : 1.0
                                return base * s
                            }
                            height: {
                                if (status !== Image.Ready) return canvas.height
                                var base = Math.max(1, sourceSize.height)
                                var s = (root.backend && root.backend.crop)
                                    ? (root.backend.crop.fitMode ? root._fitScale() : root.backend.crop.zoom)
                                    : 1.0
                                return base * s
                            }

                            source: (root.backend && root.backend.crop) ? root.backend.crop.imageUrl : ""

                            onStatusChanged: {
                                if (status === Image.Ready) {
                                    // When entering fit mode, keep image centered.
                                    flick.clampContent()
                                }
                            }
                        }

                        // --- Pan drag handler (Space) ---
                        DragHandler {
                            id: panDrag
                            enabled: root.panMode
                            target: null

                            property real _lastX: 0
                            property real _lastY: 0

                            onActiveChanged: {
                                if (active) {
                                    _lastX = 0
                                    _lastY = 0
                                }
                            }

                            onTranslationChanged: {
                                var dx = translation.x - _lastX
                                var dy = translation.y - _lastY
                                _lastX = translation.x
                                _lastY = translation.y
                                flick.contentX = flick.contentX - dx
                                flick.contentY = flick.contentY - dy
                                flick.clampContent()
                            }
                        }

                        // --- Crop overlay ---
                        Item {
                            id: overlay
                            anchors.fill: img

                            property real rectXpx: (root.backend && root.backend.crop) ? (root.backend.crop.rectX * width) : 0
                            property real rectYpx: (root.backend && root.backend.crop) ? (root.backend.crop.rectY * height) : 0
                            property real rectWpx: (root.backend && root.backend.crop) ? (root.backend.crop.rectW * width) : 0
                            property real rectHpx: (root.backend && root.backend.crop) ? (root.backend.crop.rectH * height) : 0

                            // Outside mask (non-destructive preview foundation)
                            Rectangle { x: 0; y: 0; width: overlay.width; height: overlay.rectYpx; color: Qt.rgba(0,0,0,0.55) }
                            Rectangle { x: 0; y: overlay.rectYpx + overlay.rectHpx; width: overlay.width; height: Math.max(0, overlay.height - (overlay.rectYpx + overlay.rectHpx)); color: Qt.rgba(0,0,0,0.55) }
                            Rectangle { x: 0; y: overlay.rectYpx; width: overlay.rectXpx; height: overlay.rectHpx; color: Qt.rgba(0,0,0,0.55) }
                            Rectangle { x: overlay.rectXpx + overlay.rectWpx; y: overlay.rectYpx; width: Math.max(0, overlay.width - (overlay.rectXpx + overlay.rectWpx)); height: overlay.rectHpx; color: Qt.rgba(0,0,0,0.55) }

                            Rectangle {
                                id: cropBorder
                                x: overlay.rectXpx
                                y: overlay.rectYpx
                                width: overlay.rectWpx
                                height: overlay.rectHpx
                                color: "transparent"
                                border.color: root.theme.accent
                                border.width: 2
                            }

                            // Grid lines (3x3)
                            Item {
                                id: grid
                                visible: root.backend && root.backend.crop && !root.backend.crop.previewEnabled
                                x: overlay.rectXpx
                                y: overlay.rectYpx
                                width: overlay.rectWpx
                                height: overlay.rectHpx
                                clip: true

                                Repeater {
                                    model: 2
                                    Rectangle {
                                        required property int index
                                        width: 1
                                        height: grid.height
                                        x: Math.round((index + 1) * (grid.width / 3))
                                        y: 0
                                        color: Qt.rgba(1,1,1,0.5)
                                    }
                                }
                                Repeater {
                                    model: 2
                                    Rectangle {
                                        required property int index
                                        width: grid.width
                                        height: 1
                                        x: 0
                                        y: Math.round((index + 1) * (grid.height / 3))
                                        color: Qt.rgba(1,1,1,0.5)
                                    }
                                }
                            }

                            function _dispatchRect(xN, yN, wN, hN, anchor) {
                                if (!root.backend) return
                                root.backend.dispatch("cropSetRect", { x: xN, y: yN, w: wN, h: hN, anchor: anchor })
                            }

                            // Move within rect
                            MouseArea {
                                id: moveArea
                                x: overlay.rectXpx
                                y: overlay.rectYpx
                                width: overlay.rectWpx
                                height: overlay.rectHpx
                                enabled: root.backend && root.backend.crop && !root.panMode
                                hoverEnabled: true
                                cursorShape: Qt.SizeAllCursor

                                property real startXN: 0
                                property real startYN: 0
                                property real startWN: 0
                                property real startHN: 0
                                property real pressX: 0
                                property real pressY: 0

                                onPressed: function(mouse) {
                                    if (!root.backend || !root.backend.crop) return
                                    startXN = root.backend.crop.rectX
                                    startYN = root.backend.crop.rectY
                                    startWN = root.backend.crop.rectW
                                    startHN = root.backend.crop.rectH
                                    pressX = mouse.x
                                    pressY = mouse.y
                                }

                                onPositionChanged: function(mouse) {
                                    if (!pressed) return
                                    if (!root.backend || !root.backend.crop) return
                                    var dxN = (mouse.x - pressX) / Math.max(1, overlay.width)
                                    var dyN = (mouse.y - pressY) / Math.max(1, overlay.height)
                                    overlay._dispatchRect(startXN + dxN, startYN + dyN, startWN, startHN, "move")
                                }
                            }

                            // Handle factory
                            function _handleRect(name) {
                                var s = 12
                                var cx = overlay.rectXpx
                                var cy = overlay.rectYpx
                                var cw = overlay.rectWpx
                                var ch = overlay.rectHpx

                                if (name === "tl") return Qt.rect(cx - s/2, cy - s/2, s, s)
                                if (name === "tr") return Qt.rect(cx + cw - s/2, cy - s/2, s, s)
                                if (name === "bl") return Qt.rect(cx - s/2, cy + ch - s/2, s, s)
                                if (name === "br") return Qt.rect(cx + cw - s/2, cy + ch - s/2, s, s)
                                if (name === "l") return Qt.rect(cx - s/2, cy + ch/2 - s/2, s, s)
                                if (name === "r") return Qt.rect(cx + cw - s/2, cy + ch/2 - s/2, s, s)
                                if (name === "t") return Qt.rect(cx + cw/2 - s/2, cy - s/2, s, s)
                                if (name === "b") return Qt.rect(cx + cw/2 - s/2, cy + ch - s/2, s, s)
                                return Qt.rect(0,0,0,0)
                            }

                            Repeater {
                                model: ["tl","tr","bl","br","l","r","t","b"]

                                Rectangle {
                                    required property string modelData
                                    visible: root.backend && root.backend.crop && !root.backend.crop.previewEnabled && !root.panMode
                                    color: root.theme.surface
                                    border.color: root.theme.accent
                                    border.width: 1
                                    radius: 2

                                    property string handleName: modelData
                                    property var r: overlay._handleRect(handleName)

                                    x: r.x
                                    y: r.y
                                    width: r.width
                                    height: r.height

                                    MouseArea {
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: {
                                            if (parent.handleName === "tl" || parent.handleName === "br") return Qt.SizeFDiagCursor
                                            if (parent.handleName === "tr" || parent.handleName === "bl") return Qt.SizeBDiagCursor
                                            if (parent.handleName === "l" || parent.handleName === "r") return Qt.SizeHorCursor
                                            return Qt.SizeVerCursor
                                        }

                                        property real startXN: 0
                                        property real startYN: 0
                                        property real startWN: 0
                                        property real startHN: 0
                                        property real pressX: 0
                                        property real pressY: 0

                                        onPressed: function(mouse) {
                                            if (!root.backend || !root.backend.crop) return
                                            startXN = root.backend.crop.rectX
                                            startYN = root.backend.crop.rectY
                                            startWN = root.backend.crop.rectW
                                            startHN = root.backend.crop.rectH
                                            pressX = mouse.x
                                            pressY = mouse.y
                                        }

                                        onPositionChanged: function(mouse) {
                                            if (!pressed) return
                                            if (!root.backend || !root.backend.crop) return

                                            var dxN = (mouse.x - pressX) / Math.max(1, overlay.width)
                                            var dyN = (mouse.y - pressY) / Math.max(1, overlay.height)

                                            var xN = startXN
                                            var yN = startYN
                                            var wN = startWN
                                            var hN = startHN

                                            // Adjust based on handle.
                                            if (parent.handleName.indexOf("l") >= 0) {
                                                xN = startXN + dxN
                                                wN = startWN - dxN
                                            }
                                            if (parent.handleName.indexOf("r") >= 0) {
                                                wN = startWN + dxN
                                            }
                                            if (parent.handleName.indexOf("t") >= 0) {
                                                yN = startYN + dyN
                                                hN = startHN - dyN
                                            }
                                            if (parent.handleName.indexOf("b") >= 0) {
                                                hN = startHN + dyN
                                            }

                                            overlay._dispatchRect(xN, yN, wN, hN, parent.handleName)
                                        }
                                    }
                                }
                            }

                            // Wheel zoom (around cursor)
                            WheelHandler {
                                id: wheel
                                target: null
                                enabled: root.backend && root.backend.crop
                                onWheel: function(ev) {
                                    if (!root.backend || !root.backend.crop) return
                                    var factor = (ev.angleDelta.y > 0) ? 1.25 : 0.8

                                    // Keep zoom centered around cursor by preserving relative content point.
                                    var viewX = ev.x
                                    var viewY = ev.y
                                    var oldW = flick.contentWidth
                                    var oldH = flick.contentHeight
                                    var cx = flick.contentX + viewX
                                    var cy = flick.contentY + viewY
                                    var rx = oldW > 0 ? (cx / oldW) : 0.5
                                    var ry = oldH > 0 ? (cy / oldH) : 0.5

                                    var base = root.backend.crop.fitMode ? root._fitScale() : root.backend.crop.zoom
                                    var next = root._clamp(base * factor, 0.05, 20.0)
                                    root.backend.dispatch("cropSetZoom", { value: next })

                                    Qt.callLater(function() {
                                        var nw = flick.contentWidth
                                        var nh = flick.contentHeight
                                        flick.contentX = root._clamp((nw * rx) - viewX, 0, Math.max(0, nw - flick.width))
                                        flick.contentY = root._clamp((nh * ry) - viewY, 0, Math.max(0, nh - flick.height))
                                    })

                                    ev.accepted = true
                                }
                            }
                        }
                    }
                }
            }

            // --- Right: actions + preview ---
            Rectangle {
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                radius: root.theme.radiusMedium
                color: root.theme.surface
                border.color: root.theme.border
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 10

                    Label {
                        text: "Actions"
                        font.pixelSize: 16
                        font.bold: true
                        color: root.theme.text
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Button {
                            text: "Fit"
                            Layout.fillWidth: true
                            onClicked: root.backend && root.backend.dispatch("cropSetFitMode", { value: true })
                        }

                        Button {
                            text: "Reset"
                            Layout.fillWidth: true
                            onClicked: root.backend && root.backend.dispatch("cropResetRect", null)
                        }
                    }

                    Button {
                        Layout.fillWidth: true
                        text: (root.backend && root.backend.crop && root.backend.crop.previewEnabled) ? "Exit Preview (Enter)" : "Preview (Enter)"
                        onClicked: {
                            if (!root.backend || !root.backend.crop) return
                            root.backend.dispatch("cropSetPreview", { value: !root.backend.crop.previewEnabled })
                        }
                    }

                    Button {
                        Layout.fillWidth: true
                        text: "Save As..."
                        onClicked: saveDialog.open()
                    }

                    Button {
                        Layout.fillWidth: true
                        text: "Close (Esc)"
                        onClicked: root.backend && root.backend.dispatch("closeCrop", null)
                    }

                    Label {
                        Layout.fillWidth: true
                        text: {
                            if (!root.backend || !root.backend.crop) return ""
                            var w = root.backend.crop.imageWidth
                            var h = root.backend.crop.imageHeight
                            if (w <= 0 || h <= 0) return ""
                            var l = Math.round(root.backend.crop.rectX * w)
                            var t = Math.round(root.backend.crop.rectY * h)
                            var cw = Math.round(root.backend.crop.rectW * w)
                            var ch = Math.round(root.backend.crop.rectH * h)
                            return "Rect: " + l + "," + t + "  " + cw + "×" + ch
                        }
                        color: root.theme.textDim
                        wrapMode: Text.WordWrap
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: root.theme.border
                    }

                    Label {
                        text: "Preview"
                        font.bold: true
                        color: root.theme.text
                    }

                    Rectangle {
                        id: previewBox
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: root.theme.radiusSmall
                        color: root.theme.background
                        border.color: root.theme.border
                        border.width: 1
                        clip: true

                        // Non-destructive preview: show the crop area by sampling the current image.
                        Item {
                            anchors.fill: parent
                            visible: root.backend && root.backend.crop && root.backend.crop.previewEnabled && img.status === Image.Ready

                            id: previewItem

                            property real rectXpx: overlay.rectXpx
                            property real rectYpx: overlay.rectYpx
                            property real rectWpx: overlay.rectWpx
                            property real rectHpx: overlay.rectHpx

                            Item {
                                id: previewScaleHost
                                anchors.fill: parent
                                clip: true

                                property real s: {
                                    var sw = Math.max(1, previewItem.rectWpx)
                                    var sh = Math.max(1, previewItem.rectHpx)
                                    return Math.min(width / sw, height / sh)
                                }

                                ShaderEffectSource {
                                    sourceItem: img
                                    hideSource: false
                                    sourceRect: Qt.rect(previewItem.rectXpx, previewItem.rectYpx, previewItem.rectWpx, previewItem.rectHpx)
                                    width: previewItem.rectWpx
                                    height: previewItem.rectHpx
                                    smooth: true
                                    scale: previewScaleHost.s
                                    anchors.centerIn: parent
                                }
                            }
                        }

                        Text {
                            anchors.centerIn: parent
                            visible: !(root.backend && root.backend.crop && root.backend.crop.previewEnabled && img.status === Image.Ready)
                            text: "Toggle Preview to see crop"
                            color: root.theme.textDim
                        }
                    }
                }
            }
        }
    }
}
