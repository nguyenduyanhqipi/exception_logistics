"""BUILD_PLAN.md bước 7.5 — chạy END-TO-END THUẦN BACKEND (không UI) cả 6
kịch bản demo mục 15 qua ĐÚNG pipeline mục 11:
rule_engine -> impact_analyzer -> (geocoder trong option_generator) ->
option_generator (LLM thật) -> ranker, chạy qua `job_processor` thật (không
gọi thẳng option_generator như các script Giai đoạn 6) để verify đúng thứ tự
nối trong `_process_job`.
"""
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from models import BackgroundJob, Exception_, ExceptionGroup, ImpactAnalysis, Option, Schedule, User, Vehicle
from core.impact_analyzer import analyze_impact
from core.rule_engine import calculate_severity
from worker.job_processor import process_pending_jobs

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

for vid, name, phone, payload, cost in [
    ("B03", "Lê Văn Cường", "0912000003", 1000, 7000),
    ("B04", "Phạm Thị Dung", "0912000004", 1000, 7000),
]:
    if db.get(Vehicle, vid) is None:
        db.add(Vehicle(vehicle_id=vid, company_id=company_id, driver_name=name, driver_phone=phone, max_payload_kg=payload, cost_per_km=cost))
db.commit()

SINGLE_SCENARIOS = [
    dict(
        name="KB1 late_departure (serious)", vehicle_id="B01", sub_type="late_departure", exception_group="delay",
        stops=[
            {"stop_id": "s1", "stop_order": 1, "stop_type": "giao_hang", "address": "144 Xuan Thuy, Cau Giay", "area": "Cau Giay", "order_id": "DH-101", "eta": "07:30", "sla_deadline": "09:00", "priority_tier": "thuong"},
            {"stop_id": "s2", "stop_order": 2, "stop_type": "giao_hang", "address": "72 Ho Tung Mau, Nam Tu Liem", "area": "Nam Tu Liem", "order_id": "DH-102", "eta": "08:10", "sla_deadline": "09:30", "priority_tier": "thuong"},
            {"stop_id": "s3", "stop_order": 3, "stop_type": "giao_hang", "address": "15 Au Co, Tay Ho", "area": "Tay Ho", "order_id": "DH-103", "eta": "08:50", "sla_deadline": "10:00", "priority_tier": "vip"},
        ],
        area="Cau Giay", now_hm=(7, 45), from_stop_order=1, delay_minutes=45,
    ),
    dict(
        name="KB2 road_closed (critical)", vehicle_id="B03", sub_type="road_closed", exception_group="road_block",
        stops=[
            {"stop_id": "s1", "stop_order": 1, "stop_type": "giao_hang", "address": "200 Minh Khai, Hai Ba Trung", "area": "Hai Ba Trung", "order_id": "DH-201", "eta": "14:30", "sla_deadline": "15:00", "priority_tier": "thuong"},
            {"stop_id": "s2", "stop_order": 2, "stop_type": "giao_hang", "address": "45 Tam Trinh, Hoang Mai", "area": "Hoang Mai", "order_id": "DH-202", "eta": "15:10", "sla_deadline": "16:00", "priority_tier": "thuong"},
        ],
        area="Hai Ba Trung", now_hm=(14, 35), from_stop_order=1, delay_minutes=0,
    ),
    dict(
        name="KB3 customer_absent (warning)", vehicle_id="B02", sub_type="customer_absent", exception_group="customer_reject",
        stops=[
            {"stop_id": "s2", "stop_order": 2, "stop_type": "giao_hang", "address": "25 Nguyen Trai, Thanh Xuan", "area": "Thanh Xuan", "order_id": "DH-301", "eta": "09:40", "sla_deadline": "12:00", "priority_tier": "thuong"},
            {"stop_id": "s3", "stop_order": 3, "stop_type": "giao_hang", "address": "50 Le Trong Tan, Thanh Xuan", "area": "Thanh Xuan", "order_id": "DH-302", "eta": "10:20", "sla_deadline": "13:00", "priority_tier": "thuong"},
        ],
        area="Thanh Xuan", now_hm=(9, 45), from_stop_order=2, delay_minutes=0,
    ),
    dict(
        name="KB4 cancel_order (serious)", vehicle_id="B04", sub_type="cancel_order", exception_group="customer_change",
        stops=[
            {"stop_id": "s1", "stop_order": 1, "stop_type": "giao_hang", "address": "10 Hang Bai, Hoan Kiem", "area": "Hoan Kiem", "order_id": "DH-401", "eta": "13:50", "sla_deadline": "15:30", "priority_tier": "hop_dong_phat", "sla_penalty": 600000},
        ],
        area="Hoan Kiem", now_hm=(13, 55), from_stop_order=1, delay_minutes=0,
    ),
    dict(
        name="KB5 major_breakdown (serious)", vehicle_id="C02", sub_type="major_breakdown", exception_group="vehicle_issue",
        stops=[
            {"stop_id": "s1", "stop_order": 1, "stop_type": "giao_hang", "address": "30 Ngo Gia Tu, Long Bien", "area": "Long Bien", "order_id": "DH-501", "eta": "10:15", "sla_deadline": "11:00", "priority_tier": "thuong", "volume_kg": 55},
            {"stop_id": "s2", "stop_order": 2, "stop_type": "giao_hang", "address": "12 Nguyen Son, Long Bien", "area": "Long Bien", "order_id": "DH-502", "eta": "10:45", "sla_deadline": "12:30", "priority_tier": "thuong", "volume_kg": 20},
        ],
        area="Long Bien", now_hm=(9, 50), from_stop_order=1, delay_minutes=0,
    ),
]

