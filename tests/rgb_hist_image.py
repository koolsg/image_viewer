#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
scripts/rgb_hist_image.py

JPG(또는 일반 이미지) 파일을 열어, 지정한 열(col) 또는 행(row)의 픽셀을
한쪽 끝에서 다른 쪽 끝까지 읽어 RGB 기준 도수분포를 출력합니다.

추가 정보:
- 평균/표준편차, 평균색 스와치, 1~5σ 내 포함 비율, 평균에서 가장 먼 색 Top-2 표시

사용 예:
  # 열(가장 왼쪽 0열)
  uv run python scripts/rgb_hist_image.py --input scripts/2.jpg --col 0
  # 행(맨 위 0행)
  uv run python scripts/rgb_hist_image.py --input scripts/2.jpg --row 0

출력:
  (스와치) #RRGGBB,count, dist=…  (빈도 내림차순)
  Mean/Std/Within kσ, Farthest colors …
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Tuple

# 전역 import (함수 내부 import 지양)
try:
    import pyvips  # type: ignore
    import numpy as np  # type: ignore
except Exception as exc:
    print(f"[오류] 필요한 모듈 로드 실패: {exc}", file=sys.stderr)
    raise


# 조사할 열 인덱스 설정 (0-기반)
# 예) 가장 왼쪽 열: 0, 다음 열: 1 ...
COLUMN_INDEX: int = 0
# 히스토그램 행마다 함께 출력할 스와치(박스)의 가로 셀 수
SWATCH_CELLS: int = 4


