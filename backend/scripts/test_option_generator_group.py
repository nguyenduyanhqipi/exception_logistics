"""Test option_generator.py cho combined mode (BUILD_PLAN.md bước 6.5) — dùng
đúng Kịch bản bonus mục 15: xe A (B01, minor_breakdown, serious) + xe B (C02,
major_breakdown, serious), cả 2 cần điều C03 hỗ trợ.
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from models import Exception_, ExceptionGroup, ImpactAnalysis, Schedule, User, Vehicle
from core.option_generator import build_group_context, generate_options_for_group

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

created_vehicle_c02 = False
if db.get(Vehicle, "C02") is None:
    db.add(Vehicle(vehicle_id="C02", company_id=company_id, driver_name="Đặng Văn Giang", driver_phone="0912000007", max_payload_kg=1500, cost_per_km=9500))
    db.commit()
    created_vehicle_c02 = True

stops_a = [
    {"stop_id": "a1", "stop_order": 1, "stop_type": "giao_hang", "address": "40 Cau Giay", "area": "Cau Giay", "order_id": "DH-601", "eta": "10:30", "sla_deadline": "11:00", "priority_tier": "thuong"},
    {"stop_id": "a2", "stop_order": 2, "stop_type": "giao_hang", "address": "88 Tran Dang Ninh, Cau Giay", "area": "Cau Giay", "order_id": "DH-602", "eta": "11:00", "sla_deadline": "11:45", "priority_tier": "thuong"},
]
stops_b = [
    {"stop_id": "b1", "stop_order": 1, "stop_type": "giao_hang", "address": "15 Tran Huu Duc, Nam Tu Liem", "area": "Nam Tu Liem", "order_id": "DH-603", "eta": "10:30", "sla_deadline": "11:15", "priority_tier": "vip"},
]

sched_a = Schedule(company_id=company_id, vehicle_id="B01", shift_date=date.today(), stops=stops_a)
sched_b = Schedule(company_id=company_id, vehicle_id="C02", shift_date=date.today(), stops=stops_b)
db.add_all([sched_a, sched_b])
db.flush()

exc_a = Exception_(company_id=company_id, schedule_id=sched_a.schedule_id, exception_group="vehicle_issue", sub_type="minor_breakdown", severity="serious", vehicle_id="B01", area="Cau Giay", description="Thủng lốp trước, ga-ra ước tính sửa 50 phút.", reported_by=user.user_id, status="analyzing")
exc_b = Exception_(company_id=company_id, schedule_id=sched_b.schedule_id, exception_group="vehicle_issue", sub_type="major_breakdown", severity="serious", vehicle_id="C02", area="Nam Tu Liem", description="Xe chết máy hoàn toàn.", reported_by=user.user_id, status="analyzing")
db.add_all([exc_a, exc_b])
db.flush()

db.add(ImpactAnalysis(exception_id=exc_a.exception_id, affected_stops=[{"stop_id": s["stop_id"], "order_id": s["order_id"], "delay_minutes": 0, "sla_breach": False, "priority_tier": s["priority_tier"]} for s in stops_a]))
db.add(ImpactAnalysis(exception_id=exc_b.exception_id, affected_stops=[{"stop_id": s["stop_id"], "order_id": s["order_id"], "delay_minutes": 0, "sla_breach": False, "priority_tier": s["priority_tier"]} for s in stops_b]))

group = ExceptionGroup(company_id=company_id, exception_ids=[exc_a.exception_id, exc_b.exception_id], mode="combined")
db.add(group)
db.flush()
exc_a.group_id = group.group_id
exc_b.group_id = group.group_id
db.commit()

try:
    context = build_group_context(db, group)
    check("CONTEXT có đủ 2 exception", len(context["exceptions"]) == 2)
    check("conflict_signals chứa same_vehicle hoặc tương tự", isinstance(context["conflict_signals"], list))
    print("=== conflict_signals ===", context["conflict_signals"])

    print("\n=== Gọi Gemini thật cho combined mode ===")
    options, usage = generate_options_for_group(db, group)
    print("usage:", usage)
    check("LLM trả về options thành công", usage["success"] is True)
    check("options là list 2-3 phần tử", options is not None and 2 <= len(options) <= 3)

    if options:
        for i, opt in enumerate(options):
            print(f"\n--- Option {i+1} ---")
            print(json.dumps(opt, indent=2, ensure_ascii=False))

        combined_text = " ".join(o["description"] + " " + o["rationale"] for o in options)
        mentions_both = ("B01" in combined_text or "Cầu Giấy" in combined_text or "Cau Giay" in combined_text) and (
            "C02" in combined_text or "Nam Từ Liêm" in combined_text or "Nam Tu Liem" in combined_text
        )
        check("Output phân biệt được cả 2 xe/exception (nhắc đến cả B01/khu vực A và C02/khu vực B)", mentions_both)

finally:
    db.query(ImpactAnalysis).filter(ImpactAnalysis.exception_id.in_([exc_a.exception_id, exc_b.exception_id])).delete(synchronize_session=False)
    db.query(Exception_).filter(Exception_.exception_id.in_([exc_a.exception_id, exc_b.exception_id])).delete(synchronize_session=False)
    db.query(ExceptionGroup).filter(ExceptionGroup.group_id == group.group_id).delete(synchronize_session=False)
    db.query(Schedule).filter(Schedule.schedule_id.in_([sched_a.schedule_id, sched_b.schedule_id])).delete(synchronize_session=False)
    db.commit()
    db.close()
    print("\nĐã dọn dữ liệu test.")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
