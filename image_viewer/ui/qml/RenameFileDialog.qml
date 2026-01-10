/*
 RenameFileDialog.qml — 파일/폴더 이름 변경을 위한 표준 모달 다이얼로그.
 존재 이유: Explorer의 F2 Rename 동작에서 사용하는 UI/키보드 포커스/레이아웃을 AppDialogs.qml에서 분리해 재사용 가능하고 유지보수하기 쉽게 하기 위해 존재합니다.

 디자인/동작은 DeleteConfirmationDialog.qml의 패턴(모달+dim, padding 기반 레이아웃, 명시적 포커스 제어)을 참고합니다.
*/

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dlg

    modal: true
    dim: true
    focus: true
    Keys.priority: Keys.BeforeItem
    closePolicy: Popup.NoAutoClose

    property var theme: null

    // Inputs
    property string oldPath: ""
    property string initialName: ""

    // Output
    signal acceptedWithPayload(var payload)

    // Keep dialog on top within its parent and centered when parent is set.
    z: 10000
    x: parent ? Math.round((parent.width - width) / 2) : x
    y: parent ? Math.round((parent.height - height) / 2) : y

    width: Math.max(420, Math.min(760, (initialName.length * 7) + 360))
    padding: 24

    function _acceptNow() {
        if (!dlg.oldPath) {
            dlg.close()
            return
        }
        dlg.acceptedWithPayload({ path: dlg.oldPath, newName: renameField.text })
        dlg.close()
    }

    Keys.onEscapePressed: function(event) {
        dlg.close()
        event.accepted = true
    }

    background: Rectangle {
        color: dlg.theme ? dlg.theme.surface : "#121212"
        radius: dlg.theme ? dlg.theme.radiusLarge : 8
        border.color: dlg.theme ? dlg.theme.border : "#303030"
        border.width: 1
        layer.enabled: true
    }

    contentItem: ColumnLayout {
        width: dlg.availableWidth
        spacing: 16

        Label {
            text: qsTr("Rename")
            font.pixelSize: 18
            font.bold: true
            wrapMode: Text.Wrap
            color: dlg.theme ? dlg.theme.text : "#ffffff"
        }

        TextField {
            id: renameField
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            selectByMouse: true
            focus: true
            text: dlg.initialName

            padding: 8
            font.pixelSize: 14

            color: dlg.theme ? dlg.theme.text : "#ffffff"
            selectionColor: dlg.theme ? dlg.theme.accent : "#4da3ff"
            selectedTextColor: dlg.theme ? dlg.theme.surface : "#121212"
            cursorDelegate: Rectangle {
                width: 1
                color: dlg.theme ? dlg.theme.accent : "#4da3ff"
            }
            background: Rectangle {
                radius: dlg.theme ? dlg.theme.radiusSmall : 4
                color: dlg.theme ? dlg.theme.hover : "#2a2a2a"
                border.color: renameField.activeFocus
                    ? (dlg.theme ? dlg.theme.selectionBorder : "#ffffff")
                    : (dlg.theme ? dlg.theme.border : "#333333")
                border.width: renameField.activeFocus ? 2 : 1
                implicitHeight: 36
            }

            Keys.onReturnPressed: function(event) {
                dlg._acceptNow()
                event.accepted = true
            }
            Keys.onEnterPressed: function(event) {
                dlg._acceptNow()
                event.accepted = true
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            Layout.fillWidth: true
            spacing: 12

            Button {
                id: cancelButton
                text: qsTr("Cancel")
                implicitWidth: 100
                implicitHeight: 36
                onClicked: dlg.close()
                KeyNavigation.right: okButton
                background: Rectangle {
                    anchors.fill: parent
                    color: (cancelButton.hovered || cancelButton.activeFocus)
                        ? (dlg.theme ? dlg.theme.hover : "#2a2a2a")
                        : "transparent"
                    border.color: cancelButton.activeFocus
                        ? (dlg.theme ? dlg.theme.selectionBorder : "#ffffff")
                        : (dlg.theme ? dlg.theme.border : "#333333")
                    border.width: cancelButton.activeFocus ? 2 : 1
                    radius: dlg.theme ? dlg.theme.radiusSmall : 4
                }
            }

            Button {
                id: okButton
                text: qsTr("OK")
                implicitWidth: 100
                implicitHeight: 36
                onClicked: dlg._acceptNow()
                KeyNavigation.left: cancelButton
                background: Rectangle {
                    anchors.fill: parent
                    color: (okButton.hovered || okButton.activeFocus)
                        ? Qt.lighter((dlg.theme ? dlg.theme.accent : "#4da3ff"), 1.10)
                        : (dlg.theme ? dlg.theme.accent : "#4da3ff")
                    border.color: okButton.activeFocus ? (dlg.theme ? dlg.theme.selectionBorder : "#ffffff") : "transparent"
                    border.width: okButton.activeFocus ? 2 : 0
                    radius: dlg.theme ? dlg.theme.radiusSmall : 4
                }
                contentItem: Label {
                    text: okButton.text
                    font: okButton.font
                    color: dlg.theme ? dlg.theme.surface : "#121212"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    onOpened: {
        // Focus + select full filename (including extension)
        dlg.forceActiveFocus()
        renameField.forceActiveFocus()
        Qt.callLater(function() { renameField.selectAll() })
    }
}
