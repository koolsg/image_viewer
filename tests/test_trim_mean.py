#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
scripts/test_trim_mean.py

Mean–deviance(σ) 기반 경계 탐지로 폴더 내 모든 JPG를 트림하여
"파일명_trimmed.jpg"로 저장합니다. 스크립트가 위치한 폴더 내의 *.jpg 대상.

알고리즘(각 변에서 중앙 방향으로 1픽셀씩 진행):
1) 최외각 행/열에서 픽셀들의 mean, std 산출
2) 각 행/열에서 d_sigma = sqrt(((R-μR)/σR)^2 + ((G-μG)/σG)^2 + ((B-μB)/σB)^2)
   가 3 이하인 픽셀 비율이 90% 이상이면 배경으로 간주(조건 A)
3) 직전 행/열의 mean/std가 존재할 경우, 새 행/열의 mean이 직전 mean에서
   1σ(직전 std) 이하로 떨어져 있으면(조건 B) 역시 배경으로 간주
4) 조건 A,B 중 하나라도 불만족 시 콘텐츠 시작으로 판단하여 경계 확정

주의:
- σ가 0에 가까울 때는 작은 epsilon으로 나눗셈 보호
- sRGB 8비트(RGB)로 정규화 후 처리
"""

from __future__ import annotations

import glob
import os
import sys
from typing import Tuple

# 전역 import (함수 내부 import 지양)
try:
    import pyvips  # type: ignore
    import numpy as np  # type: ignore
except Exception as exc:
    print(f"[오류] 필요한 모듈 로드 실패: {exc}", file=sys.stderr)
    raise
os.add_dll_directory("C:\\Projects\\libraries\\vips-dev-8.17\\bin")

def _load_image_vips(path: str):
    img = pyvips.Image.new_from_file(path, access="sequential")
    try:
        img = img.colourspace("srgb")
    except Exception:
        pass
    if img.hasalpha():
        img = img.flatten(background=[0, 0, 0])
    if img.bands > 3:
        img = img.extract_band(0, 3)
    if img.format != "uchar":
        img = img.cast("uchar")
    # 후속 처리(크롭/저장)에서 임의 접근이 필요할 수 있으므로 메모리로 고정
    try:
        img = img.copy_memory()
    except Exception:
        pass
    return img


def _to_numpy(img) -> "np.ndarray":
    W, H = img.width, img.height
    mem = img.write_to_memory()
    arr = np.frombuffer(mem, dtype=np.uint8).reshape(H, W, 3)
    return arr


def _row_stats(arr, y: int) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    r = arr[y, :, 0].astype(np.float64)
    g = arr[y, :, 1].astype(np.float64)
    b = arr[y, :, 2].astype(np.float64)
    mu = (float(r.mean()), float(g.mean()), float(b.mean()))
    sd = (float(r.std(ddof=0)), float(g.std(ddof=0)), float(b.std(ddof=0)))
    return mu, sd


def _col_stats(arr, x: int) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    r = arr[:, x, 0].astype(np.float64)
    g = arr[:, x, 1].astype(np.float64)
    b = arr[:, x, 2].astype(np.float64)
    mu = (float(r.mean()), float(g.mean()), float(b.mean()))
    sd = (float(r.std(ddof=0)), float(g.std(ddof=0)), float(b.std(ddof=0)))
    return mu, sd


def _sigma_ratio_line_rgb(line_rgb: "np.ndarray", mu: Tuple[float, float, float], sd: Tuple[float, float, float], k: float) -> float:
    """한 줄(행 또는 열)의 RGB 픽셀들에 대해 d_sigma<=k 비율을 반환."""
    r = line_rgb[:, 0].astype(np.float64)
    g = line_rgb[:, 1].astype(np.float64)
    b = line_rgb[:, 2].astype(np.float64)
    sr = (r - mu[0]) / (sd[0] if sd[0] > 1e-9 else 1e-9)
    sg = (g - mu[1]) / (sd[1] if sd[1] > 1e-9 else 1e-9)
    sb = (b - mu[2]) / (sd[2] if sd[2] > 1e-9 else 1e-9)
    d_sigma = np.sqrt(sr * sr + sg * sg + sb * sb)
    ratio = float((d_sigma <= float(k)).mean())
    return ratio


def _sigma_mean_shift(mu_prev: Tuple[float, float, float], sd_prev: Tuple[float, float, float], mu_curr: Tuple[float, float, float]) -> float:
    """직전 평균/표준편차 기준으로 새 평균이 몇 σ만큼 떨어졌는지(d_sigma)를 계산."""
    import math
    dr = (mu_curr[0] - mu_prev[0]) / (sd_prev[0] if sd_prev[0] > 1e-9 else 1e-9)
    dg = (mu_curr[1] - mu_prev[1]) / (sd_prev[1] if sd_prev[1] > 1e-9 else 1e-9)
    db = (mu_curr[2] - mu_prev[2]) / (sd_prev[2] if sd_prev[2] > 1e-9 else 1e-9)
    return math.sqrt(dr * dr + dg * dg + db * db)


def _find_bounds(arr: "np.ndarray") -> Tuple[int, int, int, int]:
    """mean-deviance 규칙으로 top,bottom,left,right 경계를 찾습니다."""
    H, W = arr.shape[0], arr.shape[1]

    # 상단(top)
    top = 0
    mu_prev_t = sd_prev_t = None
    while top < H:
        mu, sd = _row_stats(arr, top)
        ratio = _sigma_ratio_line_rgb(arr[top, :, :], mu, sd, k=3.0)
        condA = (ratio >= 0.90)
        condB = True if mu_prev_t is None else (_sigma_mean_shift(mu_prev_t, sd_prev_t, mu) <= 1.0)
        if condA and condB:
            mu_prev_t, sd_prev_t = mu, sd
            top += 1
        else:
            break
    if top >= H:
        top = H - 1

    # 하단(bottom)
    bottom = H - 1
    mu_prev_b = sd_prev_b = None
    while bottom >= 0:
        mu, sd = _row_stats(arr, bottom)
        ratio = _sigma_ratio_line_rgb(arr[bottom, :, :], mu, sd, k=3.0)
        condA = (ratio >= 0.90)
        condB = True if mu_prev_b is None else (_sigma_mean_shift(mu_prev_b, sd_prev_b, mu) <= 1.0)
        if condA and condB:
            mu_prev_b, sd_prev_b = mu, sd
            bottom -= 1
        else:
            break
    if bottom < 0:
        bottom = 0

    # 좌측(left)
    left = 0
    mu_prev_l = sd_prev_l = None
    while left < W:
        mu, sd = _col_stats(arr, left)
        ratio = _sigma_ratio_line_rgb(arr[:, left, :], mu, sd, k=3.0)
        condA = (ratio >= 0.90)
        condB = True if mu_prev_l is None else (_sigma_mean_shift(mu_prev_l, sd_prev_l, mu) <= 1.0)
        if condA and condB:
            mu_prev_l, sd_prev_l = mu, sd
            left += 1
        else:
            break
    if left >= W:
        left = W - 1

    # 우측(right)
    right = W - 1
    mu_prev_r = sd_prev_r = None
    while right >= 0:
        mu, sd = _col_stats(arr, right)
        ratio = _sigma_ratio_line_rgb(arr[:, right, :], mu, sd, k=3.0)
        condA = (ratio >= 0.90)
        condB = True if mu_prev_r is None else (_sigma_mean_shift(mu_prev_r, sd_prev_r, mu) <= 1.0)
        if condA and condB:
            mu_prev_r, sd_prev_r = mu, sd
            right -= 1
        else:
            break
    if right < 0:
        right = 0

    # 경계 보정(겹침 방지)
    if top > bottom:
        top = 0
        bottom = H - 1
    if left > right:
        left = 0
        right = W - 1
    return left, top, right, bottom


def _apply_crop_write_vips(img, crop_box: Tuple[int, int, int, int], out_path: str) -> None:
    l, t, r, b = crop_box
    w = max(1, r - l + 1)
    h = max(1, b - t + 1)
    cropped = img.crop(l, t, w, h)
    cropped.write_to_file(out_path)


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    jpgs = sorted(glob.glob(os.path.join(here, "*.jpg")))
    if not jpgs:
        print("[정보] 처리할 JPG가 없습니다.")
        return 0

    total = len(jpgs)
    for i, path in enumerate(jpgs, 1):
        try:
            img = _load_image_vips(path)
            arr = _to_numpy(img)
            l, t, r, b = _find_bounds(arr)

            base, ext = os.path.splitext(path)
            out_path = f"{base}_trimmed.jpg"

            # 원본과 동일 크기면 스킵
            if l == 0 and t == 0 and r == img.width - 1 and b == img.height - 1:
                print(f"[{i}/{total}] unchanged: {os.path.basename(path)}")
                continue

            _apply_crop_write_vips(img, (l, t, r, b), out_path)
            print(f"[{i}/{total}] trimmed: {os.path.basename(path)} -> {os.path.basename(out_path)}")
        except Exception as exc:
            print(f"[{i}/{total}] 실패: {os.path.basename(path)} ({exc})", file=sys.stderr)
            continue

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
