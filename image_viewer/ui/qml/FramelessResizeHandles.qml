/*
 FramelessResizeHandles.qml — 프레임리스 윈도우의 가장자리/코너 리사이즈 핸들 모음.
 이 파일은 Overlay.overlay에 부모를 붙여 창의 실제 바깥 가장자리에 맞게 리사이즈 영역을 배치합니다.
*/

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window

Item {
    id: root

    // Owning window and overlay parent (pass Overlay.overlay from the window)
    property var app
    property var overlayParent: null

    // Bottom edge
    MouseArea {
        id: bottomResize
        parent: root.overlayParent
        height: 6
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        cursorShape: Qt.SizeVerCursor
        enabled: !!root.app && root.app.visibility !== Window.Maximized
        onPressed: if (root.app) root.app.startSystemResize(Qt.BottomEdge)
    }

    // Left edge
    MouseArea {
        id: leftResize
        parent: root.overlayParent
        width: 6
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        cursorShape: Qt.SizeHorCursor
        enabled: !!root.app && root.app.visibility !== Window.Maximized
        onPressed: if (root.app) root.app.startSystemResize(Qt.LeftEdge)
    }

    // Right edge
    MouseArea {
        id: rightResize
        parent: root.overlayParent
        width: 6
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        cursorShape: Qt.SizeHorCursor
        enabled: !!root.app && root.app.visibility !== Window.Maximized
        onPressed: if (root.app) root.app.startSystemResize(Qt.RightEdge)
    }

    // Bottom-left corner
    MouseArea {
        id: bottomLeftResize
        parent: root.overlayParent
        width: 10
        height: 10
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        cursorShape: Qt.SizeBDiagCursor
        enabled: !!root.app && root.app.visibility !== Window.Maximized
        onPressed: if (root.app) root.app.startSystemResize(Qt.BottomEdge | Qt.LeftEdge)
    }

    // Bottom-right corner
    MouseArea {
        id: bottomRightResize
        parent: root.overlayParent
        width: 10
        height: 10
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        cursorShape: Qt.SizeFDiagCursor
        enabled: !!root.app && root.app.visibility !== Window.Maximized
        onPressed: if (root.app) root.app.startSystemResize(Qt.BottomEdge | Qt.RightEdge)
    }
}
