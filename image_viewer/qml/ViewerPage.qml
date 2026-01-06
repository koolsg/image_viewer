import QtQuick 2.15

Item {
    id: root

    property var main: null
    property color backgroundColor: "#1a1a1a"
    property bool hqDownscaleEnabled: false
    focus: true


    Keys.onReturnPressed: {
        if (!root.main) return
        root.main.closeView()
    }
    Keys.onEscapePressed: {
        if (!root.main) return
        root.main.closeView()
    }




    function _clamp(v, lo, hi) {
        return Math.max(lo, Math.min(hi, v))
    }

    function _fitScale() {
        if (!root.main) return 1.0
        if (img.status !== Image.Ready) return 1.0
        if (img.sourceSize.width <= 0 || img.sourceSize.height <= 0) return 1.0
        var sx = flick.width / img.sourceSize.width
        var sy = flick.height / img.sourceSize.height
        return Math.min(sx, sy)
    }

    function _zoomAround(viewX, viewY, newZoom) {


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
        if (!root.main) return
        var vx = (viewX !== undefined) ? viewX : (flick.width / 2)
        var vy = (viewY !== undefined) ? viewY : (flick.height / 2)
        var base = root.main.fitMode ? root._fitScale() : root.main.zoom
        root.main.fitMode = false
        root._zoomAround(vx, vy, root._clamp(base * factor, 0.05, 20.0))
    }

    function snapToGlobalView() {
        if (!root.main) return
        root.main.fitMode = true
        flick.contentX = 0
        flick.contentY = 0
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


                    property real zoomSaved: -1
                    property bool fitSaved: false
                    property bool rcDragActive: false
                    property int rcStartX: 0
                    property int rcStartY: 0
                    property real pressZoomMultiplier: (root.main ? root.main.pressZoomMultiplier : 3.0)


                }
            }
        }


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
