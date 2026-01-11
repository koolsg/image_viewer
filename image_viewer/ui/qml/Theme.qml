/*
 Theme.qml — 애플리케이션의 색상, 간격, 반경 등 테마 속성을 정의합니다.
 이 파일은 Controls palette를 중앙화하여 앱 전역에서 일관된 스타일을 제공하기 위해 존재합니다.
*/

import QtQuick

QtObject {
    id: themeRoot
    enum Type {
        Dark,
        Light,
        Pastel
    }

    property int currentTheme: Theme.Dark

    // Common Styles
    readonly property int radiusSmall: 4
    readonly property int radiusMedium: 8
    readonly property int radiusLarge: 12
    readonly property int paddingMedium: 12
    readonly property int spacingSmall: 6
    readonly property int spacingMedium: 10

    // Theme Colors
    readonly property color background: {
        switch (currentTheme) {
            case Theme.Light: return "#F5F5F7"
            case Theme.Pastel: return "#FDFCF0" // Creamy Mint/Pastel Yellow
            default: return "#121212"
        }
    }

    readonly property color surface: {
        switch (currentTheme) {
            case Theme.Light: return "#FFFFFF"
            case Theme.Pastel: return "#FFFFFF"
            default: return "#1E1E1E"
        }
    }

    readonly property color text: {
        switch (currentTheme) {
            case Theme.Light: return "#1D1D1F"
            case Theme.Pastel: return "#4A3F35" // Soft Brown
            default: return "#E0E0E0"
        }
    }

    readonly property color textDim: {
        switch (currentTheme) {
            case Theme.Light: return "#86868B"
            case Theme.Pastel: return "#7D6E5E"
            default: return "#9E9E9E"
        }
    }

    readonly property color accent: {
        switch (currentTheme) {
            case Theme.Light: return "#007AFF" // iOS Blue
            case Theme.Pastel: return "#FFB7B2" // Pastel Pink/Peach
            default: return "#3D85C6"
        }
    }

    readonly property color border: {
        switch (currentTheme) {
            case Theme.Light: return "#D2D2D7"
            case Theme.Pastel: return "#E6DFD3"
            default: return "#333333"
        }
    }

    readonly property color hover: {
        switch (currentTheme) {
            case Theme.Light: return "#F0F0F0"
            case Theme.Pastel: return "#FFF5F5"
            default: return "#2A2A2A"
        }
    }

    readonly property color selection: {
        switch (currentTheme) {
            case Theme.Light: return Qt.rgba(0, 122, 255, 0.15)
            case Theme.Pastel: return Qt.rgba(255, 183, 178, 0.25)
            default: return Qt.rgba(61, 133, 198, 0.25)
        }
    }

    readonly property color selectionBorder: {
        switch (currentTheme) {
            case Theme.Light: return "#007AFF"
            case Theme.Pastel: return "#FFB7B2"
            default: return "#3D85C6"
        }
    }

    // Centralized Controls palette for the app.
    // NOTE: Refer to Theme properties via `themeRoot.*` because Palette has
    // overlapping property names (e.g., `text`) that would otherwise cause
    // self-referential bindings.
    readonly property var palette: Palette {
        window: themeRoot.background
        windowText: themeRoot.text

        base: themeRoot.surface
        text: themeRoot.text

        button: themeRoot.surface
        buttonText: themeRoot.text

        highlight: themeRoot.accent
        highlightedText: themeRoot.currentTheme === Theme.Dark ? "#FFFFFF" : "#000000"
    }
}
