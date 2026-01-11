/*
 DeleteConfirmationDialog.qml — 파일 삭제 확인을 위한 표준 모달 다이얼로그.
 존재 이유: 삭제 전 사용자 확인과 재활용휴지통으로 이동 같은 공통 동작을 일관되게 처리하기 위해 존재합니다.
*/

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Dialog {
    id: dlg
    modal: true
    dim: true
    focus: true
    // Do not close when user clicks outside; keep it open and modal.
    closePolicy: Popup.NoAutoClose
    property alias titleText: titleLabel.text
    property alias infoText: infoLabel.text
    property var payload: null
    property var theme: null

    // Ensure the dialog is on top within its parent and centers itself when parent is set.
    z: 10000
    x: parent ? Math.round((parent.width - width) / 2) : x
    y: parent ? Math.round((parent.height - height) / 2) : y
    width: Math.max(400, Math.min(760, (infoText.length * 6) + 240))

    // Use dialog padding instead of anchoring the contentItem to the dialog.
    // Anchored content items don't contribute to implicit sizing and can overflow.
    padding: 24

    function _acceptNow() {
        dlg.acceptedWithPayload(dlg.payload)
        dlg.close()
    }

    function _rejectNow() {
        dlg.rejectedWithPayload(dlg.payload)
        dlg.close()
    }

    function _activateFocusedButton() {
        if (noButton.activeFocus) dlg._rejectNow()
        else dlg._acceptNow()
    }

    // Keyboard behavior:
    // - Enter: activate the currently-focused button
    // - Esc: close immediately (no signals)
    // - Y/N: Yes/No (activate)
    // - Left/Right: move focus between Yes/No (do not activate)

    Shortcut {
        sequence: "Escape"
        enabled: dlg.visible
        context: Qt.WindowShortcut
        onActivated: dlg.close()
    }

    Shortcut {
        sequence: "Y"
        enabled: dlg.visible
        onActivated: dlg._acceptNow()
    }

    Shortcut {
        sequence: "N"
        enabled: dlg.visible
        onActivated: dlg._rejectNow()
    }

    // Some Qt Quick Controls setups may not deliver Return/Enter to Keys handlers
    // on a modal Popup reliably when a Control has focus. These shortcuts ensure
    // Enter/Return always triggers the focused action.
    Shortcut {
        sequence: "Return"
        enabled: dlg.visible
        context: Qt.WindowShortcut
        onActivated: dlg._activateFocusedButton()
    }

    Shortcut {
        sequence: "Enter"
        enabled: dlg.visible
        context: Qt.WindowShortcut
        onActivated: dlg._activateFocusedButton()
    }

    // Allow user to drag the dialog by a small header area
    property bool draggable: true
    property real _dragStartX: 0
    property real _dragStartY: 0

    background: Rectangle {
        id: bg
        color: dlg.theme ? dlg.theme.surface : "#121212"
        radius: dlg.theme ? dlg.theme.radiusLarge : 8
        border.color: dlg.theme ? dlg.theme.border : "#303030"
        border.width: 1

        // Subtle shadow effect
        layer.enabled: true

        // draggable header
        Rectangle {
            id: headerBar
            anchors.left: parent.left
            anchors.right: parent.right
            height: 28
            color: Qt.rgba(0,0,0,0)

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.ClosedHandCursor
                onPressed: function(mouse) {
                    if (!dlg.draggable) return
                    dlg._dragStartX = mouse.x
                    dlg._dragStartY = mouse.y
                }
                onPositionChanged: function(mouse) {
                    if (!dlg.draggable) return
                    var nx = dlg.x + (mouse.x - dlg._dragStartX)
                    var ny = dlg.y + (mouse.y - dlg._dragStartY)
                    // Clamp to parent bounds if possible
                    if (dlg.parent) {
                        nx = Math.max(0, Math.min(nx, dlg.parent.width - dlg.width))
                        ny = Math.max(0, Math.min(ny, dlg.parent.height - dlg.height))
                    }
                    dlg.x = nx
                    dlg.y = ny
                }
            }
        }
    }

    contentItem: ColumnLayout {
        id: mainCol
        width: dlg.availableWidth
        spacing: 20

        // Wrap textual content in a ScrollView so long messages do not push
        // the action buttons outside of the dialog bounds.
        ScrollView {
            Layout.fillWidth: true
            // Constrain preferred height to a reasonable maximum to avoid overly tall dialogs
            // while still allowing most messages to fit without scrolling.
            Layout.preferredHeight: Math.min(480, Math.max(120, textContent.implicitHeight))
            clip: true

            contentItem: Flickable {
                id: flick
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                contentWidth: flick.width
                contentHeight: textContent.implicitHeight

                ColumnLayout {
                    id: textContent
                    width: flick.width
                    spacing: 8

                    Label {
                        id: titleLabel
                        text: ""
                        font.pixelSize: 18
                        font.bold: true
                        wrapMode: Text.Wrap
                        color: dlg.theme ? dlg.theme.text : "#ffffff"
                    }

                    Label {
                        id: infoLabel
                        text: ""
                        font.pixelSize: 14
                        wrapMode: Text.WordWrap
                        color: dlg.theme ? dlg.theme.textDim : "#bdbdbd"
                        lineHeight: 1.2
                    }
                }
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            Layout.fillWidth: true
            spacing: 12

            Button {
                id: yesButton
                text: qsTr("Yes (Y)")
                KeyNavigation.right: noButton
                implicitWidth: 100
                implicitHeight: 36
                contentItem: Label {
                    text: yesButton.text
                    font: yesButton.font
                    color: "white"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    anchors.fill: parent
                    color: (yesButton.hovered || yesButton.activeFocus) ? Qt.lighter("#d32f2f", 1.15) : "#d32f2f"
                    border.color: yesButton.activeFocus ? (dlg.theme ? dlg.theme.selectionBorder : "#ffffff") : "transparent"
                    border.width: yesButton.activeFocus ? 2 : 0
                    radius: dlg.theme ? dlg.theme.radiusSmall : 4
                }
                onClicked: dlg._acceptNow()
                focus: true
            }

            Button {
                id: noButton
                text: qsTr("No (N)")
                KeyNavigation.left: yesButton
                implicitWidth: 100
                implicitHeight: 36
                contentItem: Label {
                    text: noButton.text
                    font: noButton.font
                    color: dlg.theme ? dlg.theme.text : "white"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    anchors.fill: parent
                    color: (noButton.hovered || noButton.activeFocus) ? (dlg.theme ? dlg.theme.hover : "#2a2a2a") : "transparent"
                    border.color: noButton.activeFocus ? (dlg.theme ? dlg.theme.selectionBorder : "#ffffff") : (dlg.theme ? dlg.theme.border : "#333333")
                    border.width: noButton.activeFocus ? 2 : 1
                    radius: dlg.theme ? dlg.theme.radiusSmall : 4
                }
                onClicked: dlg._rejectNow()
            }
        }
    }

    signal acceptedWithPayload(var payload)
    signal rejectedWithPayload(var payload)
}
