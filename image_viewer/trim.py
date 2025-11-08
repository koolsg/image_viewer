import os
from typing import Optional, Tuple


def detect_trim_box_mask(path: str) -> Optional[Tuple[int, int, int, int]]:
    """큰 흰(또는 검정) 캔버스 위에 콘텐츠가 얹힌 경우를 강건하게 처리.

    접근: '배경색과 충분히 다른' 픽셀로 이루어진 콘텐츠 마스크를 만들고,
    그 마스크의 최소 경계 사각형(Bounding Box)을 트림 박스로 사용한다.

    - 배경색(bg)은 네 변(상/하/좌/우) 외곽 픽셀에서 최빈 RGB로 추정
    - 픽셀을 bg와의 맨해튼 거리로 비교하여 비배경(non-bg) 마스크 생성
    - 마스크가 비어있지 않다면 그 최소/최대 x,y로 박스 산출
    - 얇게 남는 배경을 없애기 위해 가장자리에서 최대 2px 추가 트림(overscan, 99% 이상 bg일 때)
    """
    try:
        import pyvips  # type: ignore
        import numpy as np  # type: ignore

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

        W, H = img.width, img.height
        if W <= 0 or H <= 0:
            return None

        mem = img.write_to_memory()
        arr = np.frombuffer(mem, dtype=np.uint8).reshape(H, W, 3)

        # 배경 컬러 추정: 좌/우/상/하 외곽에서 대표 색(최빈 RGB)을 추출
        def mode_rgb(samples: np.ndarray) -> np.ndarray:
            # samples: (N,3) uint8
            if samples.size == 0:
                return np.array([255, 255, 255], dtype=np.uint8)
            # 해시를 위해 32비트로 패킹
            packed = samples.astype(np.uint32)
            key = (packed[:, 0] << 16) | (packed[:, 1] << 8) | packed[:, 2]
            vals, counts = np.unique(key, return_counts=True)
            m = vals[np.argmax(counts)]
            return np.array([(m >> 16) & 0xFF, (m >> 8) & 0xFF, m & 0xFF], dtype=np.uint8)

        edge_samples = np.vstack([
            arr[0, :, :],           # top row
            arr[-1, :, :],          # bottom row
            arr[:, 0, :],           # left col
            arr[:, -1, :],          # right col
        ])
        bg = mode_rgb(edge_samples.reshape(-1, 3))

        # 1) non-bg 마스크 생성(배경과 충분히 다른 픽셀)
        delta = 6  # 엄격한 배경/콘텐츠 구분
        diff = np.abs(arr.astype(np.int16) - bg.astype(np.int16))
        non_bg = (diff.sum(axis=2) > delta)

        ys, xs = np.where(non_bg)
        if ys.size == 0 or xs.size == 0:
            return None
        top = int(ys.min())
        bottom = int(ys.max())
        left = int(xs.min())
        right = int(xs.max())

        # 자를 게 없으면 None
        if left == 0 and top == 0 and right == W - 1 and bottom == H - 1:
            return None

        # 보수적 방어: 범위 확인
        # 2) overscan: 테두리에서 최대 2px 추가로 줄여 남는 배경 제거
        extra = 2
        def row_bg_ratio(y: int) -> float:
            if y < 0 or y >= H:
                return 1.0
            d = np.abs(arr[y, :, :].astype(np.int16) - bg.astype(np.int16)).sum(axis=1)
            return float((d <= 4).sum() / max(1, W))
        def col_bg_ratio(x: int) -> float:
            if x < 0 or x >= W:
                return 1.0
            d = np.abs(arr[:, x, :].astype(np.int16) - bg.astype(np.int16)).sum(axis=1)
            return float((d <= 4).sum() / max(1, H))

        for _ in range(extra):
            if row_bg_ratio(top) >= 0.99:
                top += 1
            if row_bg_ratio(bottom) >= 0.99:
                bottom -= 1
            if col_bg_ratio(left) >= 0.99:
                left += 1
            if col_bg_ratio(right) >= 0.99:
                right -= 1

        new_w = max(0, right - left + 1)
        new_h = max(0, bottom - top + 1)
        if new_w <= 0 or new_h <= 0:
            return None
        # 원본과 동일한 크기면 트림할 필요 없음
        if left <= 0 and top <= 0 and right >= W - 1 and bottom >= H - 1:
            return None
        if new_w == W and new_h == H:
            return None
        return int(left), int(top), int(new_w), int(new_h)
    except Exception:
        return None


