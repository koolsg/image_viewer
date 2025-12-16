# TODO List

## Bugs/Stabilization
- [ ] Check scroll/transform state inconsistency when switching between HQ prescale/normal path in Fit mode


## Features
- [ ] HQ Downscale quality automation: Apply BICUBIC + GaussianBlur(0.4~0.6) for heavy downscaling (scale < 0.6), Lanczos otherwise
- [ ] HQ prescale debounce: Resample only once 150~250ms after resize ends
- [ ] Save/restore HQ toggle/filter/blur/gamma-aware options in settings.json
- [ ] Make prefetch window size (back 3/ahead 5) configurable
- [ ] Introduce current frame priority processing (priority queue/epoch), ignore stale results
- [ ] Add cursor-based zoom/pan lock option during left-click temporary zoom


## Refactoring
- [ ] HQ path: Add viewport alignment (1:1 placement) option and code separation
- [ ] Modularize loader/sliding window logic (maintain_decode_window → util)
