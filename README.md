# SwiftView Image Viewer

A fast, feature-rich desktop image viewer built with PySide6 and multi-process image decoding.

## Overview

- **Modern Architecture**: PySide6 GUI with pyvips-based multi-process image decoding
- **Dual Modes**: View mode for immersive image viewing, Explorer mode for file browsing
- **Performance Optimized**: Thumbnail mode for fast browsing, Full mode for original quality
- **Cross-Platform**: Windows-optimized with Linux/macOS support
- **Advanced Features**: WebP conversion, image trimming, theme system, SQLite thumbnail cache

## Features

### Core Viewing
- **Image Navigation**: Previous/Next with keyboard and mouse
- **Zoom & Pan**: Mouse wheel zoom, press-and-hold zoom, fit/actual modes
- **Fullscreen**: F11 toggle with overlay status
- **Background Colors**: Black, white, or custom color picker

### Explorer Mode
- **Grid View**: Thumbnail browsing with file operations
- **Tree Navigation**: Folder structure navigation
- **Performance**: Lazy loading and caching for large folders

### Image Processing
- **Decoding Strategies**: 
  - Thumbnail mode: Fast, screen-sized decoding
  - Full mode: Original resolution decoding
- **Multi-processing**: Parallel image decoding with pyvips
- **Caching**: LRU pixmap cache with prefetching and SQLite thumbnail cache
- **Image Trimming**: Automatic content detection with manual adjustment
- **Rotation**: Left/right rotation with visual feedback

### File Operations
- **Delete to Recycle Bin**: Safe deletion with confirmation
- **File Operations**: Copy, cut, paste, rename with Windows-like context menus
- **WebP Conversion**: Batch conversion with multi-processing and resize options
- **Format Support**: JPG, PNG, BMP, TIFF, GIF, WebP

## Installation

### Prerequisites
- Python 3.11+
- Windows: pyvips DLLs (auto-installed with `[binary]` extra)

### Quick Install (Recommended)
```bash
# Clone and install
git clone <repository-url>
cd image_viewer
uv sync

# Run
uv run python -m image_viewer
```

### Manual Install
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or venv\Scripts\activate  # Windows

# Install dependencies
pip install pyside6 pyvips[binary] numpy send2trash

# Run
python -m image_viewer
```

### Command Line Options
```bash
# Open with specific folder or image
python -m image_viewer /path/to/folder
python -m image_viewer /path/to/image.jpg

# Logging options
python -m image_viewer --log-level DEBUG --log-cats engine,ui
```

## Usage

### Basic Navigation
- **Arrow Keys**: Previous/Next image
- **Mouse Wheel**: Previous/Next (no Ctrl) or Zoom (Ctrl+Wheel)
- **Enter**: Toggle between View and Explorer modes
- **F5**: Refresh Explorer
- **F11**: Toggle fullscreen
- **Delete**: Move current file to recycle bin

### Advanced Features
- **Press-Zoom**: Hold left mouse to zoom by multiplier (default: 2.0x)
- **Thumbnail Mode**: View → "Thumbnail Mode (fast viewing)"
- **Background**: View → Black/White/Custom color
- **Settings**: Access via menu for zoom multiplier, theme, thumbnail size
- **Theme System**: Dark/Light mode with full UI theming
- **Image Trimming**: Tools → "Trim Image" with auto-detection
- **WebP Conversion**: Tools → "Convert to WebP" with batch processing

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| ←/→ | Previous/Next image |
| Home/End | First/Last image |
| Space | Snap to current global mode |
| Enter | Toggle View↔Explorer |
| F5 | Refresh Explorer |
| F11 | Fullscreen toggle |
| Delete | Delete to recycle bin |
| A/D | Rotate left/right |
| Ctrl+Wheel | Zoom |
| Ctrl+O | Open folder |
| F | Fit to screen |
| 1 | Actual size (100%) |
| T | Toggle thumbnail mode |

## Architecture

### Project Structure
```
image_viewer/
├── main.py                 # Main application window
├── image_engine/          # Backend processing
│   ├── engine.py          # Core image engine
│   ├── decoder.py         # pyvips decoding
│   ├── strategy.py        # Decoding strategies
│   ├── thumbnail_cache.py # SQLite thumbnail cache
│   ├── loader.py          # Multi-process loading
│   └── fs_model.py        # File system model
├── ui_*.py                 # User interface components
│   ├── ui_canvas.py       # Image display canvas
│   ├── ui_explorer_grid.py # Explorer grid view
│   ├── ui_explorer_tree.py # Folder tree view
│   ├── ui_trim.py         # Trim/crop interface
│   ├── ui_convert_webp.py # WebP conversion dialog
│   ├── ui_settings.py     # Settings dialog
│   └── ui_menus.py        # Menu system
├── explorer_mode_operations.py # Mode switching logic
├── file_operations.py     # File system operations
├── webp_converter.py      # WebP batch conversion
├── trim.py                # Image trimming algorithms
├── styles.py              # Theme system
├── settings_manager.py    # User settings
└── logger.py              # Logging system
```

### Key Components
- **ImageEngine**: Multi-process decoding and caching with SQLite thumbnails
- **DecodingStrategy**: Thumbnail vs Full resolution modes with adaptive sizing
- **ExplorerMode**: Grid-based file browsing with Windows-like operations
- **SettingsManager**: User preferences and state persistence
- **ThemeSystem**: Dark/Light mode with comprehensive UI styling
- **WebPConverter**: Multi-process batch conversion with resize options
- **TrimOperations**: Automatic content detection and manual adjustment

## Development

### Code Quality
```bash
# Lint and auto-fix
uv run ruff check --fix .

