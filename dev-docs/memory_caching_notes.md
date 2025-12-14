# Image Viewer – Memory and Cache Notes

Last updated: 2025-11-29

## Current pipeline
- Decode path: `pyvips -> numpy RGB array -> QImage/QPixmap` (see `decoder.py`, `loader.py`).
- Loader uses `ProcessPoolExecutor` for decoding and `ThreadPoolExecutor` for I/O scheduling.
- Viewer caches: in-memory pixmap cache + optional disk thumbnail cache per folder.

## Why RAM spikes to ~2 GB at 20 items
- A single 4K RGBA frame ≈ 32 MB. Keeping multiple variants (original/full, scaled/pixmap, thumbnail) multiplies usage.
- If both numpy buffer and QPixmap for the same image stay cached, memory roughly doubles.
- Language choice (Python/C++/C#) doesn’t change this materially; retained pixel buffers dominate.

## Numpy vs Pixmap retention
- Numpy arrays are needed for edit/compute paths (crop, filters, histograms, format convert).
- Pixmaps are needed only for display.
- Keeping both simultaneously is redundant for view-only scenarios; acceptable when editing is active.

### Suggested policy (future work)
- Separate “view cache” (pixmaps) and “edit cache” (numpy).  
  - View cache: LRU by recency; target budget e.g., 400–600 MB.
  - Edit cache: only current/last edited items; small budget; drop numpy when leaving edit mode.
- When not editing, drop numpy after pixmap is built; re-decode on demand for edits.

## Prefetch considerations
- Prefetch window (currently ahead/back) increases concurrent decodes; raises CPU/fan.
- Process pool worker count and prefetch window can be tuned to trade smoothness vs. load.
- Cancellation: when folder or selection jumps, cancel or ignore stale futures to avoid wasted decodes.

## Disk cache
- Thumbnails stored per-folder under `.cache/<name>`; key includes mtime+size to avoid staleness.
- Disk cache avoids re-decode; resolution column is filled from cache metadata when present.

## Action items (deferred)
- Implement dual-cache budgets (view/edit) with LRU and byte caps.
- Add setting to throttle prefetch window based on pending count/CPU.
- Optionally add `selection-background-color: transparent` & `show-decoration-selected: 0` for outline-only selection if we revisit thumbnail selection visuals.
