"""job_processor.py — worker xử lý background_jobs (mục 11).

Pipeline đầy đủ đúng thứ tự mục 11: rule_engine/impact_analyzer chạy ĐỒNG BỘ
ngay lúc tạo exception (api/exceptions.py, xem ghi chú BUILD_PLAN.md bước
5.1) -> geocoder (bên trong option_generator.build_context, mục 14) ->
option_generator (LLM, Giai đoạn 6) -> ranker (Giai đoạn 7) chạy Ở ĐÂY, sau
khi có options, vì ranker cần TOÀN BỘ tập option để normalize so sánh với
nhau (mục 7) — không thể rank từng option riêng lẻ lúc persist.
"""
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from models import BackgroundJob, Company, Exception_, ExceptionGroup, ImpactAnalysis, Option
from core.option_generator import QuotaExceededError, generate_options_for_exception, generate_options_for_group
from core.ranker import rank_options

SEVERITY_PRIORITY = {"critical": 0, "serious": 1, "warning": 2, None: 3}
DEFAULT_RANKING_WEIGHTS = {"cost": 0.4, "time": 0.3, "sla_risk": 0.3}

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


def _persist_manual_fallback_option(db: Session, exception_id=None, group_id=None) -> list[Option]:
    """LLM fallback (mục 8): Gemini lỗi/hết hạn mức -> vẫn tạo 1 "phương án"
    placeholder để dispatcher có option_id để chọn/ghi đè qua
    POST /api/exceptions/{id}/manual-option (mục 8: "cho phép nhập phương án
    thủ công"), thay vì màn hình trắng không có gì để xác nhận."""
    option = Option(
        exception_id=exception_id,
        group_id=group_id,
        description=MANUAL_FALLBACK_DESCRIPTION,
        cost_estimate=0,
        time_estimate_minutes=0,
        sla_risk_remaining=0.5,
    )
    db.add(option)
    return [option]


def _persist_llm_options(db: Session, raw_options: list[dict], exception_id=None, group_id=None) -> list[Option]:
    created = []
    for raw in raw_options:
        option = Option(
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
        db.add(option)
        created.append(option)
    return created


def _company_ranking_weights(db: Session, company_id) -> dict:
    company = db.get(Company, company_id)
    if company is not None and company.ranking_weights:
        return company.ranking_weights
    return DEFAULT_RANKING_WEIGHTS


def _customer_tolerant_of_delay(db: Session, exc: Exception_) -> bool:
    """Mục F: True nếu dispatcher đã ghi nhận khách chấp nhận trễ tối đa N
    phút VÀ mức trễ thật sự ước tính (impact_analysis, tính bằng rule engine
    lúc tạo exception, KHÔNG đổi bởi field này) nằm trong N phút đó. Chỉ đọc
    impact_analysis để SO SÁNH — không ghi/sửa gì vào đó."""
    if exc.customer_accepted_delay_min is None:
        return False
    impact = db.execute(
        select(ImpactAnalysis).where(ImpactAnalysis.exception_id == exc.exception_id)
    ).scalar_one_or_none()
    if impact is None or not impact.affected_stops:
        return False
    max_delay = max((s.get("delay_minutes") or 0) for s in impact.affected_stops)
    return max_delay <= exc.customer_accepted_delay_min


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
                created = _persist_llm_options(db, options, exception_id=exc.exception_id)
            else:
                llm_error = llm_error or usage.get("error") or "LLM không sinh được phương án hợp lệ"
                created = _persist_manual_fallback_option(db, exception_id=exc.exception_id)
            rank_options(
                db, created, _company_ranking_weights(db, exc.company_id),
                customer_tolerant=_customer_tolerant_of_delay(db, exc),
            )

        elif job.job_type == "analyze_group":
            exc = db.get(Exception_, job.exception_id)
            group = db.get(ExceptionGroup, exc.group_id)
            try:
                options, usage = generate_options_for_group(db, group)
            except QuotaExceededError as e:
                options, usage, llm_error = None, {}, str(e)
            if options:
                created = _persist_llm_options(db, options, group_id=group.group_id)
            else:
                llm_error = llm_error or usage.get("error") or "LLM không sinh được phương án hợp lệ"
                created = _persist_manual_fallback_option(db, group_id=group.group_id)
            # Mục F (customer_accepted_delay_min) CHƯA áp dụng ở combined mode
            # — 1 nhóm có thể gồm nhiều exception với mức khách chấp nhận khác
            # nhau (hoặc không có), gộp chúng lại thành 1 quyết định "khoan
            # dung" duy nhất cho cả nhóm cần quy tắc riêng, ngoài phạm vi hiện
            # tại. `customer_tolerant` mặc định False -> weights gốc, đúng
            # hành vi trước khi có mục F.
            rank_options(db, created, _company_ranking_weights(db, group.company_id))
            # 1 quyết định phối hợp cho combined mode (mục 5.3, 10) -> CẢ nhóm
            # thành viên cùng chuyển awaiting_decision, không chỉ exception mà
            # job.exception_id tình cờ trỏ tới.
            for member in db.execute(select(Exception_).where(Exception_.exception_id.in_(group.exception_ids))).scalars():
                member.status = "awaiting_decision"
        else:
            raise ValueError(f"job_type không hợp lệ: {job.job_type}")

        if job.job_type == "analyze_exception":
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
    """Entry point khi chạy `python -m worker.job_processor` (mục 16: worker
    chạy riêng, không chung tiến trình với API — PHẢI chạy dạng module (`-m`),
    không phải `python worker/job_processor.py` trực tiếp, nếu không Python
    chỉ coi `worker/` là thư mục tìm import chứ không phải `backend/` gốc,
    gây `ModuleNotFoundError: No module named 'database'` khi chạy trong
    Docker/container — lỗi thật đã gặp lúc deploy VM, xem BUILD_PLAN.md).
    `lock_cleanup_every_n_polls` mặc định 150 * 2s = 300s = 5 phút, đúng tần
    suất dọn lock mục 5.3."""
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
