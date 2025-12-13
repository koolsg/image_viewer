_EPOCH_MS_THRESHOLD = 10**11


def to_mtime_ms_from_stat(stat_result) -> int:
    try:
        return int(stat_result.st_mtime_ns) // 1_000_000
    except Exception:
        try:
            return round(float(stat_result.st_mtime) * 1000.0)
        except Exception:
            return 0


def to_mtime_ms(value: float | None | int | None) -> int | None:
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if v >= _EPOCH_MS_THRESHOLD:
        return int(v)
    return round(v * 1000.0)
