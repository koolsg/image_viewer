/*
 ConvertWebPDialog.qml — 이미지들을 WebP로 일괄 변환하는 UI 다이얼로그입니다.
 이 파일은 변환 설정, 진행 로그 표시 및 백엔드 변환 작업과의 상호작용을 담당합니다.
*/

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Dialog {
    id: dlg
    modal: true
    title: "Convert to WebP"
    standardButtons: Dialog.NoButton

    // Python facade (BackendFacade) injected from App.qml.
    property var backend: null
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
        target: dlg.backend

        function onTaskEvent(ev) {
            if (!ev || ev.name !== "webpConvert") return

            if (ev.state === "log") {
                dlg.appendLog(ev.message)
                return
            }

            if (ev.state === "finished") {
                dlg.appendLog("Done: " + ev.converted + "/" + ev.total + " converted.")
                return
            }

            if (ev.state === "canceled") {
                dlg.appendLog("Canceled.")
                return
            }

            if (ev.state === "error") {
                dlg.appendLog(String(ev.message || ""))
                messageDialog.title = "WebP conversion error"
                messageDialog.text = String(ev.message || "")
                messageDialog.open()
                return
            }
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
            id: progressBar
            Layout.fillWidth: true
            from: 0
            to: 100
            value: (dlg.backend && dlg.backend.tasks) ? dlg.backend.tasks.webpConvertPercent : 0
            background: Rectangle {
                implicitHeight: 6
                color: dlg.theme ? dlg.theme.background : "#1a1a1a"
                radius: 3
            }
            contentItem: Item {
                Rectangle {
                    width: progressBar.visualPosition * parent.width
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
                text: (dlg.backend && dlg.backend.tasks && dlg.backend.tasks.webpConvertRunning) ? "Running..." : "Start Conversion"
                highlighted: true
                enabled: dlg.backend && dlg.backend.tasks && !dlg.backend.tasks.webpConvertRunning
                onClicked: {
                    if (!dlg.backend) return
                    if (!dlg.folderText || dlg.folderText.length === 0) {
                        messageDialog.title = "Invalid folder"
                        messageDialog.text = "Please choose a valid folder."
                        messageDialog.open()
                        return
                    }
                    dlg.logText = ""
                    dlg.backend.dispatch(
                        "startWebpConvert",
                        {
                            folder: dlg.folderText,
                            shouldResize: dlg.shouldResize,
                            targetShort: dlg.targetShortSide,
                            quality: dlg.quality,
                            deleteOriginals: dlg.deleteOriginals
                        }
                    )
                }
            }

            Button {
                text: "Stop"
                visible: dlg.backend && dlg.backend.tasks && dlg.backend.tasks.webpConvertRunning
                onClicked: if (dlg.backend) dlg.backend.dispatch("cancelWebpConvert", null)
            }

            Button {
                text: "Close"
                enabled: !(dlg.backend && dlg.backend.tasks && dlg.backend.tasks.webpConvertRunning)
                onClicked: dlg.close()
            }
        }
    }

    onOpened: {
        if (dlg.backend && dlg.backend.explorer && dlg.backend.explorer.currentFolder && dlg.folderText.length === 0) {
            dlg.folderText = dlg.backend.explorer.currentFolder
        }
    }
}
