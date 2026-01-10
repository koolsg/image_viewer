/*
 App.qml — 애플리케이션의 최상위 창 (ApplicationWindow).
 이 파일은 전체 애플리케이션의 루트 윈도우를 제공하며, 테마/백엔드 주입, 헤더(타이틀바/메뉴), Explorer 그리드 등 주요 레이아웃과 전역 행동을 호스트합니다.
 존재 이유: 앱 전역 상태와 레이아웃 관리를 한곳에 두어 QML 컴포넌트 간 계약을 명확히 하기 위해 존재합니다.
*/

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "."

ApplicationWindow {
    id: root
    width: 1400
    height: 900
    visible: true
    title: "Image Viewer"
    flags: Qt.Window | Qt.FramelessWindowHint

    // Python sets this immediately after loading the QML root.
    // Use `root.backend` (not the unqualified context name) to satisfy
    // `pragma ComponentBehavior: Bound` rules.
    property var backend: null

    property string explorerSelectedPath: ""
    property bool hqDownscaleEnabled: false

    // Input handlers (notably DragHandler/startSystemMove) can misbehave if the window
    // appears under a currently-pressed mouse button during app launch (Windows).
    // We enable them only after the first frame/show has settled.
    property bool _inputReady: false

    Theme {
        id: theme
    }

    property var appTheme: theme

    palette: theme.palette

    function qmlDebugSafe(msg) {
        // backend is injected as a context property before QML loads.
        try {
            if (root.backend) {
                root.backend.dispatch("log", { level: "debug", message: String(msg) })
                return
            }
        } catch (e) {
            // fall back to console if Python call fails
        }
        console.log(String(msg))
    }

    onActiveChanged: {
        if (active && root.backend && !root.backend.viewer.viewMode) {
            grid.forceActiveFocus()
        }
        if (active) root.qmlDebugSafe("Application active change: active=" + active)
    }

    function _openFolderDialogAtLastParent() {
        dialogs.openFolderDialogAtLastParent()
    }

    function showDeleteDialog(title, text, info, payload) {
        dialogs.showDeleteDialog(title, text, info, payload)
    }

    ViewWindow {
        id: viewWindow
        backend: root.backend
        theme: theme
        hqDownscaleEnabled: root.hqDownscaleEnabled

        onRequestRestoreMainFocus: {
            root.requestActivate()
            root.raise()
            Qt.callLater(function() {
                root.requestActivate()
                if (grid) grid.forceActiveFocus()
            })
        }
    }

    // Invisible / non-core UI extracted to keep App.qml lean.
    AppDialogs {
        id: dialogs
        backend: root.backend
        theme: theme
        overlayParent: Overlay.overlay
    }
    Component.onCompleted: {
        Qt.callLater(function() {
            try {
                // For frameless window, showMaximized() works but we need to ensure
                // we can still restore.
                root.show()
                root.requestActivate()
                root.raise()
            } catch (e) {
                console.log("Failed to show on startup: " + e)
            }
        })

        // Defer enabling DragHandler / system move until the window is visible.
        Qt.callLater(function() { root._inputReady = true })
    }

    // --- Custom Title Bar & Window Management ---

    header: AppHeader {
        app: root
        theme: theme
        dialogs: dialogs
    }

    FramelessResizeHandles {
        app: root
        overlayParent: Overlay.overlay
    }

    FocusScope {
        id: explorerPage
        parent: root.contentItem
        anchors.fill: parent
        focus: true

        Rectangle {
            anchors.fill: parent
            color: root.backend ? root.backend.settings.backgroundColor : theme.background

            GridView {
                id: grid
                anchors.fill: parent
                anchors.margins: 12
                property int thumbVisualWidth: (root.backend && root.backend.settings) ? root.backend.settings.thumbnailWidth : 220
                property int minHSpacing: 6
                property int computedCols: Math.max(1, Math.floor(width / (thumbVisualWidth + minHSpacing)))
                property int hSpacing: Math.max(minHSpacing, Math.floor((width - (computedCols * thumbVisualWidth)) / Math.max(1, computedCols)))
                cellWidth: thumbVisualWidth + hSpacing
                cellHeight: Math.round((thumbVisualWidth + hSpacing) * 1.2)
                clip: true
                model: root.backend ? root.backend.explorer.imageModel : null
                currentIndex: root.backend ? root.backend.explorer.currentIndex : -1
                focus: true
                activeFocusOnTab: true

                // Selection state (QML-only)
                property var selectedIndices: []
                property int lastClickedIndex: -1
                property int _lastClickIndex: -1
                property real _lastClickAtMs: 0
                property int _doubleClickIntervalMs: 350
                property bool selectionRectVisible: false
                property real selectionRectX: 0
                property real selectionRectY: 0
                property real selectionRectW: 0
                property real selectionRectH: 0
                property bool dragSelecting: false
                property real pressX: 0
                property real pressY: 0
                property bool selectionSyncEnabled: true

                function setSelectionTo(idx) {
                    grid.selectedIndices = (idx >= 0) ? [idx] : []
                    grid.lastClickedIndex = idx
                    if (root.backend) {
                        root.backend.dispatch("setCurrentIndex", { index: idx })
                    }
                    if (idx >= 0 && root.backend && root.backend.explorer.imageFiles && idx < root.backend.explorer.imageFiles.length) {
                        root.explorerSelectedPath = root.backend.explorer.imageFiles[idx]
                    }
                }

                function setCurrentIndexOnly(idx) {
                    if (root.backend) {
                        root.backend.dispatch("setCurrentIndex", { index: idx })
                    }
                    if (idx >= 0 && root.backend && root.backend.explorer.imageFiles && idx < root.backend.explorer.imageFiles.length) {
                        root.explorerSelectedPath = root.backend.explorer.imageFiles[idx]
                    }
                }

                onCurrentIndexChanged: {
                    if (grid.dragSelecting || !grid.selectionSyncEnabled) return
                    if (root.backend && root.backend.explorer.currentIndex >= 0) {
                        grid.selectedIndices = [root.backend.explorer.currentIndex]
                        grid.lastClickedIndex = root.backend.explorer.currentIndex
                    }
                }

                ExplorerSelectionOverlay {
                    app: root
                    grid: grid
                    backend: root.backend
                    theme: theme
                }

                ExplorerShortcuts {
                    app: root
                    backend: root.backend
                    grid: grid
                    dialogs: dialogs
                }

                Keys.onPressed: function(event) {
                    if (!root.backend) return
                    // If a viewer is active (view mode), let viewer shortcuts handle keys.
                    if (root.backend && root.backend.viewer && root.backend.viewer.viewMode) return

                    var total = root.backend.explorer.imageFiles ? root.backend.explorer.imageFiles.length : 0
                    var idx = (root.backend.explorer.currentIndex >= 0) ? root.backend.explorer.currentIndex : 0
                    var cols = grid.computedCols || 1

                    // Arrow key navigation within the grid
                    if (event.key === Qt.Key_Left) {
                        if (idx > 0) {
                            idx = Math.max(0, idx - 1)
                            grid.setSelectionTo(idx)
                            grid.positionViewAtIndex(idx, GridView.Visible)
                        }
                        event.accepted = true
                        return
                    }

                    if (event.key === Qt.Key_Right) {
                        if (idx < total - 1) {
                            idx = Math.min(total - 1, idx + 1)
                            grid.setSelectionTo(idx)
                            grid.positionViewAtIndex(idx, GridView.Visible)
                        }
                        event.accepted = true
                        return
                    }

                    if (event.key === Qt.Key_Up) {
                        if (idx > 0) {
                            idx = Math.max(0, idx - cols)
                            grid.setSelectionTo(idx)
                            grid.positionViewAtIndex(idx, GridView.Visible)
                        }
                        event.accepted = true
                        return
                    }

                    if (event.key === Qt.Key_Down) {
                        if (idx < total - 1) {
                            idx = Math.min(total - 1, idx + cols)
                            grid.setSelectionTo(idx)
                            grid.positionViewAtIndex(idx, GridView.Visible)
                        }
                        event.accepted = true
                        return
                    }

                    // Explorer-specific file/action shortcuts (Enter/Delete/Ctrl+*/F2) moved to `ExplorerShortcuts.qml`.
                    // Shortcut instances are injected next to the grid and are enabled only when View mode is not active.
                    // (Arrow navigation remains handled here for repeat/hold behaviour.)
                }

                delegate: ExplorerGridDelegate {
                    grid: grid
                    theme: theme
                }
            }
        }
    }
}
