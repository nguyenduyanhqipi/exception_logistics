"""Chạy + in output Gemini THẬT cho 4 kịch bản còn lại của bước 6.8 (mục 15):
Kịch bản 2 (road_closed, critical), 3 (customer_absent, warning), 4
(cancel_order, serious), 5 (major_breakdown, serious). Đọc bằng mắt sau khi
chạy — không assert tự động về giọng văn (không thể tự động hoá phần đó).
"""
import json
import sys
from datetime import date

sys.path.insert(0, ".")

from database import SessionLocal
from models import Exception_, ImpactAnalysis, Schedule, User, Vehicle
from core.impact_analyzer import analyze_impact
from core.option_generator import build_context, generate_options_for_exception
from core.rule_engine import calculate_severity

db = SessionLocal()
company_id = "00000000-0000-0000-0000-000000000001"
user = db.query(User).filter(User.company_id == company_id).first()

for vid, name, phone, payload, cost in [
    ("B03", "Lê Văn Cường", "0912000003", 1000, 7000),
    ("B04", "Phạm Thị Dung", "0912000004", 1000, 7000),
]:
    if db.get(Vehicle, vid) is None:
        db.add(Vehicle(vehicle_id=vid, company_id=company_id, driver_name=name, driver_phone=phone, max_payload_kg=payload, cost_per_km=cost))
db.commit()

SCENARIOS = [
    dict(
        name="Kịch bản 2 — road_block/road_closed (kỳ vọng: critical)",
        vehicle_id="B03", shift_label="ca_chieu",
        stops=[
            {"stop_id": "s1", "stop_order": 1, "stop_type": "giao_hang", "address": "200 Minh Khai, Hai Ba Trung", "area": "Hai Ba Trung", "order_id": "DH-201", "eta": "14:30", "sla_deadline": "15:00", "priority_tier": "thuong"},
            {"stop_id": "s2", "stop_order": 2, "stop_type": "giao_hang", "address": "45 Tam Trinh, Hoang Mai", "area": "Hoang Mai", "order_id": "DH-202", "eta": "15:10", "sla_deadline": "16:00", "priority_tier": "thuong"},
        ],
        exception_group="road_block", sub_type="road_closed",
        description="Cầu Vĩnh Tuy / đường Minh Khai đoạn qua Hai Bà Trưng bị chặn hoàn toàn do tai nạn giao thông nghiêm trọng, xe không thể qua.",
        area="Hai Ba Trung",
        now_hm=(14, 35), from_stop_order=1, delay_minutes=0,
    ),
    dict(
        name="Kịch bản 3 — customer_reject/customer_absent (kỳ vọng: warning)",
        vehicle_id="B02", shift_label="ca_sang",
        stops=[
            {"stop_id": "s2", "stop_order": 2, "stop_type": "giao_hang", "address": "25 Nguyen Trai, Thanh Xuan", "area": "Thanh Xuan", "order_id": "DH-301", "eta": "09:40", "sla_deadline": "12:00", "priority_tier": "thuong", "notes": "Khong co ai o nha, lan giao dau tien"},
            {"stop_id": "s3", "stop_order": 3, "stop_type": "giao_hang", "address": "50 Le Trong Tan, Thanh Xuan", "area": "Thanh Xuan", "order_id": "DH-302", "eta": "10:20", "sla_deadline": "13:00", "priority_tier": "thuong"},
        ],
        exception_group="customer_reject", sub_type="customer_absent",
        description="Không có ai ở nhà nhận hàng, đây là lần giao đầu tiên.",
        area="Thanh Xuan",
        now_hm=(9, 45), from_stop_order=2, delay_minutes=0,
    ),
    dict(
        name="Kịch bản 4 — customer_change/cancel_order (kỳ vọng: serious)",
        vehicle_id="B04", shift_label="ca_chieu",
        stops=[
            {"stop_id": "s1", "stop_order": 1, "stop_type": "giao_hang", "address": "10 Hang Bai, Hoan Kiem", "area": "Hoan Kiem", "order_id": "DH-401", "eta": "13:50", "sla_deadline": "15:30", "priority_tier": "hop_dong_phat", "sla_penalty": 600000, "volume_kg": 8, "cargo_type": "normal"},
        ],
        exception_group="customer_change", sub_type="cancel_order",
        description="Khách gọi báo hủy đơn khi xe còn cách điểm giao khoảng 15 phút. Giá trị hàng 2.500.000đ (hàng thời trang, khách có hợp đồng phân phối với công ty).",
        area="Hoan Kiem",
        now_hm=(13, 55), from_stop_order=1, delay_minutes=0,
    ),
    dict(
        name="Kịch bản 5 — vehicle_issue/major_breakdown (kỳ vọng: serious)",
        vehicle_id="C02", shift_label="ca_sang",
        stops=[
            {"stop_id": "s1", "stop_order": 1, "stop_type": "giao_hang", "address": "30 Ngo Gia Tu, Long Bien", "area": "Long Bien", "order_id": "DH-501", "eta": "10:15", "sla_deadline": "11:00", "priority_tier": "thuong", "volume_kg": 55, "cargo_type": "normal"},
            {"stop_id": "s2", "stop_order": 2, "stop_type": "giao_hang", "address": "12 Nguyen Son, Long Bien", "area": "Long Bien", "order_id": "DH-502", "eta": "10:45", "sla_deadline": "12:30", "priority_tier": "thuong", "volume_kg": 20, "cargo_type": "normal"},
        ],
        exception_group="vehicle_issue", sub_type="major_breakdown",
        description="Xe chết máy hoàn toàn trên đường Nguyễn Văn Cừ, Long Biên, không thể chạy tiếp. Trên xe còn hàng của 2 điểm giao.",
        area="Long Bien",
        now_hm=(9, 50), from_stop_order=1, delay_minutes=0,
    ),
]

