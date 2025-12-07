"""Image Engine - Backend/Server layer for image processing.

This package provides the core data and processing functionality:
- File system management (fs_model)
- Image decoding (decoder, loader)
- Caching (cache, thumbnail_cache)
- Decoding strategies (strategy)

Usage:
    from image_viewer.image_engine import ImageEngine

    engine = ImageEngine()
    engine.image_ready.connect(on_image_ready)
    engine.open_folder("/path/to/images")
    engine.request_decode(path)
"""

from .engine import ImageEngine

__all__ = ["ImageEngine"]
