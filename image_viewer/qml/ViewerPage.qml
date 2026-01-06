import QtQuick 2.15

Item {
    id: root
    // NOTE: This is set from Python via rootObject().setProperty("main", ...)
    // so we can avoid QML global/context-property access (qmllint UnqualifiedAccess).
    property var main: null
    focus: true

    WheelHandler {
        id: wheelHandler
        onWheel: function(wheel) {
            if (!root.main) return
            var angle = wheel.angleDelta ? wheel.angleDelta.y : 0
            if (wheel.modifiers & Qt.ControlModifier) {
                // Ctrl+wheel: zoom
                var factor = angle > 0 ? 1.25 : 0.8
                root.main.fitMode = false
                var newZoom = Math.max(0.05, Math.min(20.0, root.main.zoom * factor))
                root.main.zoom = newZoom
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

    Keys.onRightPressed: {
        if (root.main) root.main.nextImage()
    }
    Keys.onLeftPressed: {
        if (root.main) root.main.prevImage()
    }
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Home) {
            if (root.main) root.main.firstImage()
            event.accepted = true
        } else if (event.key === Qt.Key_End) {
            if (root.main) root.main.lastImage()
            event.accepted = true
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Escape) {
            if (root.main) root.main.closeView()
            event.accepted = true
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "#1a1a1a"

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

                    // Use optional chaining or null checks to avoid initial load errors
                    width: (root.main && (root.main.fitMode || img.status !== Image.Ready)) ? flick.width : (img.status === Image.Ready ? sourceSize.width * (root.main ? root.main.zoom : 1.0) : flick.width)
                    height: (root.main && (root.main.fitMode || img.status !== Image.Ready)) ? flick.height : (img.status === Image.Ready ? sourceSize.height * (root.main ? root.main.zoom : 1.0) : flick.height)
                    fillMode: Image.PreserveAspectFit

                    asynchronous: true
                    cache: false
                    smooth: true
                    mipmap: true

                    source: root.main ? root.main.imageUrl : ""

                    onStatusChanged: {
                        if (status === Image.Error) {
                            console.log("QML Image Error: " + source)
                        }
                    }

                    // Mouse handling: press-to-zoom (left), right-drag pan, middle-click fit
                    property real zoomSaved: -1
                    property bool rcDragActive: false
                    property int rcStartX: 0
                    property int rcStartY: 0
                    property real pressZoomMultiplier: 3.0

                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                        hoverEnabled: true

                        onPressed: function(mouse) {
                            if (!root.main) return

                            if (mouse.button === Qt.LeftButton) {
                                // Press-to-zoom
                                img.zoomSaved = root.main.zoom
                                // Force actual mode and apply multiplier
                                root.main.fitMode = false
                                var base = (img.zoomSaved && img.zoomSaved > 0) ? img.zoomSaved : 1.0
                                root.main.zoom = base * img.pressZoomMultiplier
                            } else if (mouse.button === Qt.RightButton) {
                                // Begin right-click drag pan
                                img.rcDragActive = true
                                img.rcStartX = mouse.x
                                img.rcStartY = mouse.y
                            } else if (mouse.button === Qt.MiddleButton) {
                                // Middle-click: snap to global view (fit)
                                root.main.fitMode = true
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
                                    root.main.zoom = img.zoomSaved
                                    img.zoomSaved = -1
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
                text: "QML POC: " + (root.main && root.main.currentPath ? root.main.currentPath.replace(/^.*[\\/]/, "") : "No Image")
                font.pixelSize: 12
            }
        }
    }
}