created_exceptions = []  # (exception_id, schedule_id, expected_severity_label)
created_schedules = []
created_group_id = None
bonus_exc_ids = []
bonus_sched_ids = []

# ---- 5 kịch bản độc lập ----
for sc in SINGLE_SCENARIOS:
    schedule = Schedule(company_id=company_id, vehicle_id=sc["vehicle_id"], shift_date=date.today(), stops=sc["stops"])
    db.add(schedule)
    db.flush()
    created_schedules.append(schedule.schedule_id)

    now = datetime.combine(schedule.shift_date, datetime.min.time().replace(hour=sc["now_hm"][0], minute=sc["now_hm"][1]))
    impact = analyze_impact(sc["stops"], delay_minutes=sc["delay_minutes"], from_stop_order=sc["from_stop_order"], shift_date=schedule.shift_date, now=now)
    severity = calculate_severity(sc["sub_type"], {"departure_delay_min": sc["delay_minutes"], **impact})

    exc = Exception_(
        company_id=company_id, schedule_id=schedule.schedule_id,
        exception_group=sc["exception_group"], sub_type=sc["sub_type"], severity=severity,
        vehicle_id=sc["vehicle_id"], area=sc["area"], description=sc["name"],
        reported_by=user.user_id, status="analyzing",
    )
    db.add(exc)
    db.flush()
    db.add(ImpactAnalysis(exception_id=exc.exception_id, affected_stops=impact["affected_stops"]))
    db.add(BackgroundJob(company_id=company_id, exception_id=exc.exception_id, job_type="analyze_exception"))
    db.commit()
    created_exceptions.append((exc.exception_id, sc["name"], severity))

# ---- Kịch bản bonus: combined mode (B01 minor_breakdown + C02 major_breakdown) ----
stops_a = [
    {"stop_id": "a1", "stop_order": 1, "stop_type": "giao_hang", "address": "40 Cau Giay", "area": "Cau Giay", "order_id": "DH-601", "eta": "10:30", "sla_deadline": "11:00", "priority_tier": "thuong"},
    {"stop_id": "a2", "stop_order": 2, "stop_type": "giao_hang", "address": "88 Tran Dang Ninh, Cau Giay", "area": "Cau Giay", "order_id": "DH-602", "eta": "11:00", "sla_deadline": "11:45", "priority_tier": "thuong"},
]
stops_b = [
    {"stop_id": "b1", "stop_order": 1, "stop_type": "giao_hang", "address": "15 Tran Huu Duc, Nam Tu Liem", "area": "Nam Tu Liem", "order_id": "DH-603", "eta": "10:30", "sla_deadline": "11:15", "priority_tier": "vip"},
]
sched_a = Schedule(company_id=company_id, vehicle_id="B01", shift_date=date.today(), trip_sequence=2, stops=stops_a)
sched_b = Schedule(company_id=company_id, vehicle_id="C02", shift_date=date.today(), trip_sequence=2, stops=stops_b)
db.add_all([sched_a, sched_b])
db.flush()
bonus_sched_ids = [sched_a.schedule_id, sched_b.schedule_id]

exc_a = Exception_(company_id=company_id, schedule_id=sched_a.schedule_id, exception_group="vehicle_issue", sub_type="minor_breakdown", severity="serious", vehicle_id="B01", area="Cau Giay", description="KB bonus A - minor_breakdown", reported_by=user.user_id, status="analyzing")
exc_b = Exception_(company_id=company_id, schedule_id=sched_b.schedule_id, exception_group="vehicle_issue", sub_type="major_breakdown", severity="serious", vehicle_id="C02", area="Nam Tu Liem", description="KB bonus B - major_breakdown", reported_by=user.user_id, status="analyzing")
db.add_all([exc_a, exc_b])
db.flush()
bonus_exc_ids = [exc_a.exception_id, exc_b.exception_id]

