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

    // Injected from App.qml
    property var main: null

    // Form state
    property string folderText: ""
    property bool shouldResize: true
    property int targetShortSide: 2160
    property int quality: 90
    property bool deleteOriginals: true

    // UI state
    property string logText: ""

    width: 720
    height: 520

    background: Rectangle {
        color: "#121212"
        radius: 8
        border.color: "#303030"
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
        anchors.margins: 16
        spacing: 12

        GridLayout {
            columns: 3
            columnSpacing: 10
            rowSpacing: 10
            Layout.fillWidth: true

            Label { text: "Folder"; color: "white" }

            TextField {
                id: folderField
                Layout.fillWidth: true
                text: dlg.folderText
                placeholderText: "Choose a folder..."
                onTextChanged: dlg.folderText = text
            }

            Button {
                text: "Browse..."
                onClicked: folderPicker.open()
            }

            Label { text: "Resize"; color: "white" }

            RowLayout {
                Layout.fillWidth: true
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

                Label { text: "px"; color: "#bdbdbd" }

                Item { Layout.fillWidth: true }
            }

            Label { text: "Quality"; color: "white" }
            SpinBox {
                id: qualitySpin
                Layout.columnSpan: 2
                Layout.fillWidth: true
                from: 50
                to: 100
                value: dlg.quality
                onValueChanged: dlg.quality = value
            }

            Label { text: "Delete originals"; color: "white" }
            RowLayout {
                Layout.columnSpan: 2
                Layout.fillWidth: true
                CheckBox {
                    id: deleteCb
                    text: "Delete originals after convert"
                    checked: dlg.deleteOriginals
                    onToggled: dlg.deleteOriginals = checked
                }
                Label {
                    text: deleteCb.checked ? "Warning: originals will be removed." : ""
                    color: "#d32f2f"
                    font.bold: true
                }
                Item { Layout.fillWidth: true }
            }
        }

        ProgressBar {
            Layout.fillWidth: true
            from: 0
            to: 100
            value: dlg.main ? dlg.main.webpConvertPercent : 0
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

            // auto-scroll to end when log updates
            onTextChanged: {
                // TextArea is scrollable; keep it pinned to the bottom.
                logArea.contentY = logArea.contentHeight
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Item { Layout.fillWidth: true }

            Button {
                text: (dlg.main && dlg.main.webpConvertRunning) ? "Running..." : "Start"
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
                text: "Cancel"
                enabled: dlg.main && dlg.main.webpConvertRunning
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
        // Default folder: current folder if available.
        if (dlg.main && dlg.main.currentFolder && dlg.folderText.length === 0) {
            dlg.folderText = dlg.main.currentFolder
        }
    }
}
