pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Dialog {
    id: dlg
    modal: true
    title: "Convert to WebP"
    standardButtons: Dialog.NoButton

    property var main: null
    property var theme: null

    property string folderText: ""
    property bool shouldResize: true
    property int targetShortSide: 2160
    property int quality: 90
    property bool deleteOriginals: true

    property string logText: ""

    width: 760
    height: 600

    background: Rectangle {
        color: dlg.theme ? dlg.theme.surface : "#121212"
        radius: dlg.theme ? dlg.theme.radiusLarge : 8
        border.color: dlg.theme ? dlg.theme.border : "#303030"
        border.width: 1
    }

    function appendLog(line) {
        if (!line) return
        if (dlg.logText.length === 0) dlg.logText = String(line)
        else dlg.logText = dlg.logText + "\n" + String(line)
    }

    FolderDialog {
        id: folderPicker
        title: "Choose a folder"
        onAccepted: {
            dlg.folderText = folderPicker.selectedFolder.toString()
        }
    }

    MessageDialog {
        id: messageDialog
        title: ""
        text: ""
    }

    Connections {
        target: dlg.main
        function onWebpConvertLog(line) {
            dlg.appendLog(line)
        }
        function onWebpConvertFinished(converted, total) {
            dlg.appendLog("Done: " + converted + "/" + total + " converted.")
        }
        function onWebpConvertCanceled() {
            dlg.appendLog("Canceled.")
        }
        function onWebpConvertError(msg) {
            dlg.appendLog(String(msg))
            messageDialog.title = "WebP conversion error"
            messageDialog.text = String(msg)
            messageDialog.open()
        }
    }

    contentItem: ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        Label {
            text: "Convert Images to WebP"
            font.pixelSize: 20
            font.bold: true
            color: dlg.theme ? dlg.theme.text : "white"
        }

        GridLayout {
            columns: 3
            columnSpacing: 12
            rowSpacing: 12
            Layout.fillWidth: true

            Label { text: "Folder"; color: dlg.theme ? dlg.theme.text : "white"; font.bold: true }

            TextField {
                id: folderField
                Layout.fillWidth: true
                text: dlg.folderText
                placeholderText: "Choose a folder..."
                color: dlg.theme ? dlg.theme.text : "white"
                background: Rectangle {
                    radius: dlg.theme ? dlg.theme.radiusSmall : 4
                    color: dlg.theme ? dlg.theme.background : "#1a1a1a"
                    border.color: dlg.theme ? dlg.theme.border : "#333333"
                }
                onTextChanged: dlg.folderText = text
            }

            Button {
                text: "Browse"
                onClicked: folderPicker.open()
            }

            Label { text: "Options"; color: dlg.theme ? dlg.theme.text : "white"; font.bold: true }

            Flow {
                Layout.columnSpan: 2
                Layout.fillWidth: true
                spacing: 20

                RowLayout {
                    spacing: 8
                    CheckBox {
                        id: resizeCb
                        text: "Resize short side to"
                        checked: dlg.shouldResize
                        onToggled: dlg.shouldResize = checked
                    }

                    SpinBox {
                        id: targetSpin
                        from: 256
                        to: 8000
                        value: dlg.targetShortSide
                        enabled: resizeCb.checked
                        onValueChanged: dlg.targetShortSide = value
                    }

                    Label { text: "px"; color: dlg.theme ? dlg.theme.textDim : "#bdbdbd" }
                }

                RowLayout {
                    spacing: 8
                    Label { text: "Quality"; color: dlg.theme ? dlg.theme.text : "white" }
                    SpinBox {
                        id: qualitySpin
                        from: 50
                        to: 100
                        value: dlg.quality
                        onValueChanged: dlg.quality = value
                    }
                }
            }

            Item { Layout.preferredHeight: 1; Layout.columnSpan: 3 }

            Label { text: "Cleanup"; color: dlg.theme ? dlg.theme.text : "white"; font.bold: true }

            CheckBox {
                id: deleteCb
                Layout.columnSpan: 2
                text: "Delete originals after conversion"
                checked: dlg.deleteOriginals
                onToggled: dlg.deleteOriginals = checked
            }
        }

        ProgressBar {
            Layout.fillWidth: true
            from: 0
            to: 100
            value: dlg.main ? dlg.main.webpConvertPercent : 0
            background: Rectangle {
                implicitHeight: 6
                color: dlg.theme ? dlg.theme.background : "#1a1a1a"
                radius: 3
            }
            contentItem: Item {
                Rectangle {
                    width: parent.parent.visualPosition * parent.width
                    height: parent.height
                    radius: 3
                    color: dlg.theme ? dlg.theme.accent : "#3D85C6"
                }
            }
        }

        TextArea {
            id: logArea
            Layout.fillWidth: true
            Layout.fillHeight: true
            readOnly: true
            wrapMode: TextArea.Wrap
            text: dlg.logText
            font.family: "Consolas"
            font.pixelSize: 12
            color: dlg.theme ? dlg.theme.text : "white"
            background: Rectangle {
                color: dlg.theme ? dlg.theme.background : "#0f0f0f"
                radius: dlg.theme ? dlg.theme.radiusSmall : 4
                border.color: dlg.theme ? dlg.theme.border : "#333333"
            }

            onTextChanged: {
                logArea.contentY = Math.max(0, logArea.contentHeight - logArea.height)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Label {
                text: deleteCb.checked ? "Warning: Originals will be PERMANENTLY removed." : ""
                color: "#d32f2f"
                font.bold: true
                visible: deleteCb.checked
            }

            Item { Layout.fillWidth: true }

            Button {
                text: (dlg.main && dlg.main.webpConvertRunning) ? "Running..." : "Start Conversion"
                highlighted: true
                enabled: dlg.main && !dlg.main.webpConvertRunning
                onClicked: {
                    if (!dlg.main) return
                    if (!dlg.folderText || dlg.folderText.length === 0) {
                        messageDialog.title = "Invalid folder"
                        messageDialog.text = "Please choose a valid folder."
                        messageDialog.open()
                        return
                    }
                    dlg.logText = ""
                    dlg.main.startWebpConvert(dlg.folderText, dlg.shouldResize, dlg.targetShortSide, dlg.quality, dlg.deleteOriginals)
                }
            }

            Button {
                text: "Stop"
                visible: dlg.main && dlg.main.webpConvertRunning
                onClicked: if (dlg.main) dlg.main.cancelWebpConvert()
            }

            Button {
                text: "Close"
                enabled: !(dlg.main && dlg.main.webpConvertRunning)
                onClicked: dlg.close()
            }
        }
    }

    onOpened: {
        if (dlg.main && dlg.main.currentFolder && dlg.folderText.length === 0) {
            dlg.folderText = dlg.main.currentFolder
        }
    }
}
