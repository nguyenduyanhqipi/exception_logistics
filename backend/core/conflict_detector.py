"""conflict_detector.py — phát hiện xung đột nhiều ngoại lệ (mục 5.3, 10).

Nhận exception dạng dict (duck-typed) để test độc lập không cần DB/Maps —
`nearest_available_vehicles_fn` được inject từ ngoài (Giai đoạn 6+, khi có
geocoder thật) thay vì gọi thẳng DB/API bên trong module này.

Mỗi exception dict kỳ vọng có: vehicle_id, driver_name (optional), schedule_id,
affected_stop_ids (list, optional), sub_type, area (optional), reported_at
(datetime, optional).
"""
from datetime import datetime

NEEDS_REPLACEMENT_SUBTYPES = {"major_breakdown", "road_closed", "accident"}

HARD_SIGNALS = {"same_vehicle", "same_driver", "same_stop", "resource_contention"}


def needs_replacement_vehicle(exc: dict) -> bool:
    """mục 5.3 liệt kê cố định 3 sub_type: major_breakdown, road_closed,
    accident. Mở rộng thêm 1 trường hợp để khớp Kịch bản bonus mục 15: xe A bị
    `minor_breakdown` (thủng lốp, sửa 50 phút) VẪN được coi là "cần xe thay
    thế" một khi đã leo thang lên `serious` (mục 5.2: minor_breakdown leo
    thang serious nếu sửa > 30 phút) — một sự cố nhỏ nhưng đủ lâu để đáng cân
    nhắc điều xe thay vì chờ sửa. Không áp dụng cho minor_breakdown còn
    `warning` (sự cố thực sự nhỏ, vá nhanh) để tránh gọi
    `nearest_available_vehicles`/Maps API không cần thiết cho mọi hư hỏng vặt.
    """
    sub_type = exc.get("sub_type")
    if sub_type in NEEDS_REPLACEMENT_SUBTYPES:
        return True
    if sub_type == "minor_breakdown" and exc.get("severity") == "serious":
        return True
    return False


def _overlap(a, b) -> bool:
    return bool(set(a or []) & set(b or []))


def _time_overlap(a: dict, b: dict, window_min: int = 30) -> bool:
    ta, tb = a.get("reported_at"), b.get("reported_at")
    if not isinstance(ta, datetime) or not isinstance(tb, datetime):
        return False
    return abs((ta - tb).total_seconds()) <= window_min * 60


def detect_conflict(
    new_exc: dict,
    active_exceptions: list[dict],
    nearest_available_vehicles_fn=None,
) -> tuple[str, "dict | None", list[str]]:
    """Trả về (mode, existing_exception_xung_đột_hoặc_None, signals).

    `nearest_available_vehicles_fn(exc, top_n) -> list[vehicle_id]` — optional,
    chỉ cần truyền khi cả 2 exception đều `needs_replacement_vehicle`.
    """
    for existing in active_exceptions:
        signals = []

        if new_exc.get("vehicle_id") and new_exc["vehicle_id"] == existing.get("vehicle_id"):
            signals.append("same_vehicle")

        if new_exc.get("driver_name") and new_exc["driver_name"] == existing.get("driver_name"):
            signals.append("same_driver")

        if new_exc.get("schedule_id") and new_exc["schedule_id"] == existing.get("schedule_id"):
            if _overlap(new_exc.get("affected_stop_ids"), existing.get("affected_stop_ids")):
                signals.append("same_stop")

        if (
            nearest_available_vehicles_fn is not None
            and needs_replacement_vehicle(new_exc)
            and needs_replacement_vehicle(existing)
        ):
            new_candidates = nearest_available_vehicles_fn(new_exc, top_n=2)
            existing_candidates = nearest_available_vehicles_fn(existing, top_n=2)
            if _overlap(new_candidates, existing_candidates):
                signals.append("resource_contention")

        if (
            new_exc.get("area")
            and new_exc["area"] == existing.get("area")
            and _time_overlap(new_exc, existing, window_min=30)
        ):
            signals.append("same_area_same_time")  # tham khảo, KHÔNG kích hoạt combined

        if set(signals) & HARD_SIGNALS:
            return "combined", existing, signals

    return "independent", None, []
