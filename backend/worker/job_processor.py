"""job_processor.py — worker xử lý background_jobs (mục 11).

rule_engine/impact_analyzer chạy ĐỒNG BỘ ngay lúc tạo exception
(api/exceptions.py) — xem ghi chú BUILD_PLAN.md bước 5.1. Worker này lo phần
I/O chậm: option_generator.py (LLM, Giai đoạn 6) đã nối thật; geocoder +
ranker thật vào ở Giai đoạn 7 (hiện `score`/`rank` để trống, dispatcher vẫn
thấy đủ mô tả/chi phí/thời gian ước tính từ LLM để tự so sánh).
"""
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from models import BackgroundJob, Exception_, ExceptionGroup, Option
from core.option_generator import QuotaExceededError, generate_options_for_exception, generate_options_for_group

SEVERITY_PRIORITY = {"critical": 0, "serious": 1, "warning": 2, None: 3}

MANUAL_FALLBACK_DESCRIPTION = (
    "[AI không khả dụng] Vui lòng đánh giá tình huống và nhập phương án xử lý thủ công."
)


def _job_priority(db: Session, job: BackgroundJob):
    """Ưu tiên critical > serious > warning; cùng severity thì theo
    reported_at của exception liên quan (mục 5.3, 10)."""
    exc = db.get(Exception_, job.exception_id) if job.exception_id else None
    severity = exc.severity if exc else None
    reported_at = exc.reported_at if exc else job.created_at
    return (SEVERITY_PRIORITY.get(severity, 3), reported_at)


def _persist_manual_fallback_option(db: Session, exception_id=None, group_id=None) -> None:
    """LLM fallback (mục 8): Gemini lỗi/hết hạn mức -> vẫn tạo 1 "phương án"
    placeholder để dispatcher có option_id để chọn/ghi đè qua
    POST /api/exceptions/{id}/manual-option (mục 8: "cho phép nhập phương án
    thủ công"), thay vì màn hình trắng không có gì để xác nhận."""
    db.add(
        Option(
            exception_id=exception_id,
            group_id=group_id,
            description=MANUAL_FALLBACK_DESCRIPTION,
            rank=1,
        )
    )


def _persist_llm_options(db: Session, raw_options: list[dict], exception_id=None, group_id=None) -> None:
    for raw in raw_options:
        db.add(
            Option(
                exception_id=exception_id,
                group_id=group_id,
                description=raw.get("description"),
                cost_estimate=raw.get("cost_estimate"),
                time_estimate_minutes=raw.get("time_estimate_minutes"),
                sla_risk_remaining=raw.get("sla_risk_remaining"),
                llm_explanation=raw.get("explanation"),
                # rationale không có cột riêng trong bảng options (mục 4) -> gộp
                # vào llm_explanation để không mất thông tin LLM đã sinh ra.
            )
        )


def _process_job(db: Session, job: BackgroundJob):
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    db.commit()

    llm_error = None
    try:
        if job.job_type == "analyze_exception":
            exc = db.get(Exception_, job.exception_id)
            try:
                options, usage = generate_options_for_exception(db, exc)
            except QuotaExceededError as e:
                options, usage, llm_error = None, {}, str(e)
            if options:
                _persist_llm_options(db, options, exception_id=exc.exception_id)
            else:
                llm_error = llm_error or usage.get("error") or "LLM không sinh được phương án hợp lệ"
                _persist_manual_fallback_option(db, exception_id=exc.exception_id)

        elif job.job_type == "analyze_group":
            exc = db.get(Exception_, job.exception_id)
            group = db.get(ExceptionGroup, exc.group_id)
            try:
                options, usage = generate_options_for_group(db, group)
            except QuotaExceededError as e:
                options, usage, llm_error = None, {}, str(e)
            if options:
                _persist_llm_options(db, options, group_id=group.group_id)
            else:
                llm_error = llm_error or usage.get("error") or "LLM không sinh được phương án hợp lệ"
                _persist_manual_fallback_option(db, group_id=group.group_id)
        else:
            raise ValueError(f"job_type không hợp lệ: {job.job_type}")

        exc = db.get(Exception_, job.exception_id) if job.exception_id else None
        if exc is not None:
            exc.status = "awaiting_decision"

        # mục 8: LLM lỗi/hết hạn mức KHÔNG phải "job failed" theo nghĩa crash —
        # dispatcher vẫn có phương án thủ công để xác nhận, nên job vẫn 'done',
        # chỉ ghi rõ lý do fallback vào error để hiển thị minh bạch cho dispatcher.
        job.status = "done"
        job.completed_at = datetime.now(timezone.utc)
        job.error = llm_error
        job.result = {"llm_fallback": llm_error is not None}
        db.commit()
    except Exception as e:  # noqa: BLE001 - worker phải bắt mọi lỗi để không crash tiến trình
        db.rollback()
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()


def process_pending_jobs(db: Session) -> int:
    """Xử lý HẾT job đang pending hiện có, theo đúng thứ tự ưu tiên severity
    (mục 5.3, 10). Trả về số job đã xử lý."""
    jobs = list(db.execute(select(BackgroundJob).where(BackgroundJob.status == "pending")).scalars().all())
    jobs.sort(key=lambda j: _job_priority(db, j))
    for job in jobs:
        _process_job(db, job)
    return len(jobs)


def cleanup_expired_locks_job() -> int:
    from core.resource_lock import cleanup_expired_locks

    db = SessionLocal()
    try:
        return cleanup_expired_locks(db)
    finally:
        db.close()


def run_forever(poll_interval_seconds: int = 2, lock_cleanup_every_n_polls: int = 150):
    """Entry point khi chạy `python worker/job_processor.py` (mục 16: worker
    chạy riêng, không chung tiến trình với API). `lock_cleanup_every_n_polls`
    mặc định 150 * 2s = 300s = 5 phút, đúng tần suất dọn lock mục 5.3."""
    poll_count = 0
    while True:
        db = SessionLocal()
        try:
            process_pending_jobs(db)
        finally:
            db.close()

        poll_count += 1
        if poll_count % lock_cleanup_every_n_polls == 0:
            cleanup_expired_locks_job()

        time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    run_forever()
