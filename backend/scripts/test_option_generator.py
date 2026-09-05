"""Test option_generator.py (BUILD_PLAN.md bước 6.3, 6.4) trên Kịch bản 1 mục 15.
Tạo exception test thật trong DB, build CONTEXT, gọi Gemini thật, in kết quả
để đọc bằng mắt (bước 6.8 sẽ đọc kỹ hơn cho cả 6 kịch bản).
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from models import Exception_, ImpactAnalysis, Schedule, User, Vehicle
from core.impact_analyzer import analyze_impact
from core.option_generator import build_context, generate_options_for_exception
from core.rule_engine import calculate_severity

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


db = SessionLocal()
company_id = "00000000-0000-0000-0000-000000000001"
user = db.query(User).filter(User.company_id == company_id).first()
vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == "B01").first()

stops = [
    {"stop_id": "s1", "stop_order": 1, "stop_type": "giao_hang", "address": "144 Xuan Thuy, Cau Giay", "area": "Cau Giay", "order_id": "DH-101", "eta": "07:30", "sla_deadline": "09:00", "priority_tier": "thuong", "volume_kg": 25, "cargo_type": "normal"},
    {"stop_id": "s2", "stop_order": 2, "stop_type": "giao_hang", "address": "72 Ho Tung Mau, Nam Tu Liem", "area": "Nam Tu Liem", "order_id": "DH-102", "eta": "08:10", "sla_deadline": "09:30", "priority_tier": "thuong", "volume_kg": 40, "cargo_type": "normal"},
    {"stop_id": "s3", "stop_order": 3, "stop_type": "giao_hang", "address": "15 Au Co, Tay Ho", "area": "Tay Ho", "order_id": "DH-103", "eta": "08:50", "sla_deadline": "10:00", "priority_tier": "vip", "volume_kg": 18, "cargo_type": "bulky"},
]

schedule = Schedule(company_id=company_id, vehicle_id="B01", shift_date=date.today(), depot_arrival_time="06:30", depot_loading_duration_min=30, planned_departure_time="07:00", stops=stops)
db.add(schedule)
db.flush()

impact = analyze_impact(stops, delay_minutes=45, from_stop_order=1, shift_date=schedule.shift_date, now=datetime.combine(schedule.shift_date, datetime.min.time().replace(hour=7, minute=45)))
severity = calculate_severity("late_departure", {"departure_delay_min": 45, **impact})

exc = Exception_(
    company_id=company_id,
    schedule_id=schedule.schedule_id,
    exception_group="delay",
    sub_type="late_departure",
    severity=severity,
    vehicle_id="B01",
    area="Cau Giay",
    description="Tài xế đến kho trễ 50 phút.",
    reported_by=user.user_id,
    status="analyzing",
)
db.add(exc)
db.flush()
db.add(ImpactAnalysis(exception_id=exc.exception_id, affected_stops=impact["affected_stops"]))
db.commit()

try:
    # ---- 6.3: build_context ----
    context = build_context(db, exc)
    print("=== CONTEXT ===")
    print(json.dumps(context, indent=2, ensure_ascii=False))
    check("context.exception.sub_type = late_departure", context["exception"]["sub_type"] == "late_departure")
    check("context.exception.severity đúng", context["exception"]["severity"] == severity)
    check("context.vehicle.driver_name có giá trị (B01)", context["vehicle"]["driver_name"] == "Nguyễn Văn An")
    check("context.vehicle.max_payload_kg có giá trị", context["vehicle"]["max_payload_kg"] is not None)
    check("context.trip.stops đủ 3 điểm", len(context["trip"]["stops"]) == 3)
    check("context.impact_analysis.affected_stops đủ 3", len(context["impact_analysis"]["affected_stops"]) == 3)
    check("context.ranking_weights có giá trị", context["ranking_weights"] is not None)

    # ---- 6.4: gọi Gemini thật ----
    print("\n=== Gọi Gemini thật ===")
    options, usage = generate_options_for_exception(db, exc)
    print("usage:", usage)
    check("LLM trả về options thành công", usage["success"] is True)
    check("options là list 2-3 phần tử", options is not None and 2 <= len(options) <= 3)
    if options:
        for i, opt in enumerate(options):
            print(f"\n--- Option {i+1} ---")
            print(json.dumps(opt, indent=2, ensure_ascii=False))
        required_fields = {"description", "rationale", "cost_estimate", "time_estimate_minutes", "sla_risk_remaining", "explanation"}
        check("mỗi option có đủ 6 field JSON schema", all(required_fields <= set(o.keys()) for o in options))

finally:
    db.query(ImpactAnalysis).filter(ImpactAnalysis.exception_id == exc.exception_id).delete(synchronize_session=False)
    db.query(Exception_).filter(Exception_.exception_id == exc.exception_id).delete(synchronize_session=False)
    db.query(Schedule).filter(Schedule.schedule_id == schedule.schedule_id).delete(synchronize_session=False)
    db.commit()
    db.close()
    print("\nĐã dọn dữ liệu test.")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