cleanup_ids = []

for sc in SCENARIOS:
    print("\n" + "=" * 90)
    print(sc["name"])
    print("=" * 90)

    schedule = Schedule(company_id=company_id, vehicle_id=sc["vehicle_id"], shift_date=date.today(), shift_label=sc["shift_label"], stops=sc["stops"])
    db.add(schedule)
    db.flush()

    from datetime import datetime
    now = datetime.combine(schedule.shift_date, datetime.min.time().replace(hour=sc["now_hm"][0], minute=sc["now_hm"][1]))
    impact = analyze_impact(sc["stops"], delay_minutes=sc["delay_minutes"], from_stop_order=sc["from_stop_order"], shift_date=schedule.shift_date, now=now)
    severity = calculate_severity(sc["sub_type"], {"departure_delay_min": sc["delay_minutes"], **impact})
    print(f"-> severity tính được: {severity}")
    print(f"-> impact: time_to_deadline_min={impact.get('time_to_deadline_min')}, downstream_stops_affected={impact.get('downstream_stops_affected')}, has_priority_order={impact.get('has_priority_order')}")

    exc = Exception_(
        company_id=company_id, schedule_id=schedule.schedule_id,
        exception_group=sc["exception_group"], sub_type=sc["sub_type"], severity=severity,
        vehicle_id=sc["vehicle_id"], area=sc["area"], description=sc["description"],
        reported_by=user.user_id, status="analyzing",
    )
    db.add(exc)
    db.flush()
    db.add(ImpactAnalysis(exception_id=exc.exception_id, affected_stops=impact["affected_stops"]))
    db.commit()
    cleanup_ids.append((exc.exception_id, schedule.schedule_id))

    options, usage = generate_options_for_exception(db, exc)
    print(f"-> LLM usage: {usage}")
    if options:
        for i, opt in enumerate(options):
            print(f"\n--- Option {i+1} ---")
            print(json.dumps(opt, indent=2, ensure_ascii=False))
    else:
        print("!!! LLM không sinh được phương án hợp lệ:", usage.get("error"))

print("\n\nDọn dữ liệu test...")
for exc_id, sched_id in cleanup_ids:
    db.query(ImpactAnalysis).filter(ImpactAnalysis.exception_id == exc_id).delete(synchronize_session=False)
    db.query(Exception_).filter(Exception_.exception_id == exc_id).delete(synchronize_session=False)
    db.query(Schedule).filter(Schedule.schedule_id == sched_id).delete(synchronize_session=False)
db.commit()
db.close()
print("Xong.")
