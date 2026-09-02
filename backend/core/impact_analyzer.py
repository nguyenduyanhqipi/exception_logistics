"""impact_analyzer.py — tính tác động của ngoại lệ (mục 5.2, 5.4 TECHNICAL_SPEC.md).

Chuyển 1 ngoại lệ + các điểm giao còn lại của chuyến thành các biến số rule
engine cần (`time_to_deadline_min`, `downstream_stops_affected`,
`has_priority_order`) và danh sách `affected_stops` (lưu vào
`impact_analysis.affected_stops`, mục 4).
"""
from datetime import date, datetime, time, timedelta

PRIORITY_TIERS_ALWAYS_HIGH = {"vip", "hop_dong_phat"}
SLA_PENALTY_THRESHOLD_DEFAULT = 500_000


def _to_time(value) -> "time | None":
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        return time.fromisoformat(value)
    raise TypeError(f"Không parse được thời gian: {value!r}")


def compute_affected_stops(
    stops: list[dict], delay_minutes: int, from_stop_order: int = 1, to_stop_order: "int | None" = None
) -> list[dict]:
    """Tính ETA mới + sla_breach cho các điểm giao bị ảnh hưởng, dịch đều theo
    `delay_minutes`.

    `to_stop_order=None` (mặc định) — ảnh hưởng DÂY CHUYỀN, từ `from_stop_order`
    đến hết chuyến (đúng cho delay/slow_loading/traffic_jam/road_closed/
    vehicle_issue — toàn bộ điểm phía sau đều bị đẩy lùi).
    `to_stop_order=X` — CHỈ ảnh hưởng 1 khoảng cụ thể [from_stop_order, X],
    không lan xuống các điểm sau (đúng cho customer_reject/customer_change —
    vấn đề cục bộ tại 1 điểm, không kéo lùi cả tuyến; xem Kịch bản 3 mục 15:
    điểm giao kế tiếp ghi rõ "Chưa bị ảnh hưởng").

    Mô hình đơn giản có chủ đích: cộng đều `delay_minutes` cho các điểm trong
    phạm vi ảnh hưởng — đủ để rule engine tính severity (mục 5.2). Mô hình
    tinh hơn (so sánh phương án đổi thứ tự điểm giao...) thuộc trách nhiệm của
    `option_generator.py` ở Giai đoạn 6, không phải impact_analyzer.
    """
    affected = []
    for stop in stops:
        if stop["stop_order"] < from_stop_order:
            continue
        if to_stop_order is not None and stop["stop_order"] > to_stop_order:
            continue
        eta = _to_time(stop.get("eta"))
        sla_deadline = _to_time(stop.get("sla_deadline"))
        new_eta = None
        if eta is not None:
            new_eta = (datetime.combine(date.today(), eta) + timedelta(minutes=delay_minutes)).time()
        sla_breach = new_eta > sla_deadline if (new_eta is not None and sla_deadline is not None) else None

        affected.append(
            {
                "stop_id": stop.get("stop_id"),
                "order_id": stop.get("order_id"),
                "delay_minutes": delay_minutes,
                "new_eta": new_eta.isoformat() if new_eta is not None else None,
                "sla_breach": sla_breach,
                "priority_tier": stop.get("priority_tier", "thuong"),
                "sla_penalty": stop.get("sla_penalty"),
                "sla_deadline": sla_deadline.isoformat() if sla_deadline is not None else None,
                "_sla_deadline_time": sla_deadline,  # dùng nội bộ cho compute_time_to_deadline_min, KHÔNG lưu vào DB
            }
        )
    return affected


def compute_time_to_deadline_min(affected_stops: list[dict], shift_date: date, now: datetime) -> "int | None":
    """Số phút còn lại đến `sla_deadline` GẦN NHẤT trong các điểm bị ảnh hưởng."""
    deadlines = [
        datetime.combine(shift_date, stop["_sla_deadline_time"])
        for stop in affected_stops
        if stop.get("_sla_deadline_time") is not None
    ]
    if not deadlines:
        return None
    return int((min(deadlines) - now).total_seconds() // 60)


def compute_downstream_stops_affected(affected_stops: list[dict]) -> int:
    return len(affected_stops)


def compute_has_priority_order(
    affected_stops: list[dict], sla_penalty_threshold: int = SLA_PENALTY_THRESHOLD_DEFAULT
) -> bool:
    for stop in affected_stops:
        if stop.get("priority_tier") in PRIORITY_TIERS_ALWAYS_HIGH:
            return True
        penalty = stop.get("sla_penalty")
        if penalty is not None and penalty > sla_penalty_threshold:
            return True
    return False


def analyze_impact(
    stops: list[dict],
    delay_minutes: int,
    from_stop_order: int,
    shift_date: date,
    now: datetime,
    to_stop_order: "int | None" = None,
) -> dict:
    """Hàm chính — trả về đủ input cho `rule_engine.calculate_severity()`."""
    affected_stops = compute_affected_stops(stops, delay_minutes, from_stop_order, to_stop_order)
    result = {
        "affected_stops": [{k: v for k, v in s.items() if k != "_sla_deadline_time"} for s in affected_stops],
        "time_to_deadline_min": compute_time_to_deadline_min(affected_stops, shift_date, now),
        "downstream_stops_affected": compute_downstream_stops_affected(affected_stops),
        "has_priority_order": compute_has_priority_order(affected_stops),
    }
    return result


def filter_vehicles_by_payload(candidate_vehicles: list, stops_to_transfer: list[dict], bulky_multiplier: float = 1.7) -> list:
    """Loại xe không đủ tải trọng khi tìm xe thay thế (mục 5.4).

    `candidate_vehicles`: list các object/dict có thuộc tính `max_payload_kg`.
    Nếu `volume_kg` bị bỏ trống HOÀN TOÀN ở mọi điểm cần chuyển -> không loại
    xe nào (tránh thiếu dữ liệu làm loại nhầm phương án khả thi).
    """
    total_kg = 0.0
    any_volume_given = False
    for stop in stops_to_transfer:
        vol = stop.get("volume_kg")
        if vol is None:
            continue
        any_volume_given = True
        cargo_type = stop.get("cargo_type", "normal")
        effective = float(vol) * (bulky_multiplier if cargo_type == "bulky" else 1.0)
        total_kg += effective

    if not any_volume_given:
        return list(candidate_vehicles)

    def _payload(v):
        return float(v["max_payload_kg"]) if isinstance(v, dict) else float(v.max_payload_kg)

    return [v for v in candidate_vehicles if _payload(v) >= total_kg]
