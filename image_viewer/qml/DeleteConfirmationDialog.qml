import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Dialog {
    id: dlg
    modal: true
    property alias titleText: titleLabel.text
    property alias infoText: infoLabel.text
    property var payload: null
    property var theme: null

    x: parent ? (parent.width - width) / 2 : x
    y: parent ? (parent.height - height) / 2 : y
    width: Math.max(400, Math.min(760, (infoText.length * 6) + 240))

    background: Rectangle {
        color: dlg.theme ? dlg.theme.surface : "#121212"
        radius: dlg.theme ? dlg.theme.radiusLarge : 8
        border.color: dlg.theme ? dlg.theme.border : "#303030"
        border.width: 1

        // Subtle shadow effect
        layer.enabled: true
    }

    contentItem: ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 20

        RowLayout {
            spacing: 16
            Layout.fillWidth: true

            ColumnLayout {
                Layout.fillWidth: true
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
                    wrapMode: Text.Wrap
                    color: dlg.theme ? dlg.theme.textDim : "#bdbdbd"
                    lineHeight: 1.2
                }
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 12

            Button {
                id: noButton
                text: qsTr("Cancel")
                contentItem: Label {
                    text: parent.text
                    font: parent.font
                    color: dlg.theme ? dlg.theme.text : "white"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    implicitWidth: 100
                    implicitHeight: 36
                    color: parent.hovered ? (dlg.theme ? dlg.theme.hover : "#2a2a2a") : "transparent"
                    border.color: dlg.theme ? dlg.theme.border : "#333333"
                    border.width: 1
                    radius: dlg.theme ? dlg.theme.radiusSmall : 4
                }
                onClicked: { dlg.rejectedWithPayload(dlg.payload); dlg.close(); }
            }

            Button {
                id: yesButton
                text: qsTr("Delete")
                contentItem: Label {
                    text: parent.text
                    font: parent.font
                    color: "white"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    implicitWidth: 100
                    implicitHeight: 36
                    color: parent.hovered ? Qt.lighter("#d32f2f", 1.1) : "#d32f2f"
                    radius: dlg.theme ? dlg.theme.radiusSmall : 4
                }
                onClicked: { dlg.acceptedWithPayload(dlg.payload); dlg.close(); }
                focus: true
            }
        }
    }

    signal acceptedWithPayload(var payload)
    signal rejectedWithPayload(var payload)
}
