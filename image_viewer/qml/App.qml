pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "."

ApplicationWindow {
    id: root
    width: 1400
    height: 900
    visible: true
    title: "Image Viewer (QML)"

    // Set from Python via rootObject().setProperty("main", ...)
    property var main: null

    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            spacing: 8

            ToolButton {
                text: "Open Folder"
                onClicked: folderDialog.open()
            }

            Item { Layout.fillWidth: true }

            Label {
                text: {
                    if (!root.main) return ""
                    var total = root.main.imageFiles ? root.main.imageFiles.length : 0
                    var idx = root.main.currentIndex
                    if (total <= 0) return "No folder"
                    return (idx + 1) + " / " + total
                }
            }

            ToolButton {
                text: root.main && root.main.viewMode ? "Back" : "View"
                enabled: root.main && (root.main.imageFiles && root.main.imageFiles.length > 0)
                onClicked: {
                    if (!root.main) return
                    root.main.viewMode = !root.main.viewMode
                }
            }
        }
    }

    FolderDialog {
        id: folderDialog
        title: "Choose a folder"
        onAccepted: {
            if (!root.main) return
            // Pass URL string; Python normalizes file:// URLs to local paths.
            root.main.openFolder(folderDialog.selectedFolder.toString())
        }
    }

    // --- Global shortcuts (work in both Explorer and Viewer) ---
    Shortcut {
        sequences: [ StandardKey.Open ]
        context: Qt.ApplicationShortcut
        onActivated: folderDialog.open()
    }
    Shortcut {
        sequence: "Escape"
        context: Qt.ApplicationShortcut
        onActivated: {
            if (!root.main) return
            if (root.main.viewMode) {
                root.main.closeView()
            }
        }
    }
    Shortcut {
        sequence: "Left"
        context: Qt.ApplicationShortcut
        onActivated: if (root.main && root.main.viewMode) root.main.prevImage()
    }
    Shortcut {
        sequence: "Right"
        context: Qt.ApplicationShortcut
        onActivated: if (root.main && root.main.viewMode) root.main.nextImage()
    }
    Shortcut {
        sequence: "Home"
        context: Qt.ApplicationShortcut
        onActivated: if (root.main && root.main.viewMode) root.main.firstImage()
    }
    Shortcut {
        sequence: "End"
        context: Qt.ApplicationShortcut
        onActivated: if (root.main && root.main.viewMode) root.main.lastImage()
    }
    Shortcut {
        sequences: [ StandardKey.Copy ]
        context: Qt.ApplicationShortcut
        onActivated: {
            if (!root.main) return
            if (root.main.currentPath) root.main.copyText(root.main.currentPath)
        }
    }

    StackLayout {
        id: stack
        anchors.fill: parent
        currentIndex: (root.main && root.main.viewMode) ? 1 : 0

        // Explorer (Grid)
        Item {
            id: explorerPage
            Layout.fillWidth: true
            Layout.fillHeight: true

            Rectangle {
                anchors.fill: parent
                color: "#121212"

                GridView {
                    id: grid
                    anchors.fill: parent
                    anchors.margins: 12
                    cellWidth: 220
                    cellHeight: 270
                    clip: true
                    model: root.main ? root.main.imageModel : null
                    currentIndex: root.main ? root.main.currentIndex : -1

                    delegate: Item {
                        id: delegateRoot
                        required property int index
                        required property string path
                        required property string name
                        required property string sizeText
                        required property string mtimeText
                        required property string resolutionText
                        required property string thumbUrl

                        width: grid.cellWidth
                        height: grid.cellHeight

                        Rectangle {
                            id: card
                            anchors.fill: parent
                            anchors.margins: 6
                            radius: 8
                            color: (delegateRoot.index === grid.currentIndex) ? "#2a3b52" : "#1a1a1a"
                            border.color: (delegateRoot.index === grid.currentIndex) ? "#6aa9ff" : "#2a2a2a"
                            border.width: 1

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 6

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 160
                                    radius: 6
                                    color: "#0f0f0f"

                                    Image {
                                        id: thumb
                                        anchors.fill: parent
                                        anchors.margins: 6
                                        fillMode: Image.PreserveAspectFit
                                        asynchronous: true
                                        cache: false
                                        smooth: true
                                        mipmap: true
                                        source: delegateRoot.thumbUrl
                                    }
                                }

                                Label {
                                    Layout.fillWidth: true
                                    color: "white"
                                    text: delegateRoot.name
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    color: "#b0b0b0"
                                    font.pixelSize: 11
                                    text: [delegateRoot.resolutionText, delegateRoot.sizeText].filter(Boolean).join(" • ")
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    color: "#7f7f7f"
                                    font.pixelSize: 10
                                    text: delegateRoot.mtimeText
                                    elide: Text.ElideRight
                                }

                                Item { Layout.fillHeight: true }
                            }

                            Menu {
                                id: ctxMenu
                                MenuItem {
                                    text: "Open"
                                    onTriggered: {
                                        if (!root.main) return
                                        root.main.currentIndex = delegateRoot.index
                                        root.main.viewMode = true
                                    }
                                }
                                MenuItem {
                                    text: "Copy path"
                                    onTriggered: if (root.main) root.main.copyText(delegateRoot.path)
                                }
                                MenuItem {
                                    text: "Reveal in Explorer"
                                    onTriggered: if (root.main) root.main.revealInExplorer(delegateRoot.path)
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                onClicked: function(mouse) {
                                    if (!root.main) return
                                    grid.currentIndex = delegateRoot.index
                                    root.main.currentIndex = delegateRoot.index
                                    if (mouse.button === Qt.RightButton) {
                                        ctxMenu.popup()
                                    } else {
                                        // Single click selects; double click opens.
                                    }
                                }
                                onDoubleClicked: {
                                    if (!root.main) return
                                    root.main.currentIndex = delegateRoot.index
                                    root.main.viewMode = true
                                }
                            }
                        }
                    }
                }
            }
        }

        // Viewer
        ViewerPage {
            id: viewerPage
            Layout.fillWidth: true
            Layout.fillHeight: true
            main: root.main
        }
    }
}
