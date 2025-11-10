import os
from typing import Optional, Tuple







def detect_trim_box_stats(path: str, profile: str = "normal") -> Optional[Tuple[int, int, int, int]]:
    """
    행/열별 비배경 비율(r)과 표준편차(s)를 이용한 경계 검출(개선판).

    변경/개선 사항:
    - 허용 오차 ε 도입: 배경과의 차이가 작으면 배경으로 간주
    - Y(밝기) 기반 판정: 크로마 번짐 영향 최소화
    - 다중 열/행 윈도우 스무딩: r_col/r_row 이동평균으로 노이즈 완화
    - 민감도/임계/overscan 수치 조정(얇은 테두리 제거 강화)
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

        # 1) 밝기(Y) 기반 차이 맵 산출 (크로마 번짐 억제)
        arr16 = arr.astype(np.int16)
        bg16 = bg.astype(np.int16)
        y = (0.2126 * arr16[:, :, 0] + 0.7152 * arr16[:, :, 1] + 0.0722 * arr16[:, :, 2]).astype(np.float32)
        y_bg = float(0.2126 * bg16[0] + 0.7152 * bg16[1] + 0.0722 * bg16[2])
        d = np.abs(y - y_bg)  # HxW (밝기 차이)

        # 2) 허용 오차/임계/스무딩/오버스캔 프로파일 결정
        p = (profile or "normal").lower()
        if p == "aggressive":
            eps = 2.0
            k_smooth = 5
            tau_r = 0.002   # 0.2%
            tau_s = 3.0
            overscan_iters = 4
            bg_ratio_thr = 0.997
        else:  # normal
            eps = 3.0
            k_smooth = 5
            tau_r = 0.005   # 0.5%
            tau_s = 4.0
            overscan_iters = 3
            bg_ratio_thr = 0.995
        non_bg = (d > eps)

        # 3) r/s 통계 + 스무딩(이동평균)
        r_row = non_bg.mean(axis=1)  # (H,)
        r_col = non_bg.mean(axis=0)  # (W,)
        s_row = d.std(axis=1)
        s_col = d.std(axis=0)

        def _smooth_1d(a: np.ndarray, k: int = 5) -> np.ndarray:
            if k <= 1 or a.size <= 1:
                return a
            k = int(max(1, k))
            w = np.ones((k,), dtype=np.float32) / float(k)
            pad = k // 2
            ap = np.pad(a.astype(np.float32), (pad, pad), mode="edge")
            return np.convolve(ap, w, mode="valid")

        r_row_s = _smooth_1d(r_row, k=k_smooth)
        r_col_s = _smooth_1d(r_col, k=k_smooth)

        def find_top():
            for y in range(H):
                if r_row_s[y] > tau_r or s_row[y] > tau_s:
                    return y
            return 0
        def find_bottom():
            for y in range(H - 1, -1, -1):
                if r_row_s[y] > tau_r or s_row[y] > tau_s:
                    return y
            return H - 1
        def find_left():
            for x in range(W):
                if r_col_s[x] > tau_r or s_col[x] > tau_s:
                    return x
            return 0
        def find_right():
            for x in range(W - 1, -1, -1):
                if r_col_s[x] > tau_r or s_col[x] > tau_s:
                    return x
            return W - 1

        top = find_top()
        bottom = find_bottom()
        left = find_left()
        right = find_right()

        # 5) overscan: 경계 부근 배경 비율이 충분히 높으면 한 칸 더 깎기
        def row_bg_ratio(y_: int) -> float:
            if y_ < 0 or y_ >= H:
                return 1.0
            return float((d[y_, :] <= eps).mean())
        def col_bg_ratio(x_: int) -> float:
            if x_ < 0 or x_ >= W:
                return 1.0
            return float((d[:, x_] <= eps).mean())
        for _ in range(int(overscan_iters)):
            if row_bg_ratio(top) >= bg_ratio_thr:
                top += 1
            if row_bg_ratio(bottom) >= bg_ratio_thr:
                bottom -= 1
            if col_bg_ratio(left) >= bg_ratio_thr:
                left += 1
            if col_bg_ratio(right) >= bg_ratio_thr:
                right -= 1

        # 6) 무효/무변화 방지: 원본과 동일 크기면 None
        new_w = max(0, right - left + 1)
        new_h = max(0, bottom - top + 1)
        if new_w <= 0 or new_h <= 0:
            return None
        if (left <= 0 and top <= 0 and right >= W - 1 and bottom >= H - 1) or (new_w == W and new_h == H):
            return None

        return int(left), int(top), int(new_w), int(new_h)
    except Exception:
        return None







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







from typing import Optional


def apply_trim_to_file(path: str, crop, overwrite: bool, alg: Optional[str] = None) -> str:
    import pyvips  # type: ignore
    l, t, w, h = crop
    # 로그: 읽기 시작
    try:
        _logger.debug("[trim] read begin: %s", path)
    except Exception:
        pass
    img = pyvips.Image.new_from_file(path, access="sequential")
    try:
        img = img.colourspace("srgb")
    except Exception:
        pass
    if img.hasalpha():
        img = img.flatten(background=[0, 0, 0])
    if img.bands > 3:
        img = img.extract_band(0, 3)
    try:
        img = img.copy_memory()
    except Exception:
        pass
    try:
        _logger.debug("[trim] read ok: size=(%s,%s)", img.width, img.height)
    except Exception:
        pass
    trimmed = img.crop(l, t, w, h)
    base, ext = os.path.splitext(path)
    if overwrite:
        out_path = path
    else:
        suffix = "_trimmed"
        if isinstance(alg, str) and alg.lower() == "stats":
            suffix = f"{suffix}_{alg.lower()}"
        out_path = f"{base}{suffix}{ext}"
    # 경로 정규화 (Windows/libvips 호환성 향상)
    try:
        out_path = os.path.abspath(out_path)
        out_path = os.path.normpath(out_path)
    except Exception:
        pass
    """
    if overwrite:
        try:
            _logger.debug("[trim] send2trash begin: %s", path)
        except Exception:
            pass
        try:
            from send2trash import send2trash

            send2trash(os.path.abspath(path))
            _logger.debug("[trim] send2trash ok: %s", os.path.abspath(path))
        except Exception as e:
            try:
                _logger.debug("[trim] send2trash err: %s -> %r", os.path.abspath(path), e)
            except Exception:
                pass
                """
    if overwrite:
        # 덮어쓰기: tmp에 저장 후 원자 교체
        try:
            from uuid import uuid4
            dir_name = os.path.dirname(out_path)
            ext2 = os.path.splitext(out_path)[1]
            tmp_out = os.path.join(dir_name, f".__tmp_trim_{uuid4().hex}{ext2}")
        except Exception:
            tmp_out = out_path + ".__tmp_trim"
        try:
            _logger.debug("[trim] write tmp begin: %s", tmp_out)
        except Exception:
            pass
        trimmed.write_to_file(tmp_out)
        try:
            _logger.debug("[trim] write tmp ok: %s", tmp_out)
        except Exception:
            pass
        try:
            _logger.debug("[trim] replace begin: %s -> %s", tmp_out, out_path)
        except Exception:
            pass
        try:
            os.replace(tmp_out, out_path)
            _logger.debug("[trim] replace ok: %s", out_path)
        except Exception as e:
            try:
                _logger.debug("[trim] replace err: %s -> %s : %r", tmp_out, out_path, e)
            except Exception:
                pass
            try:
                if os.path.exists(tmp_out):
                    os.remove(tmp_out)
            except Exception:
                pass
            raise
    else:
        try:
            _logger.debug("[trim] write begin: %s", out_path)
        except Exception:
            pass
        trimmed.write_to_file(out_path)
        try:
            _logger.debug("[trim] write ok: %s", out_path)
        except Exception:
            pass
    return out_path
from .logger import get_logger
_logger = get_logger("trim")
