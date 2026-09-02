"""conflict_detector.py — phát hiện xung đột nhiều ngoại lệ (mục 5.3, 10).

Nhận exception dạng dict (duck-typed) để test độc lập không cần DB/Maps —
`nearest_available_vehicles_fn` được inject từ ngoài (Giai đoạn 6+, khi có
geocoder thật) thay vì gọi thẳng DB/API bên trong module này.

Mỗi exception dict kỳ vọng có: vehicle_id, driver_name (optional), schedule_id,
affected_stop_ids (list, optional), sub_type, area (optional), reported_at
(datetime, optional).
"""
from datetime import datetime

from sqlalchemy import select

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


def nearest_available_vehicles(db, company_id: str, exc: dict, top_n: int = 2) -> list[str]:
    """Xe active, không phải chính xe đang gặp sự cố, không đang bận (không
    gắn với 1 exception active khác), xếp gần nhất theo khoảng cách ước tính
    tới khu vực ngoại lệ (mục 5.3). Hệ thống không track GPS thời gian thực
    (mục 1: "vị trí xe do dispatcher nhập tay") nên coi xe rảnh đang ở khu
    vực kho mặc định của company — dùng `geocoder.distance_matrix` làm proxy
    khoảng cách kho↔khu vực ngoại lệ. Graceful degradation (mục 14): geocoder
    lỗi/hết hạn mức Maps → không có dữ liệu khoảng cách cho xe nào, fallback
    về thứ tự `vehicle_id` (không loại xe nào vì thiếu dữ liệu, đúng tinh
    thần mục 5.4 "thiếu dữ liệu không được làm hệ thống loại nhầm")."""
    from core.geocoder import distance_matrix
    from models import Company, Exception_, Vehicle

    busy_vehicle_ids = {
        row[0]
        for row in db.execute(
            select(Exception_.vehicle_id).where(
                Exception_.company_id == company_id,
                Exception_.status.in_(("pending", "analyzing", "awaiting_decision")),
                Exception_.vehicle_id.is_not(None),
            )
        ).all()
    }
    own_vehicle_id = exc.get("vehicle_id")
    candidates = db.execute(
        select(Vehicle).where(
            Vehicle.company_id == company_id,
            Vehicle.status == "active",
            Vehicle.vehicle_id != own_vehicle_id,
            Vehicle.deleted_at.is_(None),
        )
    ).scalars().all()
    candidates = [v for v in candidates if v.vehicle_id not in busy_vehicle_ids]

    company = db.get(Company, company_id)
    exc_area = exc.get("area")
    depot_area = company.default_depot_area if company else None

    ranked = []
    for v in sorted(candidates, key=lambda v: v.vehicle_id):
        distance_km = None
        if exc_area and depot_area:
            result = distance_matrix(db, depot_area, exc_area)
            distance_km = result["distance_km"] if result else None
        ranked.append((distance_km if distance_km is not None else float("inf"), v.vehicle_id))

    ranked.sort(key=lambda r: (r[0], r[1]))
    return [vehicle_id for _, vehicle_id in ranked[:top_n]]


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
