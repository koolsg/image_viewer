/*
 ViewerPage.qml — 단일 이미지 표시 및 팬/줌/fit 동작을 처리하는 뷰어 페이지 컴포넌트.
 존재 이유: 이미지 뷰 모드의 렌더링과 상호작용(확대/팬/회전 등)을 캡슐화하기 위해 분리되어 있습니다.
*/

import QtQuick
import "."

Item {
    id: root

    // Python facade (BackendFacade) injected from App.qml.
    property var backend: null
    property var theme: null
    property color backgroundColor: "#1a1a1a"
    property bool hqDownscaleEnabled: false
    focus: true

    // Viewer-local shortcuts moved to ViewerShortcuts.qml
    ViewerShortcuts {
        backend: root.backend
    }




    function _clamp(v, lo, hi) {
        return Math.max(lo, Math.min(hi, v))
    }

    function _fitScale() {
        if (!root.backend) return 1.0
        if (img.status !== Image.Ready) return 1.0
        if (img.sourceSize.width <= 0 || img.sourceSize.height <= 0) return 1.0
        var sx = flick.width / img.sourceSize.width
        var sy = flick.height / img.sourceSize.height
        return Math.min(sx, sy)
    }

    function _zoomAround(viewX, viewY, newZoom) {

        if (!root.backend) return
        if (img.status !== Image.Ready) {
            root.backend.dispatch("setZoom", { value: newZoom })
            return
        }

        var oldW = flick.contentWidth
        var oldH = flick.contentHeight
        var cx = flick.contentX + viewX
        var cy = flick.contentY + viewY
        var rx = oldW > 0 ? (cx / oldW) : 0.5
        var ry = oldH > 0 ? (cy / oldH) : 0.5

    root.backend.dispatch("setZoom", { value: newZoom })

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
        if (!root.backend) return
        var vx = (viewX !== undefined) ? viewX : (flick.width / 2)
        var vy = (viewY !== undefined) ? viewY : (flick.height / 2)
        var base = root.backend.viewer.fitMode ? root._fitScale() : root.backend.viewer.zoom
        root._zoomAround(vx, vy, root._clamp(base * factor, 0.05, 20.0))
    }

    function snapToGlobalView() {
        if (!root.backend) return
        root.backend.dispatch("setFitMode", { value: true })
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
                    rotation: root.backend ? root.backend.viewer.rotation : 0


                    width: (root.backend && (root.backend.viewer.fitMode || img.status !== Image.Ready)) ? flick.width : (img.status === Image.Ready ? sourceSize.width * (root.backend ? root.backend.viewer.zoom : 1.0) : flick.width)
                    height: (root.backend && (root.backend.viewer.fitMode || img.status !== Image.Ready)) ? flick.height : (img.status === Image.Ready ? sourceSize.height * (root.backend ? root.backend.viewer.zoom : 1.0) : flick.height)
                    fillMode: Image.PreserveAspectFit

                    asynchronous: true
                    cache: false
                    smooth: true
                    mipmap: root.hqDownscaleEnabled

                    source: root.backend ? root.backend.viewer.imageUrl : ""

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
                    property real pressZoomMultiplier: (root.backend ? root.backend.settings.pressZoomMultiplier : 3.0)


                }
            }
        }


        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.margins: 16
            color: root.theme ? Qt.rgba(root.theme.surface.r, root.theme.surface.g, root.theme.surface.b, 0.7) : "#80000000"
            radius: root.theme ? root.theme.radiusMedium : 4
            width: infoText.width + 24
            height: infoText.height + 12
            border.color: root.theme ? root.theme.border : "transparent"
            border.width: root.theme ? 1 : 0

            Text {
                id: infoText
                anchors.centerIn: parent
                color: root.theme ? root.theme.text : "white"
                text: {
                    if (!root.backend) return ""
                    if (root.backend.viewer.statusOverlayText) return root.backend.viewer.statusOverlayText
                    if (root.backend.viewer.currentPath) return root.backend.viewer.currentPath.replace(/^.*[\\/]/, "")
                    return "No Image"
                }
                font.pixelSize: 13
                font.bold: true
            }
        }
    }

}
