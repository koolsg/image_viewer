/*
 AppDialogs.qml — 앱에서 사용하는 모달/보조 다이얼로그 모음.
 이 파일은 폴더 선택, 삭제 확인, 이름 변경, WebP 변환 등 다이얼로그 관련 로직을 중앙화하여 App.qml을 단순화하기 위해 존재합니다.
*/

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "."

Item {
    id: dialogs

    // The owning window injects these.
    property var backend: null
    required property Theme theme
    // Optional: pass Overlay.overlay from the owning ApplicationWindow.
    // Using the overlay ensures Qt Quick Controls can enforce modality correctly.
    property var overlayParent: null

    function openFolderDialogAtLastParent() {
        // Start the FolderDialog at the parent directory of the last opened folder.
        // QtQuick.Dialogs expects a file:/// URL.
        var base = (dialogs.backend && dialogs.backend.explorer && dialogs.backend.explorer.currentFolder)
            ? ("" + dialogs.backend.explorer.currentFolder)
            : "";
        if (!base) {
            folderDialog.open();
            return;
        }

        // Avoid regex literals here; qmllint can be picky about escapes.
        var p = base.split("\\").join("/");
        // trim trailing slashes
        while (p.length > 3 && p.endsWith("/")) p = p.slice(0, -1);
        var lastSlash = p.lastIndexOf("/");
        var parent = (lastSlash > 0) ? p.slice(0, lastSlash) : p;
        if (parent.endsWith(":")) parent = parent + "/";

        folderDialog.currentFolder = "file:///" + parent;
        folderDialog.open();
    }

    function showDeleteDialog(title, text, info, payload) {
        deleteDialog.titleText = title;
        deleteDialog.infoText = info;
        deleteDialog.payload = (typeof payload === "undefined") ? null : payload;
        deleteDialog.open();
    }

    function openRenameDialog(oldPath, initialName) {
        renameDialog.oldPath = oldPath ? ("" + oldPath) : "";
        renameDialog.initialName = initialName ? ("" + initialName) : "";
        renameDialog.open();
    }

    function showInfo(title, text) {
        infoDialog.title = title;
        infoDialog.text = text;
        infoDialog.open();
    }

    function openWebPDialog() {
        webpDialog.open()
    }

    function openBackgroundColorDialog() {
        bgColorDialog.open()
    }

    FolderDialog {
        id: folderDialog
        title: "Choose a folder"
        onAccepted: {
            if (!dialogs.backend) return
            dialogs.backend.dispatch("openFolder", { path: folderDialog.selectedFolder.toString() })
        }
    }

    ConvertWebPDialog {
        id: webpDialog
        backend: dialogs.backend
        theme: dialogs.theme
    }

    ColorDialog {
        id: bgColorDialog
        title: "Choose background color"
        onAccepted: {
            if (!dialogs.backend) return
            dialogs.backend.dispatch("setBackgroundColor", { color: bgColorDialog.selectedColor })
        }
    }

    MessageDialog {
        id: infoDialog
        title: "Info"
        text: ""
    }

    DeleteConfirmationDialog {
        id: deleteDialog
        theme: dialogs.theme
        // Ensure dialog receives focus when opened
        onOpened: {
            Qt.callLater(function() { deleteDialog.forceActiveFocus() })
        }
    }

    Dialog {
        id: renameDialog
        // Parent will be set by the caller's window; keep it null-safe.
        parent: null
        modal: true
        focus: true
        title: "Rename"
        standardButtons: Dialog.Ok | Dialog.Cancel

        property string oldPath: ""
        property string initialName: ""  // Store the initial filename to populate

        // Keep the dialog centered (avoids "top-left corner" placement issues)
        x: Math.round(((parent ? parent.width : 0) - width) / 2)
        y: Math.round(((parent ? parent.height : 0) - height) / 2)

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 10

            TextField {
                id: renameField
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                selectByMouse: true
                focus: true
                text: renameDialog.initialName

                padding: 8
                font.pixelSize: 14

                color: dialogs.theme.text
                selectionColor: dialogs.theme.accent
                selectedTextColor: dialogs.theme.surface
                cursorDelegate: Rectangle {
                    width: 1
                    color: dialogs.theme.accent
                }
                background: Rectangle {
                    radius: dialogs.theme.radiusSmall
                    color: dialogs.theme.hover
                    border.color: dialogs.theme.border
                    border.width: 1
                    implicitHeight: 36
                }

                Keys.onReturnPressed: function(event) {
                    // Pressing Enter confirms the rename (same as clicking OK)
                    renameDialog.accept()
                    event.accepted = true
                }
            }
        }

        onOpened: {
            // Focus + select full filename (including extension), Windows-style.
            renameDialog.forceActiveFocus()
            renameField.forceActiveFocus()
            Qt.callLater(function() { renameField.selectAll() })
        }

        onAccepted: {
            if (!dialogs.backend) return
            if (!oldPath) return
            dialogs.backend.dispatch("renameFile", { path: oldPath, newName: renameField.text })
        }
    }

    Component.onCompleted: {
        // Ensure the rename dialog is attached to the window content area so it centers correctly.
        // This must run after the component is instantiated under the owning window.
        Qt.callLater(function() {
            var w = dialogs.Window.window
            if (!w) return

            // Prefer overlay parenting so Dialog modality works (blocks background input)
            // and dimming is handled by Controls.
            var p = dialogs.overlayParent
            if (!p && w.contentItem) p = w.contentItem
            if (!p) return

            renameDialog.parent = p
            if (deleteDialog) deleteDialog.parent = p
        })

        deleteDialog.acceptedWithPayload.connect(function(p) {
            if (!dialogs.backend) return
            dialogs.backend.dispatch("deleteFiles", { paths: (Array.isArray(p) ? p : [p]) })
        })
    }
}
