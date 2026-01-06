import QtQuick 2.15

Item {
    id: root
    // NOTE: This is set from Python via rootObject().setProperty("main", ...)
    // so we can avoid QML global/context-property access (qmllint UnqualifiedAccess).
    property var main: null
    property color backgroundColor: "#1a1a1a"
    property bool hqDownscaleEnabled: false
    focus: true

    // Keys handlers only run for the item with activeFocus. In the fullscreen viewer,
    // we want Escape/Enter/Return to *always* exit view mode, even if a Shortcut exists.
    // Accepting ShortcutOverride keeps these keys from being consumed by shortcut routing.
    Keys.priority: Keys.BeforeItem
    Keys.onShortcutOverride: function(event) {
        if (!root.main) return
        if (!root.main.viewMode) return
        if (event.key === Qt.Key_Escape || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            root.main.qmlDebug("ViewerPage Keys.onShortcutOverride: key=" + event.key + " modifiers=" + event.modifiers + " accepted=" + event.accepted)
            event.accepted = true
        }
    }
    Keys.onEscapePressed: {
        if (!root.main) return
        root.main.qmlDebug("ViewerPage Keys.onEscapePressed")
        root.main.closeView()
    }
    Keys.onReturnPressed: {
        if (!root.main) return
        root.main.qmlDebug("ViewerPage Keys.onReturnPressed")
        root.main.closeView()
    }
    Keys.onEnterPressed: {
        if (!root.main) return
        root.main.qmlDebug("ViewerPage Keys.onEnterPressed")
        root.main.closeView()
    }

    function _clamp(v, lo, hi) {
        return Math.max(lo, Math.min(hi, v))
    }

    function _fitScale() {
        // Approximate legacy get_fit_scale() using sourceSize and viewport size.
        if (!root.main) return 1.0
        if (img.status !== Image.Ready) return 1.0
        if (img.sourceSize.width <= 0 || img.sourceSize.height <= 0) return 1.0
        var sx = flick.width / img.sourceSize.width
        var sy = flick.height / img.sourceSize.height
        return Math.min(sx, sy)
    }

    function _zoomAround(viewX, viewY, newZoom) {
        // Keep the content point under (viewX, viewY) stable when zoom changes.
        // viewX/viewY are in Flickable viewport coordinates.
        if (!root.main) return
        if (img.status !== Image.Ready) {
            root.main.zoom = newZoom
            return
        }

        var oldW = flick.contentWidth
        var oldH = flick.contentHeight
        var cx = flick.contentX + viewX
        var cy = flick.contentY + viewY
        var rx = oldW > 0 ? (cx / oldW) : 0.5
        var ry = oldH > 0 ? (cy / oldH) : 0.5

        root.main.zoom = newZoom

        // Apply new scroll offsets. contentWidth/Height update after bindings settle;
        // schedule to next tick.
        Qt.callLater(function() {
            var nw = flick.contentWidth
            var nh = flick.contentHeight
            var nx = (nw * rx) - viewX
            var ny = (nh * ry) - viewY
            flick.contentX = _clamp(nx, 0, Math.max(0, nw - flick.width))
            flick.contentY = _clamp(ny, 0, Math.max(0, nh - flick.height))
        })
    }

    function zoomBy(factor, viewX, viewY) {
        // Legacy parity: arrow up/down zoom. Anchor at (viewX, viewY) when provided,
        // otherwise zoom around the viewport center.
        if (!root.main) return
        var vx = (viewX !== undefined) ? viewX : (flick.width / 2)
        var vy = (viewY !== undefined) ? viewY : (flick.height / 2)
        var base = root.main.fitMode ? root._fitScale() : root.main.zoom
        root.main.fitMode = false
        root._zoomAround(vx, vy, root._clamp(base * factor, 0.05, 20.0))
    }

    function snapToGlobalView() {
        // Legacy parity: Space / middle click.
        if (!root.main) return
        root.main.fitMode = true
        flick.contentX = 0
        flick.contentY = 0
    }

    WheelHandler {
        id: wheelHandler
        onWheel: function(wheel) {
            if (!root.main) return
            var angle = wheel.angleDelta ? wheel.angleDelta.y : 0
            if (wheel.modifiers & Qt.ControlModifier) {
                // Ctrl+wheel: zoom
                var factor = angle > 0 ? 1.25 : 0.8
                var base = root.main.fitMode ? root._fitScale() : root.main.zoom
                root.main.fitMode = false
                var newZoom = root._clamp(base * factor, 0.05, 20.0)
                // Cursor-anchored zoom (legacy align-cursor behavior).
                var vx = (wheel.x !== undefined) ? wheel.x : (flick.width / 2)
                var vy = (wheel.y !== undefined) ? wheel.y : (flick.height / 2)
                root._zoomAround(vx, vy, newZoom)
            } else {
                // Wheel: navigate images
                if (angle > 0) {
                    root.main.prevImage()
                } else if (angle < 0) {
                    root.main.nextImage()
                }
            }
            wheel.accepted = true
        }
    }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_A) {
            if (!root.main) return
            root.main.rotateBy(-90)
            event.accepted = true
        } else if (event.key === Qt.Key_D) {
            if (!root.main) return
            root.main.rotateBy(90)
            event.accepted = true
        } else if ((event.modifiers & Qt.ControlModifier) && (event.modifiers & Qt.ShiftModifier)) {
            // Rotation shortcuts (viewer-only)
            if (!root.main) return
            if (event.key === Qt.Key_Left) {
                root.main.rotateBy(-90)
                event.accepted = true
            } else if (event.key === Qt.Key_Right) {
                root.main.rotateBy(90)
                event.accepted = true
            } else if (event.key === Qt.Key_0) {
                root.main.resetRotation()
                event.accepted = true
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor

        Flickable {
            id: flick
            anchors.fill: parent
            contentWidth: imgContainer.width
            contentHeight: imgContainer.height
            clip: true

            Item {
                id: imgContainer
                width: Math.max(flick.width, img.width * img.scale)
                height: Math.max(flick.height, img.height * img.scale)

                Image {
                    id: img
                    anchors.centerIn: parent
                    transformOrigin: Item.Center
                    rotation: root.main ? root.main.rotation : 0

                    // Use optional chaining or null checks to avoid initial load errors
                    width: (root.main && (root.main.fitMode || img.status !== Image.Ready)) ? flick.width : (img.status === Image.Ready ? sourceSize.width * (root.main ? root.main.zoom : 1.0) : flick.width)
                    height: (root.main && (root.main.fitMode || img.status !== Image.Ready)) ? flick.height : (img.status === Image.Ready ? sourceSize.height * (root.main ? root.main.zoom : 1.0) : flick.height)
                    fillMode: Image.PreserveAspectFit

                    asynchronous: true
                    cache: false
                    smooth: true
                    mipmap: root.hqDownscaleEnabled

                    source: root.main ? root.main.imageUrl : ""

                    onStatusChanged: {
                        if (status === Image.Error) {
                            console.log("QML Image Error: " + source)
                        }
                    }

                    // Mouse handling: press-to-zoom (left), right-drag pan, middle-click fit
                    property real zoomSaved: -1
                    property bool fitSaved: false
                    property bool rcDragActive: false
                    property int rcStartX: 0
                    property int rcStartY: 0
                    property real pressZoomMultiplier: (root.main ? root.main.pressZoomMultiplier : 3.0)

                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton | Qt.BackButton | Qt.ForwardButton
                        hoverEnabled: true

                        onPressed: function(mouse) {
                            if (!root.main) return

                            if (mouse.button === Qt.LeftButton) {
                                // Press-to-zoom
                                img.fitSaved = root.main.fitMode

                                var base = img.fitSaved ? root._fitScale() : root.main.zoom
                                img.zoomSaved = base
                                // Force actual mode and apply multiplier
                                root.main.fitMode = false
                                var newZoom = root._clamp(base * img.pressZoomMultiplier, 0.05, 20.0)

                                // Zoom around cursor (legacy align-cursor behavior).
                                var p = mapToItem(flick, mouse.x, mouse.y)
                                root._zoomAround(p.x, p.y, newZoom)
                            } else if (mouse.button === Qt.RightButton) {
                                // Begin right-click drag pan
                                img.rcDragActive = true
                                img.rcStartX = mouse.x
                                img.rcStartY = mouse.y
                            } else if (mouse.button === Qt.MiddleButton) {
                                // Middle-click: snap to global view (fit)
                                root.main.fitMode = true
                                flick.contentX = 0
                                flick.contentY = 0
                            } else if (mouse.button === Qt.BackButton) {
                                // Auxiliary mouse button (legacy XButton1): zoom out
                                var base2 = root.main.fitMode ? root._fitScale() : root.main.zoom
                                root.main.fitMode = false
                                var p2 = mapToItem(flick, mouse.x, mouse.y)
                                root._zoomAround(p2.x, p2.y, root._clamp(base2 * 0.8, 0.05, 20.0))
                            } else if (mouse.button === Qt.ForwardButton) {
                                // Auxiliary mouse button (legacy XButton2): zoom in
                                var base3 = root.main.fitMode ? root._fitScale() : root.main.zoom
                                root.main.fitMode = false
                                var p3 = mapToItem(flick, mouse.x, mouse.y)
                                root._zoomAround(p3.x, p3.y, root._clamp(base3 * 1.25, 0.05, 20.0))
                            }
                        }

                        onPositionChanged: function(mouse) {
                            if (img.rcDragActive) {
                                var dx = mouse.x - img.rcStartX
                                var dy = mouse.y - img.rcStartY
                                flick.contentX = flick.contentX - dx
                                flick.contentY = flick.contentY - dy
                                img.rcStartX = mouse.x
                                img.rcStartY = mouse.y
                            }
                        }

                        onReleased: function(mouse) {
                            if (!root.main) return

                            if (mouse.button === Qt.LeftButton) {
                                // Restore zoom
                                if (img.zoomSaved >= 0) {
                                    if (img.fitSaved) {
                                        root.main.fitMode = true
                                        flick.contentX = 0
                                        flick.contentY = 0
                                    } else {
                                        root.main.fitMode = false
                                        root.main.zoom = img.zoomSaved
                                    }
                                    img.zoomSaved = -1
                                    img.fitSaved = false
                                }
                            } else if (mouse.button === Qt.RightButton) {
                                img.rcDragActive = false
                            }
                        }
                    }
                }
            }
        }

        // Overlay info
        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.margins: 10
            color: "#80000000"
            radius: 4
            width: infoText.width + 20
            height: infoText.height + 10

            Text {
                id: infoText
                anchors.centerIn: parent
                color: "white"
                text: {
                    if (!root.main) return ""
                    if (root.main.statusOverlayText) return root.main.statusOverlayText
                    if (root.main.currentPath) return root.main.currentPath.replace(/^.*[\\/]/, "")
                    return "No Image"
                }
                font.pixelSize: 12
            }
        }
    }

}
