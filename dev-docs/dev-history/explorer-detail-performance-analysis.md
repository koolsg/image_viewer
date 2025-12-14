# Explorer Detail Performance Analysis

This note explains why the context menu appears quickly in Thumbnail mode but slowly in Detail mode, and why switching from Thumbnail to Detail feels slow.

## Summary
- The context menu code is identical for both modes; the menu itself is cheap.
- The delay occurs before the menu is shown, during `QTreeView` layout and the model’s `data()` work in Detail view.
- Two main hotspots:
  1) Tree header auto-sizing (`QHeaderView.ResizeToContents` + `sizeHintForColumn`) — O(N × columns) over many rows.
  2) Resolution column computation that triggers `QImageReader` for many files to read image headers when Detail is first displayed.

## Where the context menu is built
- In `ThumbnailGridWidget` (`ui_explorer_grid.py`), `_show_context_menu` builds the same `QMenu` in both modes, connected via `customContextMenuRequested`.
- Since the same function runs in both modes, the slowness in Detail is not from the menu itself.

## Why Detail is heavier than Thumbnail
1) **Detail uses QTreeView with extra columns and automatic sizing**
   - In `load_folder()`, the Detail view sets:
     - `header.setSectionResizeMode(QHeaderView.ResizeToContents)`
     - Loops all columns and calls `sizeHintForColumn(col)` (which scans many rows)
   - On large folders this is expensive and runs when Detail becomes visible.

2) **The model provides Resolution data that may read image headers**
   - `ImageFileSystemModel.data()` calls `_meta_update_basic(path)` for every `data()` request.
   - For the Resolution column, `_resolution_str()` uses `QImageReader(path)` if width/height aren’t cached yet.
   - First display of Detail on a big folder can open many files just to read dimensions.

These costs are largely absent in Thumbnail mode, which only shows a single Name column with icons and relies on cached thumbnails.

## Why Thumbnail→Detail switching feels slow
- First time Detail is shown:
  1) QTreeView performs layout with `ResizeToContents` and column size hints (row scanning).
  2) The model is queried for `DisplayRole` in the Resolution column across many rows, causing `QImageReader` header reads.
- The context menu in Detail can be delayed by the same pre-menu layout/data work.

## Quick diagnostics (to verify)
- Temporarily comment out in `load_folder()`:
  - `header.setSectionResizeMode(QHeaderView.ResizeToContents)`
  - The `for col in ... sizeHintForColumn` loop
- Temporarily change `_resolution_str()` to return an empty string without using `QImageReader`.
- Re-run and observe faster Detail context menu and faster Thumbnail→Detail switch. This confirms the hotspots.

## Improvement options
1) **Avoid ResizeToContents for large directories**
   - Use `QHeaderView.Interactive` with sane default widths; don’t recompute widths per-load.
   - Or sample a small subset of rows to estimate widths.
2) **Lazy/background resolution**
   - Compute resolution only for visible rows and cache it; or move header-reading to a background task and emit `dataChanged` as values arrive.
3) **Reduce work in `data()`**
   - Cache basic file info on `directoryLoaded` once per path, rather than redoing it in every `data()` call.
4) **Optional: direct context menu hook on QTreeView**
   - If needed, attach a minimal context-menu handler on the tree that doesn’t trigger a full relayout before showing the menu.

These changes should keep Detail functional while making the context menu responsive and the mode switch much faster.

## Implementation Status

| 문서의 제안 | 우리가 구현한 것 |
|------------|-----------------|
| _meta_update_basic() 매번 호출 문제 | ✅ 모든 호출 제거 |
| QImageReader 헤더 읽기 문제 | ✅ 사전 로딩 (_preload_resolution_info) |
| data() 호출마다 파일 접근 | ✅ 캐시만 사용 |
| 폴더 로드 시 한 번만 캐싱 | ✅ batch_load_thumbnails() + 해상도 사전 로딩 |
| 컨텍스트 메뉴 자체는 문제 아님 | ✅ 맞음, 하지만 재사용으로 추가 최적화 |