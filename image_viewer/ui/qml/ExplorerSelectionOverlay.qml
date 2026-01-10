/*
 ExplorerSelectionOverlay.qml — Explorer Grid 위의 선택/드래그/더블클릭 등 입력 처리를 담당하는 오버레이.
 존재 이유: 드래그 셀렉션, 선택 사각형, 더블클릭(뷰 전환) 같은 상호작용을 Grid 내의 delegate에서 분리해 중앙에서 관리하기 위해 존재합니다.
*/

pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: overlay

    // Owning objects/refs.
    required property var app
    required property var grid
    required property var backend
    required property var theme

    // IMPORTANT: GridView (Flickable) children are parented to `contentItem` by default.
    // This overlay must live in the viewport, not in the scrolling content, otherwise
    // `mouse.x/y` are already in content coordinates and adding `contentX/contentY`
    // will double-offset hit testing (breaking click selection).
    parent: overlay.grid
    z: 1000

    anchors.fill: overlay.grid

    function _log(msg) {
        if (overlay.app && typeof overlay.app.qmlDebugSafe === "function") {
            overlay.app.qmlDebugSafe(String(msg))
            return
        }
        console.log(String(msg))
    }

    // Overlay mouse area: any drag starts selection and disables scrolling
    MouseArea {
        id: selectionMouse
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        hoverEnabled: true

        onPressed: function(mouse) {
            // capture start (content coordinates)
            overlay.grid.dragSelecting = false
            overlay.grid.selectionRectVisible = true
            overlay.grid.pressX = mouse.x
            overlay.grid.pressY = mouse.y
            overlay.grid.selectionRectX = mouse.x + overlay.grid.contentX
            overlay.grid.selectionRectY = mouse.y + overlay.grid.contentY
            overlay.grid.selectionRectW = 0
            overlay.grid.selectionRectH = 0

            // block GridView scrolling while dragging selection
            overlay.grid.interactive = false

            // prepare selection behavior: clear unless ctrl/shift held
            if (!(mouse.modifiers & Qt.ControlModifier) && !(mouse.modifiers & Qt.ShiftModifier)) {
                overlay.grid.selectedIndices = []
            } else {
                // suppress sync during multi-select drag
                overlay.grid.selectionSyncEnabled = false
            }
        }

        onPositionChanged: function(mouse) {
            var dx = mouse.x - overlay.grid.pressX
            var dy = mouse.y - overlay.grid.pressY
            // small movement -> not a dragSelect yet
            if (!overlay.grid.dragSelecting && Math.abs(dx) + Math.abs(dy) > 6) {
                overlay.grid.dragSelecting = true
            }

            if (overlay.grid.dragSelecting) {
                var cx = mouse.x + overlay.grid.contentX
                var cy = mouse.y + overlay.grid.contentY
                overlay.grid.selectionRectW = cx - overlay.grid.selectionRectX
                overlay.grid.selectionRectH = cy - overlay.grid.selectionRectY
            }
        }

        onReleased: function(mouse) {
            overlay.grid.interactive = true
            var dx = mouse.x - overlay.grid.pressX
            var dy = mouse.y - overlay.grid.pressY

            if (overlay.grid.dragSelecting) {
                // finalize rectangular selection (content coordinates)
                overlay.grid.selectionRectVisible = false
                overlay.grid.dragSelecting = false

                var x1 = Math.min(overlay.grid.selectionRectX, overlay.grid.selectionRectX + overlay.grid.selectionRectW)
                var y1 = Math.min(overlay.grid.selectionRectY, overlay.grid.selectionRectY + overlay.grid.selectionRectH)
                var x2 = Math.max(overlay.grid.selectionRectX, overlay.grid.selectionRectX + overlay.grid.selectionRectW)
                var y2 = Math.max(overlay.grid.selectionRectY, overlay.grid.selectionRectY + overlay.grid.selectionRectH)

                // use cell math for reliable hit detection
                var total = overlay.backend ? (overlay.backend.explorer ? (overlay.backend.explorer.imageFiles ? overlay.backend.explorer.imageFiles.length : 0) : 0) : 0
                var cols = overlay.grid.computedCols || 1
                var newSel = overlay.grid.selectedIndices.slice()
                for (var i = 0; i < total; ++i) {
                    var col = i % cols
                    var row = Math.floor(i / cols)
                    var ix = col * overlay.grid.cellWidth
                    var iy = row * overlay.grid.cellHeight
                    var iw = overlay.grid.cellWidth
                    var ih = overlay.grid.cellHeight

                    // check overlap
                    if (!(ix > x2 || (ix + iw) < x1 || iy > y2 || (iy + ih) < y1)) {
                        if (newSel.indexOf(i) === -1) newSel.push(i)
                    }
                }
                overlay.grid.selectedIndices = newSel

                // set currentIndex to last selected
                if (overlay.grid.selectedIndices.length > 0) {
                    var last = overlay.grid.selectedIndices[overlay.grid.selectedIndices.length - 1]
                    overlay.grid.selectionSyncEnabled = false
                    overlay.grid.setCurrentIndexOnly(last)
                    overlay.grid.lastClickedIndex = last
                    Qt.callLater(function() { overlay.grid.selectionSyncEnabled = true })
                }
                mouse.accepted = true

            } else {
                // treat as click (no significant drag)
                // Do grid selection based on click position
                var cx = mouse.x + overlay.grid.contentX
                var cy = mouse.y + overlay.grid.contentY
                var cols = overlay.grid.computedCols || 1
                var col = Math.floor(cx / overlay.grid.cellWidth)
                var row = Math.floor(cy / overlay.grid.cellHeight)
                if (col < 0 || row < 0) {
                    // click on empty area -> clear selection unless modifiers held
                    if (!(mouse.modifiers & Qt.ControlModifier) && !(mouse.modifiers & Qt.ShiftModifier)) {
                        overlay.grid.selectedIndices = []
                        if (overlay.backend) overlay.backend.dispatch("setCurrentIndex", { index: -1 })
                        if (overlay.app) overlay.app.explorerSelectedPath = ""
                    }
                    overlay.grid._lastClickIndex = -1
                    overlay.grid._lastClickAtMs = 0
                } else {
                    var idx = row * cols + col
                    var total = overlay.backend ? (overlay.backend.explorer ? (overlay.backend.explorer.imageFiles ? overlay.backend.explorer.imageFiles.length : 0) : 0) : 0
                    if (idx >= 0 && idx < total) {
                        var nowMs = Date.now()
                        var isDouble = (idx === overlay.grid._lastClickIndex) && ((nowMs - overlay.grid._lastClickAtMs) <= overlay.grid._doubleClickIntervalMs)
                        // Update click tracking even if modifiers are held.
                        overlay.grid._lastClickIndex = idx
                        overlay.grid._lastClickAtMs = nowMs

                        if (mouse.modifiers & Qt.ShiftModifier && overlay.grid.lastClickedIndex >= 0) {
                            var a = Math.min(overlay.grid.lastClickedIndex, idx)
                            var b = Math.max(overlay.grid.lastClickedIndex, idx)
                            var newSel = overlay.grid.selectedIndices.slice()
                            for (var i = a; i <= b; ++i) {
                                if (newSel.indexOf(i) === -1) newSel.push(i)
                            }
                            overlay.grid.selectedIndices = newSel
                            overlay.grid.lastClickedIndex = idx
                            overlay.grid.selectionSyncEnabled = false
                            overlay.grid.setCurrentIndexOnly(idx)
                            Qt.callLater(function() { overlay.grid.selectionSyncEnabled = true })
                            overlay.grid.positionViewAtIndex(idx, GridView.Visible)
                        } else if (mouse.modifiers & Qt.ControlModifier) {
                            var newSel = overlay.grid.selectedIndices.slice()
                            var p = newSel.indexOf(idx)
                            if (p === -1) newSel.push(idx)
                            else newSel.splice(p, 1)
                            overlay.grid.selectedIndices = newSel
                            overlay.grid.lastClickedIndex = idx
                            overlay.grid.selectionSyncEnabled = false
                            overlay.grid.setCurrentIndexOnly(idx)
                            Qt.callLater(function() { overlay.grid.selectionSyncEnabled = true })
                            overlay.grid.positionViewAtIndex(idx, GridView.Visible)
                        } else {
                            overlay.grid.setSelectionTo(idx)
                            overlay.grid.selectionRectVisible = false
                        }

                        // Reliable double-click handling lives here because this overlay
                        // receives the left clicks (delegate MouseArea does not).
                        if (isDouble && overlay.backend) {
                            overlay._log("[THUMB] DOUBLE-CLICK idx=" + idx)
                            // Ensure currentIndex is set before switching view.
                            overlay.backend.dispatch("setCurrentIndex", { index: idx })
                            overlay.backend.dispatch("setViewMode", { value: true })
                        }
                    }
                }
                // Consume left click; this overlay owns selection/click behavior.
                mouse.accepted = true
            }

            overlay.grid.forceActiveFocus()
            overlay.grid.selectionRectVisible = false
            overlay.grid.selectionSyncEnabled = true
        }
    }

    // visual selection rect (content coords -> view coords)
    Rectangle {
        id: selectionRect
        visible: overlay.grid.selectionRectVisible
        color: overlay.theme.selection
        border.color: overlay.theme.selectionBorder
        border.width: 1
        radius: 2
        x: Math.min(overlay.grid.selectionRectX, overlay.grid.selectionRectX + overlay.grid.selectionRectW) - overlay.grid.contentX
        y: Math.min(overlay.grid.selectionRectY, overlay.grid.selectionRectY + overlay.grid.selectionRectH) - overlay.grid.contentY
        width: Math.abs(overlay.grid.selectionRectW)
        height: Math.abs(overlay.grid.selectionRectH)
        z: 100
    }
}