def detect_trim_box_stats(path: str) -> Optional[Tuple[int, int, int, int]]:
    """행/열별 비배경 비율(r)과 표준편차(s)를 이용한 경계 검출.

    - 배경(bg): 외곽 최빈 RGB
    - d = |pix - bg|_1
    - r_row[y] = mean(d[y, :] > delta), s_row[y] = std(d[y, :])
      r_col[x] = mean(d[:, x] > delta), s_col[x] = std(d[:, x])
    - top = min y s.t. r>tau_r or s>tau_s; bottom/left/right 유사
    - overscan 2px (해당 라인이 거의 배경(≥99%)이면 한 칸 더)
    """
    try:
        import pyvips  # type: ignore
        import numpy as np  # type: ignore

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
        W, H = img.width, img.height
        if W <= 0 or H <= 0:
            return None
        mem = img.write_to_memory()
        arr = np.frombuffer(mem, dtype=np.uint8).reshape(H, W, 3)

        # 배경색 추정(외곽 최빈 RGB)
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

        d = np.abs(arr.astype(np.int16) - bg.astype(np.int16)).sum(axis=2)  # HxW
        delta = 6
        r_row = (d > delta).mean(axis=1)
        r_col = (d > delta).mean(axis=0)
        s_row = d.std(axis=1)
        s_col = d.std(axis=0)

        tau_r = 0.02  # 2% 비배경 비율
        tau_s = 8.0   # 표준편차 임계

        def find_top():
            for y in range(H):
                if r_row[y] > tau_r or s_row[y] > tau_s:
                    return y
            return 0
        def find_bottom():
            for y in range(H - 1, -1, -1):
                if r_row[y] > tau_r or s_row[y] > tau_s:
                    return y
            return H - 1
        def find_left():
            for x in range(W):
                if r_col[x] > tau_r or s_col[x] > tau_s:
                    return x
            return 0
        def find_right():
            for x in range(W - 1, -1, -1):
                if r_col[x] > tau_r or s_col[x] > tau_s:
                    return x
            return W - 1

        top = find_top()
        bottom = find_bottom()
        left = find_left()
        right = find_right()

        # overscan 2px
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
                top += 1
            if row_bg_ratio(bottom) >= 0.99:
                bottom -= 1
            if col_bg_ratio(left) >= 0.99:
                left += 1
            if col_bg_ratio(right) >= 0.99:
                right -= 1

        new_w = max(0, right - left + 1)
        new_h = max(0, bottom - top + 1)
        if new_w <= 0 or new_h <= 0:
            return None
        return int(left), int(top), int(new_w), int(new_h)
    except Exception:
        return None


def detect_trim_box(path: str) -> Optional[Tuple[int, int, int, int]]:
    """기본 탐지(마스크 기반) 래퍼. 필요 시 다른 알고리즘으로 교체 가능."""
    box = detect_trim_box_mask(path)
    return box


