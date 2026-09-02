"""Test hàng đợi ưu tiên severity (BUILD_PLAN.md bước 5.5): tạo 3 ngoại lệ
test với severity khác nhau, cố ý tạo THEO THỨ TỰ NGƯỢC (warning trước,
critical sau cùng) để chứng minh worker xử lý theo severity chứ không theo
thứ tự tạo — rồi xác nhận xử lý đúng critical > serious > warning.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from models import BackgroundJob, Exception_, ImpactAnalysis, Option, Schedule, User, Vehicle
from worker.job_processor import process_pending_jobs

passed = 0
failed = 0


def check(label, actual, expected):
    global passed, failed
    ok = actual == expected
    print(f"[{'OK' if ok else 'FAIL'}] {label}: got={actual!r} expected={expected!r}")
    if ok:
        passed += 1
    else:
        failed += 1


db = SessionLocal()
company_id = "00000000-0000-0000-0000-000000000001"
user = db.query(User).filter(User.company_id == company_id).first()
schedule = db.query(Schedule).filter(Schedule.company_id == company_id).first()

if schedule is None:
    print("Không có schedule demo nào trong DB — tạo tạm 1 schedule test.")
    vehicle = db.query(Vehicle).filter(Vehicle.company_id == company_id).first()
    schedule = Schedule(company_id=company_id, vehicle_id=vehicle.vehicle_id, shift_date=datetime.now().date(), shift_label="ca_sang", stops=[])
    db.add(schedule)
    db.commit()
    db.refresh(schedule)

created_exceptions = []
try:
    # Tạo THEO THỨ TỰ: warning -> serious -> critical (ngược thứ tự ưu tiên mong muốn)
    for severity, sub_type, group in [
        ("warning", "customer_absent", "customer_reject"),
        ("serious", "customer_dispute", "customer_reject"),
        ("critical", "accident", "vehicle_issue"),
    ]:
        exc = Exception_(
            company_id=company_id,
            schedule_id=schedule.schedule_id,
            exception_group=group,
            sub_type=sub_type,
            severity=severity,
            reported_by=user.user_id,
            status="analyzing",
        )
        db.add(exc)
        db.flush()
        job = BackgroundJob(company_id=company_id, exception_id=exc.exception_id, job_type="analyze_exception")
        db.add(job)
        created_exceptions.append((severity, exc.exception_id))
    db.commit()

    process_pending_jobs(db)

    order = []
    for severity, exc_id in created_exceptions:
        job = db.query(BackgroundJob).filter(BackgroundJob.exception_id == exc_id).first()
        order.append((job.started_at, severity))
    order.sort()
    processed_severity_order = [s for _, s in order]

    check("Thứ tự xử lý = critical, serious, warning (bất kể thứ tự tạo)", processed_severity_order, ["critical", "serious", "warning"])

    for severity, exc_id in created_exceptions:
        job = db.query(BackgroundJob).filter(BackgroundJob.exception_id == exc_id).first()
        check(f"Job severity={severity} chuyển done", job.status, "done")

finally:
    for _, exc_id in created_exceptions:
        db.query(Option).filter(Option.exception_id == exc_id).delete(synchronize_session=False)
        db.query(ImpactAnalysis).filter(ImpactAnalysis.exception_id == exc_id).delete(synchronize_session=False)
        db.query(BackgroundJob).filter(BackgroundJob.exception_id == exc_id).delete(synchronize_session=False)
        db.query(Exception_).filter(Exception_.exception_id == exc_id).delete(synchronize_session=False)
    db.commit()
    db.close()
    print("Đã dọn dữ liệu test.")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
