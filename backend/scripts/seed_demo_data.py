"""Seed dữ liệu demo đầy đủ (BUILD_PLAN.md bước 10.1): 10 xe (mục 15) + 6
schedule cho 6 kịch bản demo (5 chính + bonus). Idempotent (UPSERT) — chạy
lại nhiều lần an toàn.

QUYẾT ĐỊNH THIẾT KẾ QUAN TRỌNG — LỆCH SO VỚI CHỮ NGHĨA MỤC 15 (có lý do kỹ
thuật bắt buộc, ghi ở BUILD_PLAN.md bước 10.1): mục 15 mô tả các kịch bản với
ngày/giờ CỐ ĐỊNH (01/09/2026, 07:30, 14:35...). Nhưng hệ thống tính severity/
impact bằng GIỜ THỰC (`datetime.now()`, xem `api/exceptions.py`), không có cơ
chế giả lập thời gian nào — phát hiện lúc test UI Giai đoạn 8 (severity ra
`critical` sai khi seed data dùng giờ đã qua so với giờ thực tế). Vì exception
của mỗi kịch bản được NHẬP TRỰC TIẾP qua UI lúc trình bày (không seed sẵn —
chỉ seed `schedules`), script này tính giờ các điểm giao là ĐỘ LỆCH TƯƠNG ĐỐI
so với thời điểm CHẠY SCRIPT (`now`), giữ đúng khoảng cách phút mà mục 15 mô
tả (vd "45 phút trễ", "còn 25 phút đến hạn") — để khi trình bày ngay sau khi
seed, severity/escalation ra đúng kết quả kỳ vọng. Nên CHẠY LẠI SCRIPT NÀY
NGAY TRƯỚC BUỔI TRÌNH BÀY THẬT (không chạy 1 lần rồi để đó nhiều ngày).

Chạy: python scripts/seed_demo_data.py
"""
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from database import SessionLocal
from models import Schedule, Vehicle

COMPANY_ID = "00000000-0000-0000-0000-000000000001"

VEHICLES = [
    ("B01", "Nguyễn Văn An", "0912000001", 1000, 7000),
    ("B02", "Trần Thị Bình", "0912000002", 1000, 7000),
    ("B03", "Lê Văn Cường", "0912000003", 1000, 7000),
    ("B04", "Phạm Thị Dung", "0912000004", 1000, 7000),
    ("B05", "Hoàng Văn Em", "0912000005", 1000, 7000),
    ("C01", "Vũ Thị Phương", "0912000006", 1500, 9500),
    ("C02", "Đặng Văn Giang", "0912000007", 1500, 9500),
    ("C03", "Bùi Thị Hoa", "0912000008", 1500, 9500),
    ("C04", "Đinh Văn Inh", "0912000009", 1500, 9500),
    ("C05", "Ngô Thị Kim", "0912000010", 1500, 9500),
]


def _t(base: datetime, minutes: int) -> str:
    """Giờ (HH:MM) = base + minutes, dùng làm eta/sla_deadline trong stops[]."""
    return (base + timedelta(minutes=minutes)).strftime("%H:%M")


def upsert_vehicles(db):
    for vehicle_id, driver_name, driver_phone, max_payload_kg, cost_per_km in VEHICLES:
        v = db.get(Vehicle, vehicle_id)
        if v is None:
            v = Vehicle(vehicle_id=vehicle_id, company_id=COMPANY_ID)
            db.add(v)
        v.driver_name = driver_name
        v.driver_phone = driver_phone
        v.max_payload_kg = max_payload_kg
        v.cost_per_km = cost_per_km
        v.status = "active"
    db.commit()
    print(f"Upsert {len(VEHICLES)} xe.")


