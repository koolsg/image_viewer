/*
 MenuTest.qml — 메뉴/타이틀바/리사이즈 동작을 빠르게 재현하기 위한 최소 테스트 윈도우.
 사용 목적: 헤더/메뉴 관련 동작을 격리해 실험하거나 디버깅하기 위해 존재합니다.
*/

import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "."

ApplicationWindow {
    id: root
    width: 900
    height: 600
    visible: true
    title: "test"
    flags: Qt.Window | Qt.FramelessWindowHint

    Theme {
        id: theme
    }

    // Same startup guard we use in the main app: avoid starting a system-move
    // before the first frame is shown.
    property bool _inputReady: false
    Component.onCompleted: Qt.callLater(function() { root._inputReady = true })

    // In frameless mode, the OS title bar is gone by definition.
    // Provide a tiny custom title bar so we can still see the window title.
    header: Column {
        width: root.width
        spacing: 0

        Rectangle {
            id: titleBar
            width: parent.width
            height: 32
            color: theme.surface
            z: 1000

            // NOTE (Windows): Enabling a layer here can cause visible trailing/lag during
            // startSystemMove() window drags (the title bar appears to "chase" the window).
            // Keep it disabled for responsive, artifact-free dragging.
            layer.enabled: false

            // Drag region (exclude buttons)
            Item {
                anchors.left: parent.left
                anchors.right: windowButtons.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom

                DragHandler {
                    acceptedButtons: Qt.LeftButton
                    enabled: root._inputReady
                    onActiveChanged: if (active) root.startSystemMove()
                }

                // Typical Windows behavior: double-click title bar toggles maximize/restore.
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

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.title
                    color: theme.text
                    font.pixelSize: 12
                }
            }

            Row {
                id: windowButtons
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                spacing: 0

                Button {
                    id: minBtn
                    width: 46
                    height: parent.height
                    flat: true
                    hoverEnabled: true
                    background: Rectangle {
                        anchors.fill: parent
                        color: minBtn.hovered ? theme.hover : "transparent"
                    }
                    contentItem: Text {
                        anchors.fill: parent
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
                        anchors.fill: parent
                        color: maxBtn.hovered ? theme.hover : "transparent"
                    }
                    contentItem: Text {
                        anchors.fill: parent
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
                        anchors.fill: parent
                        color: closeBtn.hovered ? "#E81123" : "transparent"
                    }
                    contentItem: Text {
                        anchors.fill: parent
                        text: "✕"
                        color: closeBtn.hovered ? "#FFFFFF" : theme.text
                        font.pixelSize: 14
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: Qt.quit()
                }
            }

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 3
                color: theme.border
            }
        }

        // Menu row directly under the title bar
        MenuBar {
            id: testMenuBar
            width: parent.width
            implicitHeight: 30
            height: implicitHeight
            z: 2000
            background: Rectangle {
                color: theme.surface
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 3
                    color: theme.border
                }
            }

            Menu { title: "File"; MenuItem { text: "(noop)" } }
            Menu { title: "View"; MenuItem { text: "(noop)" } }
            Menu { title: "Help"; MenuItem { text: "(noop)" } }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: theme.background

        Text {
            anchors.centerIn: parent
            text: "MenuBar test: File | View | Help"
            color: theme.text
            font.pixelSize: 18
        }
    }

    // --- Resize Handles (frameless windows have no native resize border) ---
    // Parent to Overlay.overlay so they sit at the true window edge (above header).
    MouseArea {
        id: topResize
        parent: Overlay.overlay
        height: 6; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
        cursorShape: Qt.SizeVerCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.TopEdge)
    }
    MouseArea {
        id: bottomResize
        parent: Overlay.overlay
        height: 6; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
        cursorShape: Qt.SizeVerCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.BottomEdge)
    }
    MouseArea {
        id: leftResize
        parent: Overlay.overlay
        width: 6; anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
        cursorShape: Qt.SizeHorCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.LeftEdge)
    }
    MouseArea {
        id: rightResize
        parent: Overlay.overlay
        width: 6; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
        cursorShape: Qt.SizeHorCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.RightEdge)
    }
    MouseArea {
        id: topLeftResize
        parent: Overlay.overlay
        width: 10; height: 10; anchors.left: parent.left; anchors.top: parent.top
        cursorShape: Qt.SizeFDiagCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.TopEdge | Qt.LeftEdge)
    }
    MouseArea {
        id: topRightResize
        parent: Overlay.overlay
        width: 10; height: 10; anchors.right: parent.right; anchors.top: parent.top
        cursorShape: Qt.SizeBDiagCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.TopEdge | Qt.RightEdge)
    }
    MouseArea {
        id: bottomLeftResize
        parent: Overlay.overlay
        width: 10; height: 10; anchors.left: parent.left; anchors.bottom: parent.bottom
        cursorShape: Qt.SizeBDiagCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.BottomEdge | Qt.LeftEdge)
    }
    MouseArea {
        id: bottomRightResize
        parent: Overlay.overlay
        width: 10; height: 10; anchors.right: parent.right; anchors.bottom: parent.bottom
        cursorShape: Qt.SizeFDiagCursor
        enabled: root.visibility !== Window.Maximized
        onPressed: root.startSystemResize(Qt.BottomEdge | Qt.RightEdge)
    }
}
