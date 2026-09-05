"""Test LLM fallback khi Gemini lỗi/down hoàn toàn (BUILD_PLAN.md bước 6.7).
Mock `generate` luôn thất bại (mô phỏng sai key/network down), chạy qua
`job_processor` thật, xác nhận: không crash, job vẫn 'done' (không phải
'failed' — đây là fallback có kiểm soát, không phải lỗi hệ thống), có ghi rõ
lý do fallback, và dispatcher vẫn có 1 option (placeholder) để xác nhận +
có thể tự thêm phương án thủ công qua API.
"""
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm_adapter import LLMCallResult
from database import SessionLocal
from models import BackgroundJob, Exception_, ImpactAnalysis, Option, Schedule, User
from worker.job_processor import _process_job

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


def fake_generate_always_fails(prompt):
    return LLMCallResult("", 0, 0, 50, success=False, error="API key không hợp lệ hoặc Gemini không phản hồi")


db = SessionLocal()
company_id = "00000000-0000-0000-0000-000000000001"
user = db.query(User).filter(User.company_id == company_id).first()

schedule = Schedule(company_id=company_id, vehicle_id="B01", shift_date=date.today(), stops=[])
db.add(schedule)
db.flush()
exc = Exception_(company_id=company_id, schedule_id=schedule.schedule_id, exception_group="delay", sub_type="late_departure", severity="warning", vehicle_id="B01", reported_by=user.user_id, status="analyzing")
db.add(exc)
db.flush()
db.add(ImpactAnalysis(exception_id=exc.exception_id, affected_stops=[]))
job = BackgroundJob(company_id=company_id, exception_id=exc.exception_id, job_type="analyze_exception")
db.add(job)
db.commit()

try:
    with patch("core.option_generator.generate", side_effect=fake_generate_always_fails):
        # KHÔNG raise exception -> hệ thống không crash
        _process_job(db, job)

    check("Job KHÔNG bị crash (chạy xong, không raise ra ngoài)", True)
    check("Job status='done' (fallback có kiểm soát, không phải 'failed')", job.status == "done")
    check("job.error ghi rõ lý do fallback", job.error is not None and len(job.error) > 0)
    print("job.error:", job.error)

    db.refresh(exc)
    check("Exception status chuyển 'awaiting_decision' (dispatcher vẫn xử lý được)", exc.status == "awaiting_decision")

    options = db.query(Option).filter(Option.exception_id == exc.exception_id).all()
    check("Vẫn có 1 option placeholder để dispatcher xác nhận/ghi đè", len(options) == 1)
    if options:
        print("Placeholder option:", options[0].description)

finally:
    db.query(Option).filter(Option.exception_id == exc.exception_id).delete(synchronize_session=False)
    db.query(BackgroundJob).filter(BackgroundJob.exception_id == exc.exception_id).delete(synchronize_session=False)
    db.query(ImpactAnalysis).filter(ImpactAnalysis.exception_id == exc.exception_id).delete(synchronize_session=False)
    db.query(Exception_).filter(Exception_.exception_id == exc.exception_id).delete(synchronize_session=False)
    db.query(Schedule).filter(Schedule.schedule_id == schedule.schedule_id).delete(synchronize_session=False)
    db.commit()
    db.close()
    print("Đã dọn dữ liệu test.")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