def make_trim_preview(path: str, crop, view_w: int, view_h: int):
    try:
        from PySide6.QtGui import QImage, QPixmap
        import pyvips  # type: ignore
        import numpy as np  # type: ignore
        l, t, w, h = crop
        img = pyvips.Image.new_from_file(path, access="sequential")
        try:
            img = img.colourspace("srgb")
        except Exception:
            pass
        if img.hasalpha():
            img = img.flatten(background=[0, 0, 0])
        if img.bands > 3:
            img = img.extract_band(0, 3)
        src = img
        dst = img.crop(l, t, w, h)
        gap = 24  # 프리뷰 사이 여백
        landscape = src.width >= src.height
        if landscape:
            target_h_each = max(1, view_h // 2)
            s1 = src.resize(target_h_each / src.height, vscale=target_h_each / src.height)
            s2 = dst.resize(target_h_each / dst.height, vscale=target_h_each / dst.height)
            width_max = max(s1.width, s2.width)
            canvas = pyvips.Image.black(width_max, s1.height + gap + s2.height, bands=3)
            canvas = canvas.insert(s1, 0, 0)
            canvas = canvas.insert(s2, 0, s1.height + gap)
        else:
            target_w_each = max(1, view_w // 2)
            s1 = src.resize(target_w_each / src.width)
            s2 = dst.resize(target_w_each / dst.width)
            height_max = max(s1.height, s2.height)
            canvas = pyvips.Image.black(s1.width + gap + s2.width, height_max, bands=3)
            canvas = canvas.insert(s1, 0, 0)
            canvas = canvas.insert(s2, s1.width + gap, 0)
        mem = canvas.write_to_memory()
        arr = np.frombuffer(mem, dtype=np.uint8).reshape(canvas.height, canvas.width, canvas.bands)
        qimg = QImage(arr.data, canvas.width, canvas.height, canvas.width * 3, QImage.Format_RGB888)
        return QPixmap.fromImage(qimg)
    except Exception:
        return None


def make_dual_preview(path: str, crop1, crop2, view_w: int, view_h: int):
    """두 알고리즘 결과를 좌우로 비교하는 프리뷰 생성."""
    try:
        from PySide6.QtGui import QImage, QPixmap
        import pyvips  # type: ignore
        import numpy as np  # type: ignore
        img = pyvips.Image.new_from_file(path, access="sequential")
        try:
            img = img.colourspace("srgb")
        except Exception:
            pass
        if img.hasalpha():
            img = img.flatten(background=[0, 0, 0])
        if img.bands > 3:
            img = img.extract_band(0, 3)
        # 두 버전 크롭
        def crop_to_image(crop):
            if not crop:
                return None
            l, t, w, h = crop
            return img.crop(l, t, w, h)
        a = crop_to_image(crop1) or img
        b = crop_to_image(crop2) or img
        # 좌우 배치
        gap = 24  # 좌/우 결과 간 여백
        target_w_each = max(1, view_w // 2)
        a2 = a.resize(target_w_each / a.width)
        b2 = b.resize(target_w_each / b.width)
        height_max = max(a2.height, b2.height)
        canvas = pyvips.Image.black(a2.width + gap + b2.width, height_max, bands=3)
        canvas = canvas.insert(a2, 0, 0)
        canvas = canvas.insert(b2, a2.width + gap, 0)
        mem = canvas.write_to_memory()
        arr = np.frombuffer(mem, dtype=np.uint8).reshape(canvas.height, canvas.width, canvas.bands)
        qimg = QImage(arr.data, canvas.width, canvas.height, canvas.width * 3, QImage.Format_RGB888)
        return QPixmap.fromImage(qimg)
    except Exception:
        return None


from typing import Optional


def apply_trim_to_file(path: str, crop, overwrite: bool, alg: Optional[str] = None) -> str:
    import pyvips  # type: ignore
    l, t, w, h = crop
    img = pyvips.Image.new_from_file(path, access="sequential")
    try:
        img = img.colourspace("srgb")
    except Exception:
        pass
    if img.hasalpha():
        img = img.flatten(background=[0, 0, 0])
    if img.bands > 3:
        img = img.extract_band(0, 3)
    trimmed = img.crop(l, t, w, h)
    base, ext = os.path.splitext(path)
    if overwrite:
        out_path = path
    else:
        suffix = "_trimmed"
        if isinstance(alg, str) and alg.lower() in ("mask", "stats"):
            suffix = f"{suffix}_{alg.lower()}"
        out_path = f"{base}{suffix}{ext}"
    if overwrite:
        try:
            from send2trash import send2trash
            send2trash(os.path.abspath(path))
        except Exception:
            pass
    trimmed.write_to_file(out_path)
    return out_path
