import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Dialog {
    id: dlg
    modal: true
    property alias titleText: titleLabel.text
    property alias infoText: infoLabel.text
    property var payload: null
    property string theme: "dark"

    x: parent ? (parent.width - width) / 2 : x
    y: parent ? (parent.height - height) / 2 : y
    width: Math.max(360, Math.min(760, (infoText.length * 6) + 240))

    background: Rectangle {
        color: dlg.theme === "light" ? "#ffffff" : "#121212"
        radius: 8
        border.color: dlg.theme === "light" ? "#e0e0e0" : "#303030"
        border.width: 1
        width: dlg.width
        height: dlg.height
    }

    contentItem: ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12

        RowLayout {
            spacing: 12
            Layout.preferredHeight: 56

            Image {
                source: ""
                Layout.preferredWidth: 48
                Layout.preferredHeight: 48
                fillMode: Image.PreserveAspectFit
            }

            ColumnLayout {
                Layout.fillWidth: true
                        Label {
                    id: titleLabel
                    text: ""
                    font.pixelSize: 14
                    font.bold: true
                    wrapMode: Text.Wrap
                    color: dlg.theme === "light" ? "#000000" : "#ffffff"
                }
                Label {
                    id: infoLabel
                    text: ""
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    color: dlg.theme === "light" ? "#333333" : "#bdbdbd"
                }
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 10

            Button {
                id: noButton
                objectName: "button-no"
                text: qsTr("No")
                onClicked: { dlg.rejectedWithPayload(dlg.payload); dlg.close(); }
            }

            Button {
                id: yesButton
                objectName: "button-yes"
                text: qsTr("Yes")
                onClicked: { dlg.acceptedWithPayload(dlg.payload); dlg.close(); }
                // Make Yes default so Enter activates it
                focus: true
            }
        }

        // Shortcuts at dialog level (Y/N)
        Shortcut { sequences: ["Y"] ; onActivated: yesButton.clicked() }
        Shortcut { sequences: ["N"] ; onActivated: noButton.clicked() }
    }

    signal acceptedWithPayload(var payload)
    signal rejectedWithPayload(var payload)
}