db.add(ImpactAnalysis(exception_id=exc_a.exception_id, affected_stops=[{"stop_id": s["stop_id"], "order_id": s["order_id"], "delay_minutes": 0, "sla_breach": False, "priority_tier": s["priority_tier"]} for s in stops_a]))
db.add(ImpactAnalysis(exception_id=exc_b.exception_id, affected_stops=[{"stop_id": s["stop_id"], "order_id": s["order_id"], "delay_minutes": 0, "sla_breach": False, "priority_tier": s["priority_tier"]} for s in stops_b]))

group = ExceptionGroup(company_id=company_id, exception_ids=[exc_a.exception_id, exc_b.exception_id], mode="combined")
db.add(group)
db.flush()
created_group_id = group.group_id
exc_a.group_id = group.group_id
exc_b.group_id = group.group_id
db.add(BackgroundJob(company_id=company_id, exception_id=exc_a.exception_id, job_type="analyze_group"))
db.commit()

try:
    print("Chạy process_pending_jobs() cho toàn bộ 6 kịch bản...")
    n = process_pending_jobs(db)
    print(f"-> Đã xử lý {n} job.\n")
    check("Xử lý đủ 6 job (5 đơn lẻ + 1 group)", n == 6)

    for exc_id, name, expected_severity in created_exceptions:
        db.refresh(db.get(Exception_, exc_id))
        exc = db.get(Exception_, exc_id)
        job = db.query(BackgroundJob).filter(BackgroundJob.exception_id == exc_id).first()
        options = db.query(Option).filter(Option.exception_id == exc_id).order_by(Option.rank).all()
        print(f"{name}: severity={exc.severity} (kỳ vọng {expected_severity}), job.status={job.status}, job.error={job.error}, số option={len(options)}")
        check(f"  [{name}] job.status='done'", job.status == "done")
        check(f"  [{name}] exception.status='awaiting_decision'", exc.status == "awaiting_decision")
        check(f"  [{name}] có ít nhất 1 option", len(options) >= 1)
        check(f"  [{name}] mọi option đều có rank + score (đã qua ranker)", all(o.rank is not None and o.score is not None for o in options))
        if len(options) > 1:
            scores = [float(o.score) for o in options]
            check(f"  [{name}] score giảm dần theo rank (rank 1 tốt nhất)", scores == sorted(scores, reverse=True))

    group_options = db.query(Option).filter(Option.group_id == created_group_id).order_by(Option.rank).all()
    exc_a_db = db.get(Exception_, bonus_exc_ids[0])
    exc_b_db = db.get(Exception_, bonus_exc_ids[1])
    print(f"\nKB bonus (combined): exc_a.status={exc_a_db.status}, exc_b.status={exc_b_db.status}, số option nhóm={len(group_options)}")
    check("[Bonus] có ít nhất 1 option cho group", len(group_options) >= 1)
    check("[Bonus] mọi option nhóm đều có rank + score", all(o.rank is not None and o.score is not None for o in group_options))
    check("[Bonus] cả 2 exception thành viên đều awaiting_decision", exc_a_db.status == "awaiting_decision" and exc_b_db.status == "awaiting_decision")

finally:
    print("\nDọn dữ liệu test...")
    all_exc_ids = [e[0] for e in created_exceptions] + bonus_exc_ids
    all_sched_ids = created_schedules + bonus_sched_ids
    db.query(Option).filter((Option.exception_id.in_(all_exc_ids)) | (Option.group_id == created_group_id)).delete(synchronize_session=False)
    db.query(BackgroundJob).filter(BackgroundJob.exception_id.in_(all_exc_ids)).delete(synchronize_session=False)
    db.query(ImpactAnalysis).filter(ImpactAnalysis.exception_id.in_(all_exc_ids)).delete(synchronize_session=False)
    db.query(Exception_).filter(Exception_.exception_id.in_(all_exc_ids)).delete(synchronize_session=False)
    db.query(ExceptionGroup).filter(ExceptionGroup.group_id == created_group_id).delete(synchronize_session=False)
    db.query(Schedule).filter(Schedule.schedule_id.in_(all_sched_ids)).delete(synchronize_session=False)
    db.commit()
    db.close()
    print("Xong.")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