# Type checking
uv run pyright
```

### Project Structure
- Follow the documented workflow in `AGENTS.md`
- Track tasks in `TASKS.md` and `control.yaml`
- Log completed work in `SESSIONS.md`

### Adding Features
1. Plan in `TASKS.md`
2. Implement with quality checks
3. Document in `SESSIONS.md`
4. Update `README.md` if user-facing

## Configuration

### Settings File
Location: `image_viewer/settings.json`
```json
{
  "thumbnail_mode": true,
  "background_color": "#000000",
  "press_zoom_multiplier": 2.0,
  "last_parent_dir": "C:/Users/...",
  "theme": "dark",
  "thumbnail_width": 200,
  "thumbnail_height": 150,
  "thumbnail_hspacing": 10,
  "window_geometry": "x,y,width,height",
  "window_state": "normal|maximized|fullscreen"
}
```

### Thumbnail Cache
- **Location**: `SwiftView_thumbs.db` (SQLite format)
- **Purpose**: Persistent thumbnail cache across sessions
- **Benefits**: Faster folder loading on subsequent visits
- **Management**: Automatically cleaned when cache exceeds limits

### Environment Variables
- `LIBVIPS_BIN`: Path to pyvips DLLs (Windows if not in PATH)
- `IMAGE_VIEWER_LOG`: Logging level
- `IMAGE_VIEWER_LOG_CATS`: Log categories

## Troubleshooting

### Common Issues

**"pyvips not found" or DLL errors**
- Install: `pip install pyvips[binary]`
- Or set `LIBVIPS_BIN` environment variable

**Performance with large folders**
- Enable Thumbnail mode for faster loading
- Use SQLite thumbnail cache for persistent performance
- Check Explorer Mode performance settings

**Memory usage with large images**
- Use Thumbnail mode for browsing
- Clear cache if needed (restart application)

**Explorer Mode shows only C: drive**
- This is a known issue being addressed
- Workaround: Use File → Open Folder to navigate directly

### Windows-Specific
- Edge-to-edge fullscreen rendering
- Recycle Bin integration via send2trash
- DLL loading for pyvips
- SQLite thumbnail cache compatible with Windows thumbs.db

### Debug Logging
```bash
# Enable debug logging
python -m image_viewer --log-level DEBUG

# Debug specific components
python -m image_viewer --log-cats engine,ui,explorer
```

## Development Status

### Current Features (✅ Implemented)
- **Core Viewing**: Fast image navigation, zoom, pan, rotation
- **Explorer Mode**: Grid view with file operations, folder tree
- **Performance**: Multi-process decoding, SQLite thumbnail cache
- **Image Processing**: WebP conversion, automatic trimming
- **UI/UX**: Theme system, settings persistence, keyboard shortcuts
- **File Operations**: Copy/cut/paste/rename, recycle bin integration

### In Development (🚧 Work in Progress)
- **Performance Optimization**: LRU cache memory limits, lazy loading for large folders
- **Trim UI Improvements**: Crop presets (16:9, 4:3, 1:1)
- **UI Enhancements**: Application icon, toolbar, menu structure refinement

### Planned Features (📋 Roadmap)
- **Advanced Editing**: Crop/save, brightness/contrast adjustment
- **Batch Operations**: Image merge/split, batch processing
- **User Experience**: Slideshow mode, metadata display, dual monitor support
- **Packaging**: Optimized libvips DLLs, installer creation

See `TASKS.md` for detailed implementation priorities and progress.

## Contributing

1. Read `AGENTS.md` for development workflow and coding standards
2. Check `TASKS.md` for current priorities and in-progress items
3. Follow code quality standards (ruff, pyright)
4. Document changes in `SESSIONS.md` and update relevant control files

## License

[Add your license here]

---

**SwiftView** is actively developed with regular feature updates and performance improvements.