def _compute_planned_departure(arrival: "time | None", loading_min: "int | None") -> "time | None":
    """Y HỆT logic `api/schedules.py::_compute_planned_departure` — tạo
    schedule trực tiếp qua ORM ở đây (không qua API) nên phải tự tính lại,
    KHÔNG được để trống (bug thật gặp lúc test 10.3: thiếu field này làm
    frontend không hỏi câu phụ 'xe có mặt tại kho đúng giờ không' vì điều
    kiện hiển thị dựa vào planned_departure_time có giá trị hay không)."""
    if arrival is None or loading_min is None:
        return None
    dt = datetime.combine(date.today(), arrival)
    return (dt + timedelta(minutes=loading_min)).time()


def _upsert_schedule(db, vehicle_id, shift_date_val, trip_sequence, stops, depot_arrival_time=None, depot_loading_duration_min=None):
    existing = db.execute(
        select(Schedule).where(
            Schedule.vehicle_id == vehicle_id,
            Schedule.shift_date == shift_date_val,
            Schedule.trip_sequence == trip_sequence,
            Schedule.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    planned_departure_time = _compute_planned_departure(depot_arrival_time, depot_loading_duration_min)

    if existing is not None:
        existing.stops = stops
        existing.depot_arrival_time = depot_arrival_time
        existing.depot_loading_duration_min = depot_loading_duration_min
        existing.planned_departure_time = planned_departure_time
        return existing

    schedule = Schedule(
        company_id=COMPANY_ID,
        vehicle_id=vehicle_id,
        shift_date=shift_date_val,
        trip_sequence=trip_sequence,
        depot_arrival_time=depot_arrival_time,
        depot_loading_duration_min=depot_loading_duration_min,
        planned_departure_time=planned_departure_time,
        stops=stops,
    )
    db.add(schedule)
    return schedule


def _stop(order, addr, area, order_id, cust, phone, eta, sla, tier="thuong", volume_kg=None, cargo_type="normal", sla_penalty=None):
    return {
        "stop_id": f"seed-{order_id}",
        "stop_order": order,
        "stop_type": "giao_hang",
        "address": addr,
        "area": area,
        "order_id": order_id,
        "customer_name": cust,
        "customer_phone": phone,
        "eta": eta,
        "sla_deadline": sla,
        "priority_tier": tier,
        "volume_kg": volume_kg,
        "cargo_type": cargo_type,
        "sla_penalty": sla_penalty,
        "notes": None,
    }


def seed_schedules(db):
    now = datetime.now()
    today = date.today()
    n = 0

    # KB1 — B01, delay/late_departure: trễ xuất phát 45' (dispatcher tự nhập
    # lúc demo). Buffer TRƯỚC khi cộng delay phải > 45 để giữ đúng mục 15
    # ("không điểm nào breach SLA") — dùng đúng khoảng cách gốc mục 15 (90'/
    # 80'/70' buffer), KHÔNG được rút ngắn tuỳ tiện (bug thật gặp ở bản đầu:
    # buffer 60'/50'/40' khiến điểm 3 tự breach ngay cả không có time-drift).
    _upsert_schedule(
        db, "B01", today, 1,
        depot_arrival_time=time(6, 30), depot_loading_duration_min=30,
        stops=[
            _stop(1, "144 Xuân Thủy, Cầu Giấy", "Cầu Giấy", "DH-101", "Nguyễn Thị Lan", "0987001101", _t(now, 30), _t(now, 120), "thuong"),
            _stop(2, "72 Hồ Tùng Mậu, Nam Từ Liêm", "Nam Từ Liêm", "DH-102", "Trần Văn Hùng", "0987001102", _t(now, 70), _t(now, 150), "thuong"),
            _stop(3, "15 Âu Cơ, Tây Hồ", "Tây Hồ", "DH-103", "Lê Thị Mai", "0987001103", _t(now, 110), _t(now, 180), "vip"),
        ],
    )
    n += 1

    # KB2 — B03, road_block/road_closed: stop1 deadline chỉ còn 25' (< 30) ->
    # critical dù road_closed nền đã là serious.
    _upsert_schedule(
        db, "B03", today, 1,
        stops=[
            _stop(1, "200 Minh Khai, Hai Bà Trưng", "Hai Bà Trưng", "DH-201", "Phạm Văn Đức", "0987002101", _t(now, -5), _t(now, 25), "thuong"),
            _stop(2, "45 Tam Trinh, Hoàng Mai", "Hoàng Mai", "DH-202", "Ngô Thị Hằng", "0987002102", _t(now, 35), _t(now, 85), "thuong"),
        ],
    )
    n += 1

    # KB3 — B02, customer_reject/customer_absent: buffer rộng (135'), không
    # priority -> giữ warning, đối trọng với KB1/KB2.
    _upsert_schedule(
        db, "B02", today, 1,
        stops=[
            _stop(1, "88 Tây Sơn, Đống Đa", "Đống Đa", "DH-300", "Khách đã giao", "0900000000", _t(now, -30), _t(now, 30), "thuong"),
            _stop(2, "25 Nguyễn Trãi, Thanh Xuân", "Thanh Xuân", "DH-301", "Vũ Văn Long", "0912345678", _t(now, -5), _t(now, 135), "thuong"),
            _stop(3, "50 Lê Trọng Tấn, Thanh Xuân", "Thanh Xuân", "DH-302", "Đỗ Văn Nam", "0987003103", _t(now, 35), _t(now, 175), "thuong"),
        ],
    )
    n += 1

    # KB4 — B04, customer_change/cancel_order: priority_tier=hop_dong_phat,
    # sla_penalty 600k -> has_priority_order=True -> escalate serious.
    _upsert_schedule(
        db, "B04", today, 1,
        stops=[
            _stop(1, "10 Hàng Bài, Hoàn Kiếm", "Hoàn Kiếm", "DH-401", "Đỗ Thị Nga", "0909112233", _t(now, -5), _t(now, 95), "hop_dong_phat", volume_kg=8, sla_penalty=600000),
        ],
    )
    n += 1

    # KB5 — C02, vehicle_issue/major_breakdown: stop1 deadline 70' (30-90) ->
    # sàn serious, trùng đúng nền cố định major_breakdown.
    _upsert_schedule(
        db, "C02", today, 1,
        stops=[
            _stop(1, "30 Ngô Gia Tự, Long Biên", "Long Biên", "DH-501", "Bùi Văn Tùng", "0987005101", _t(now, 25), _t(now, 70), "thuong", volume_kg=55),
            _stop(2, "12 Nguyễn Sơn, Long Biên", "Long Biên", "DH-502", "Trịnh Thị Yến", "0987005102", _t(now, 55), _t(now, 160), "thuong", volume_kg=20),
        ],
    )
    n += 1

    # Bonus — A: B01 minor_breakdown, B: C02 major_breakdown, cùng cần C03 hỗ
    # trợ -> resource_contention -> combined mode. Dùng trip_sequence=2 cho B01
    # (chuyến 1 đã dùng ở KB1) và C02 (chuyến 1 đã dùng ở KB5) để không đụng
    # UNIQUE constraint.
    _upsert_schedule(
        db, "B01", today, 2,
        stops=[
            _stop(1, "40 Cầu Giấy", "Cầu Giấy", "DH-601", "Nguyễn Văn Kiên", "0987006010", _t(now, 20), _t(now, 60), "thuong"),
            _stop(2, "88 Trần Đăng Ninh, Cầu Giấy", "Cầu Giấy", "DH-602", "Hồ Thị Vân", "0987006020", _t(now, 50), _t(now, 105), "thuong"),
        ],
    )
    n += 1
    _upsert_schedule(
        db, "C02", today, 2,
        stops=[
            _stop(1, "15 Trần Hữu Dực, Nam Từ Liêm", "Nam Từ Liêm", "DH-603", "Lương Văn Phúc", "0987006030", _t(now, 20), _t(now, 75), "vip", volume_kg=45),
        ],
    )
    n += 1

    db.commit()
    print(f"Upsert {n} schedule cho 6 kịch bản demo (5 chính + bonus 2 chuyến).")


def main():
    db = SessionLocal()
    try:
        upsert_vehicles(db)
        seed_schedules(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
