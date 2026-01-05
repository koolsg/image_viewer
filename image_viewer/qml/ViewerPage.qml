import QtQuick 2.15

Item {
    id: root
    // NOTE: This is set from Python via rootObject().setProperty("appController", ...)
    // so we can avoid QML global/context-property access (qmllint UnqualifiedAccess).
    property var appController: null
    focus: true

    Keys.onRightPressed: {
        if (root.appController) root.appController.nextImage()
    }
    Keys.onLeftPressed: {
        if (root.appController) root.appController.prevImage()
    }
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Home) {
            if (root.appController) root.appController.firstImage()
            event.accepted = true
        } else if (event.key === Qt.Key_End) {
            if (root.appController) root.appController.lastImage()
            event.accepted = true
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Escape) {
            if (root.appController) root.appController.closeViewWindow()
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
                    width: (root.appController && (root.appController.fitMode || img.status !== Image.Ready)) ? flick.width : (img.status === Image.Ready ? sourceSize.width * (root.appController ? root.appController.zoom : 1.0) : flick.width)
                    height: (root.appController && (root.appController.fitMode || img.status !== Image.Ready)) ? flick.height : (img.status === Image.Ready ? sourceSize.height * (root.appController ? root.appController.zoom : 1.0) : flick.height)
                    fillMode: Image.PreserveAspectFit

                    asynchronous: true
                    cache: false
                    smooth: true
                    mipmap: true

                    source: root.appController ? root.appController.imageUrl : ""

                    onStatusChanged: {
                        if (status === Image.Error) {
                            console.log("QML Image Error: " + source)
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
                text: "QML POC: " + (root.appController && root.appController.currentPath ? root.appController.currentPath.replace(/^.*[\\/]/, "") : "No Image")
                font.pixelSize: 12
            }
        }
    }
}