def _to_hex(rgb: Tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"

def _print_color_swatch(rgb: Tuple[int, int, int], width: int = 8, height: int = 2) -> None:
    """ANSI 배경색으로 작은 색상 박스를 터미널에 출력합니다.
    Windows PowerShell/Windows Terminal 등 ANSI 지원 환경에서 동작합니다.
    """
    try:
        r, g, b = rgb
        block = "  "  # 두 칸(가로 픽셀 느낌)
        line = f"\x1b[48;2;{r};{g};{b}m" + (block * width) + "\x1b[0m"
        for _ in range(height):
            print(line)
    except Exception:
        pass

def _swatch_inline(rgb: Tuple[int, int, int], cells: int = SWATCH_CELLS) -> str:
    """한 줄에 함께 출력할 작은 색상 박스 문자열(ANSI 배경색)을 생성합니다."""
    try:
        r, g, b = rgb
        return f"\x1b[48;2;{r};{g};{b}m" + (" " * max(1, int(cells))) + "\x1b[0m"
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="이미지의 지정 열/행 RGB 도수분포 출력")
    ap.add_argument("--input", "-i", required=True, help="입력 이미지 경로 (jpg/png/webp 등)")
    group = ap.add_mutually_exclusive_group(required=False)
    group.add_argument("--col", type=int, default=None, help="조사할 열 인덱스(0-기반)")
    group.add_argument("--row", type=int, default=None, help="조사할 행 인덱스(0-기반)")
    ap.add_argument("--limit", type=int, default=0, help="상위 N개만 출력(0=전체)")
    args = ap.parse_args()

    path = args.input
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(os.getcwd(), path))
    if not os.path.exists(path):
        print(f"[오류] 입력 파일을 찾을 수 없습니다: {path}", file=sys.stderr)
        return 2

    try:
        img = pyvips.Image.new_from_file(path, access="sequential")
        try:
            img = img.colourspace("srgb")
        except Exception:
            pass
        if img.hasalpha():
            img = img.flatten(background=[0, 0, 0])
        if img.bands > 3:
            # 0번부터 3밴드(RGB)만 추출
            img = img.extract_band(0, 3)
        elif img.bands < 3:
            # 단일/2밴드 이미지는 RGB로 확장
            img = pyvips.Image.bandjoin([img] * 3)
        if img.format != "uchar":
            img = img.cast("uchar")

        W, H = img.width, img.height
        if W <= 0 or H <= 0:
            print("[오류] 잘못된 이미지 크기", file=sys.stderr)
            return 4
        mem = img.write_to_memory()
        arr = np.frombuffer(mem, dtype=np.uint8).reshape(H, W, 3)
    except Exception as exc:
        print(f"[오류] 이미지 읽기 실패: {exc}", file=sys.stderr)
        return 6

    # 지정 열(col) 또는 행(row) 선택
    mode = "col"
    idx = COLUMN_INDEX
    if args.col is not None:
        idx = int(args.col)
        mode = "col"
        if idx < 0 or idx >= W:
            print(f"[오류] 열 인덱스 범위 초과: 0 <= col < {W}", file=sys.stderr)
            return 5
        line_rgb_full = arr[:, idx, :]  # (H,3)
        N = H
    elif args.row is not None:
        idx = int(args.row)
        mode = "row"
        if idx < 0 or idx >= H:
            print(f"[오류] 행 인덱스 범위 초과: 0 <= row < {H}", file=sys.stderr)
            return 5
        line_rgb_full = arr[idx, :, :]  # (W,3)
        N = W
    else:
        # 기본: 가장 왼쪽 열
        mode = "col"
        idx = COLUMN_INDEX
        if idx < 0 or idx >= W:
            print(f"[오류] 열 인덱스 범위 초과: 0 <= col < {W}", file=sys.stderr)
            return 5
        line_rgb_full = arr[:, idx, :]
        N = H

    # 집계(히스토그램)
    hist: Counter[Tuple[int, int, int]] = Counter()
    for i in range(N):
        r, g, b = int(line_rgb_full[i, 0]), int(line_rgb_full[i, 1]), int(line_rgb_full[i, 2])
        hist[(r, g, b)] += 1

    # 통계(평균/표준편차)를 먼저 계산해 평균과의 거리(dist)를 같이 표시
    try:
        column_rgb = line_rgb_full.astype(np.float64)  # (N,3)
        mean_rgb_f = column_rgb.mean(axis=0)
        std_rgb_f = column_rgb.std(axis=0, ddof=0)
        mean_rgb = tuple(int(round(x)) for x in mean_rgb_f.tolist())  # type: ignore
        std_tuple = tuple(float(x) for x in std_rgb_f.tolist())
    except Exception as exc:
        print(f"[경고] 통계 계산 실패(거리 출력 생략): {exc}", file=sys.stderr)
        mean_rgb = None  # type: ignore
        std_tuple = None  # type: ignore

    items = hist.most_common()
    if args.limit and args.limit > 0:
        items = items[: args.limit]

    for (r, g, b), cnt in items:
        sw = _swatch_inline((r, g, b), cells=SWATCH_CELLS)
        if mean_rgb is not None:
            dr = r - mean_rgb[0]
            dg = g - mean_rgb[1]
            db = b - mean_rgb[2]
            dist = (dr * dr + dg * dg + db * db) ** 0.5  # Euclidean RGB 거리
            print(f"{sw} {_to_hex((r, g, b))},{cnt}, dist={dist:.2f}")
        else:
            print(f"{sw} {_to_hex((r, g, b))},{cnt}")

    # 평균/표준편차 및 평균색 박스 출력 + 시그마 범위 비율(1~5σ)
    if mean_rgb is not None and std_tuple is not None:
        print("")
        print(f"Mean RGB: {mean_rgb} ({_to_hex(mean_rgb)})")
        print(f"StdDev  : (R={std_tuple[0]:.2f}, G={std_tuple[1]:.2f}, B={std_tuple[2]:.2f})")
        _print_color_swatch(mean_rgb, width=8, height=2)

        # 1~5σ 내 포함 비율 (대각 공분산 가정 Mahalanobis 거리)
        try:
            mu = mean_rgb_f  # (3,)
            sigma = std_tuple  # (3,)
            sigma_arr = np.array(sigma, dtype=np.float64)
            # 작은 값 보호
            sigma_safe = np.where(sigma_arr > 1e-9, sigma_arr, 1e-9)
            drgb = (column_rgb - mu) / sigma_safe  # (H,3)
            d_sigma = np.sqrt((drgb ** 2).sum(axis=1))  # (N,)
            for k in range(1, 6):
                inside = (d_sigma <= float(k))
                cnt = int(inside.sum())
                pct = 100.0 * cnt / float(N)
                print(f"Within {k}σ: {pct:.2f}% ({cnt}/{N})")

            # 평균에서 가장 멀리 떨어진 색상 Top-2 (유니크 컬러 기준)
            def _dsigma_of(rgb: Tuple[int, int, int]) -> float:
                r, g, b = rgb
                dr = (float(r) - float(mu[0])) / float(sigma_safe[0])
                dg = (float(g) - float(mu[1])) / float(sigma_safe[1])
                db = (float(b) - float(mu[2])) / float(sigma_safe[2])
                return (dr * dr + dg * dg + db * db) ** 0.5

            # 고유 색상들 중 d_sigma가 큰 순으로 상위 2개
            uniq_with_dist = [((r, g, b), _dsigma_of((r, g, b)), cnt) for (r, g, b), cnt in hist.items()]
            uniq_with_dist.sort(key=lambda t: t[1], reverse=True)
            topN = uniq_with_dist[:2]
            if topN:
                print("")
                print("Farthest colors from mean (by σ):")
                for (r, g, b), dsg, cnt in topN:
                    sw = _swatch_inline((r, g, b), cells=SWATCH_CELLS)
                    pct = 100.0 * cnt / float(N)
                    print(f"{sw} {_to_hex((r, g, b))}, d_sigma={dsg:.2f}, count={cnt} ({pct:.2f}%)")
        except Exception as exc:
            print(f"[경고] 시그마 범위 계산 실패: {exc}", file=sys.stderr)

    target_label = f"열={idx}" if mode == "col" else f"행={idx}"
    length_label = f"길이={N}"
    print(f"[요약] {target_label}, {length_label}, 고유 RGB={len(hist)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
