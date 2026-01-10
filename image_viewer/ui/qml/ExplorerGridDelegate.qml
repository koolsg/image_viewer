/*
 ExplorerGridDelegate.qml — Explorer Grid의 각 썸네일 카드(delegate) 정의.
 이 파일은 썸네일 이미지, 파일 메타정보, 선택/하이라이트 스타일 등을 렌더링하여 그리드 항목을 구성합니다.
*/

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: delegateRoot

    // Provided by GridView/model (captured explicitly for Bound mode)
    required property int index
    required property string path
    required property string name
    required property string sizeText
    required property string mtimeText
    required property string resolutionText
    required property string thumbUrl

    // Provided by the owning view
    property var grid
    property var theme

    width: grid.cellWidth
    height: grid.cellHeight

    Rectangle {
        id: card

        width: delegateRoot.grid.thumbVisualWidth
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 6
        anchors.bottomMargin: 6
        height: parent.height - 12
        radius: delegateRoot.theme.radiusMedium
        color: (delegateRoot.grid.selectedIndices.indexOf(delegateRoot.index) !== -1) ? delegateRoot.theme.selection : delegateRoot.theme.surface
        border.color: (delegateRoot.grid.selectedIndices.indexOf(delegateRoot.index) !== -1) ? delegateRoot.theme.selectionBorder : delegateRoot.theme.border
        border.width: 1

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.RightButton

            onClicked: function(mouse) {
                if (mouse.button === Qt.RightButton) {
                    delegateRoot.grid.setSelectionTo(delegateRoot.index)
                }
            }
        }

        ToolTip.visible: false
        ToolTip.delay: 300
        ToolTip.text: [delegateRoot.name, [delegateRoot.resolutionText, delegateRoot.sizeText].filter(Boolean).join(" | ")].filter(Boolean).join("\n")

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 6

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.round(delegateRoot.grid.thumbVisualWidth * 0.76)
                radius: delegateRoot.theme.radiusSmall
                color: delegateRoot.theme.background

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

            Text {
                Layout.fillWidth: true
                color: delegateRoot.theme.text
                text: delegateRoot.name
                wrapMode: Text.Wrap
                font.pixelSize: 13
            }
            Text {
                Layout.fillWidth: true
                color: delegateRoot.theme.textDim
                font.pixelSize: 11
                text: [ (delegateRoot.name && delegateRoot.name.indexOf('.') !== -1) ? delegateRoot.name.split('.').pop().toUpperCase() : null, delegateRoot.resolutionText, delegateRoot.sizeText ].filter(Boolean).join(" | ")
            }
            Label {
                Layout.fillWidth: true
                color: delegateRoot.theme.textDim
                opacity: 0.7
                font.pixelSize: 10
                text: delegateRoot.mtimeText
                elide: Text.ElideRight
            }

            Item { Layout.fillHeight: true }
        }
    }
}
