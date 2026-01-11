/*
 ViewWindow.qml — 이미지 뷰 모드를 위한 별도 Window 컨테이너.
 이 파일은 ViewerPage를 호스트하고 전체화면 전환, 포커스 복원, 뷰 전용 삭제 확인 등을 처리합니다.
*/

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import "."

Window {
    id: viewWindow

    required property var backend
    required property Theme theme
    required property bool hqDownscaleEnabled

    // Let the owning window decide how to restore focus when this view hides.
    signal requestRestoreMainFocus()

    // Optional logging hook. Owner can override by assigning `log = root.qmlDebugSafe`.
    function log(msg) {
        console.log(String(msg))
    }

    title: "View"
    visibility: (backend && backend.viewer && backend.viewer.viewMode) ? Window.FullScreen : Window.Hidden
    color: (backend && backend.settings) ? backend.settings.backgroundColor : theme.background

    onVisibleChanged: {
        log("viewWindow.onVisibleChanged: visible=" + visible)
        if (visible) {
            viewWindow.requestActivate()
            Qt.callLater(function() {
                viewFocus.forceActiveFocus()
                if (backend && backend.crop && backend.crop.active) cropPage.forceActiveFocus()
                else viewerPage.forceActiveFocus()
            })
        } else {
            log("viewWindow.onVisibleChanged: hiding, requesting main focus restore")
            requestRestoreMainFocus()
        }
    }

    onClosing: function(close) {
        log("viewWindow.onClosing requested")
        if (backend) backend.dispatch("closeView", null)
        close.accepted = false
    }

    DeleteConfirmationDialog {
        id: viewDeleteDialog
        theme: theme
    }

    function showViewDeleteDialog(path) {
        viewDeleteDialog.titleText = "Delete File"
        viewDeleteDialog.infoText = (path ? (path.replace(/^.*[\\/]/, "") + "\n\nIt will be moved to Recycle Bin.") : "")
        viewDeleteDialog.payload = (typeof path === "undefined") ? null : path
        viewDeleteDialog.open()
    }

    Component.onCompleted: {
        viewDeleteDialog.acceptedWithPayload.connect(function(p) {
            if (!backend) return
            backend.dispatch("deleteFiles", { paths: (Array.isArray(p) ? p : [p]) })
        })
    }

    FocusScope {
        id: viewFocus
        anchors.fill: parent
        focus: true

        ViewerPage {
            id: viewerPage
            anchors.fill: parent
            backend: viewWindow.backend
            theme: viewWindow.theme
            backgroundColor: (viewWindow.backend && viewWindow.backend.settings) ? viewWindow.backend.settings.backgroundColor : viewWindow.theme.background
            hqDownscaleEnabled: viewWindow.hqDownscaleEnabled
            visible: !(viewWindow.backend && viewWindow.backend.crop && viewWindow.backend.crop.active)
            enabled: visible
        }

        CropPage {
            id: cropPage
            anchors.fill: parent
            backend: viewWindow.backend
            theme: viewWindow.theme
            visible: (viewWindow.backend && viewWindow.backend.crop && viewWindow.backend.crop.active)
            enabled: visible
        }
    }
}
