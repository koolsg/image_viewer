#!/usr/bin/env python
"""Standalone tester for the stats-based trim algorithm.

Usage:
    python scripts/test_trim_stats.py --input path/to/image --output path/to/result

It prints decision details (background estimate, boundary discovery, overscan moves)
and writes the trimmed output only when the stats algorithm indicates a real crop.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import pytest
np = pytest.importorskip("numpy")
pyvips = pytest.importorskip("pyvips")
pytestmark = pytest.mark.imaging
os.add_dll_directory("C:\\Projects\\libraries\\vips-dev-8.17\\bin")

def detect_trim_box_stats_verbose(path: str) -> Tuple[Optional[Tuple[int, int, int, int]], list[str]]:
    logs: list[str] = []
    logs.append(f"Loading image: {path}")
    try:
        img = pyvips.Image.new_from_file(path, access="sequential")
        logs.append(f"Original size: {img.width}x{img.height}, bands={img.bands}, format={img.format}")
        try:
            img = img.colourspace("srgb")
        except Exception as exc:
            logs.append(f"colourspace conversion failed: {exc}")
        if img.hasalpha():
            logs.append("Image has alpha; flattening with default background")
            img = img.flatten(background=[0, 0, 0])
        if img.bands > 3:
            logs.append("More than 3 bands; extracting first 3")
            img = img.extract_band(0, 3)
        if img.format != "uchar":
            logs.append(f"Casting from {img.format} to uchar")
            img = img.cast("uchar")
        W, H = img.width, img.height
        if W <= 0 or H <= 0:
            logs.append("Invalid dimensions after preprocessing")
            return None, logs
        mem = img.write_to_memory()
        arr = np.frombuffer(mem, dtype=np.uint8).reshape(H, W, 3)

        def mode_rgb(samples: np.ndarray) -> np.ndarray:
            if samples.size == 0:
                return np.array([255, 255, 255], dtype=np.uint8)
            packed = samples.astype(np.uint32)
            key = (packed[:, 0] << 16) | (packed[:, 1] << 8) | packed[:, 2]
            vals, counts = np.unique(key, return_counts=True)
            m = vals[np.argmax(counts)]
            return np.array([(m >> 16) & 0xFF, (m >> 8) & 0xFF, m & 0xFF], dtype=np.uint8)

        edge_samples = np.vstack([arr[0, :, :], arr[-1, :, :], arr[:, 0, :], arr[:, -1, :]])
        bg = mode_rgb(edge_samples.reshape(-1, 3))
        logs.append(f"Estimated background RGB: {bg.tolist()}")

        d = np.abs(arr.astype(np.int16) - bg.astype(np.int16)).sum(axis=2)
        delta = 6
        r_row = (d > delta).mean(axis=1)
        r_col = (d > delta).mean(axis=0)
        s_row = d.std(axis=1)
        s_col = d.std(axis=0)
        tau_r = 0.02
        tau_s = 8.0
        logs.append(f"Thresholds: delta={delta}, tau_r={tau_r}, tau_s={tau_s}")

        def find_boundary(arr_r, arr_s, forward=True):
            rng = range(len(arr_r)) if forward else range(len(arr_r) - 1, -1, -1)
            for idx in rng:
                if arr_r[idx] > tau_r or arr_s[idx] > tau_s:
                    return idx, arr_r[idx], arr_s[idx]
            fallback = 0 if forward else len(arr_r) - 1
            return fallback, arr_r[fallback], arr_s[fallback]

        top, top_r, top_s = find_boundary(r_row, s_row, True)
        bottom, bottom_r, bottom_s = find_boundary(r_row, s_row, False)
        left, left_r, left_s = find_boundary(r_col, s_col, True)
        right, right_r, right_s = find_boundary(r_col, s_col, False)

        logs.append(f"Initial top boundary at {top} (r={top_r:.4f}, s={top_s:.2f})")
        logs.append(f"Initial bottom boundary at {bottom} (r={bottom_r:.4f}, s={bottom_s:.2f})")
        logs.append(f"Initial left boundary at {left} (r={left_r:.4f}, s={left_s:.2f})")
        logs.append(f"Initial right boundary at {right} (r={right_r:.4f}, s={right_s:.2f})")

        def row_bg_ratio(y: int) -> float:
            if y < 0 or y >= H:
                return 1.0
            return float((d[y, :] <= 4).mean())

        def col_bg_ratio(x: int) -> float:
            if x < 0 or x >= W:
                return 1.0
            return float((d[:, x] <= 4).mean())

        for _ in range(2):
            if row_bg_ratio(top) >= 0.99:
                logs.append(f"Overscan: row {top} almost background, moving top inward")
                top += 1
            if row_bg_ratio(bottom) >= 0.99:
                logs.append(f"Overscan: row {bottom} almost background, moving bottom inward")
                bottom -= 1
            if col_bg_ratio(left) >= 0.99:
                logs.append(f"Overscan: col {left} almost background, moving left inward")
                left += 1
            if col_bg_ratio(right) >= 0.99:
                logs.append(f"Overscan: col {right} almost background, moving right inward")
                right -= 1

        new_w = max(0, right - left + 1)
        new_h = max(0, bottom - top + 1)
        logs.append(f"Final box: left={left}, top={top}, width={new_w}, height={new_h}")
        if new_w <= 0 or new_h <= 0:
            logs.append("Invalid crop dimensions; skipping")
            return None, logs
        if left <= 0 and top <= 0 and right >= W - 1 and bottom >= H - 1:
            logs.append("Box covers entire image; skipping")
            return None, logs
        if new_w == W and new_h == H:
            logs.append("Dimensions unchanged; skipping")
            return None, logs
        logs.append(
            f"Trim delta: left -{left}, top -{top}, right -{W - 1 - right}, bottom -{H - 1 - bottom}"
        )
        return (int(left), int(top), int(new_w), int(new_h)), logs
    except Exception as exc:
        logs.append(f"Error during detection: {exc}")
        return None, logs


def trim_image(path: str, output: str, crop: Tuple[int, int, int, int], logs: list[str]) -> None:
    l, t, w, h = crop
    logs.append(f"Writing trimmed region ({w}x{h}) to {output}")
    img = pyvips.Image.new_from_file(path, access="sequential")
    trimmed = img.crop(l, t, w, h)
    trimmed.write_to_file(output)


def main() -> None:
    # 테스트용 경로를 직접 지정하세요.
    INPUT_PATH = "2.jpg"
    OUTPUT_PATH = "2_trimmed.jpg"

    crop, logs = detect_trim_box_stats_verbose(INPUT_PATH)
    for line in logs:
        print(line)
    if not crop:
        print("No trimming performed.")
        return
    if os.path.abspath(INPUT_PATH) == os.path.abspath(OUTPUT_PATH):
        print("Input and output paths are identical; aborting to avoid overwrite.")
        return
    trim_image(INPUT_PATH, OUTPUT_PATH, crop, logs)
    print("Trim complete.")


if __name__ == "__main__":
    main()
