"""llm_usage.py — log mỗi lần gọi LLM + hard limit số lần gọi/ngày (mục 8, 9).

Ngưỡng giá USD/token là ƯỚC TÍNH THAM KHẢO (giá Gemini API thay đổi theo thời
gian, không có nguồn xác nhận real-time tại thời điểm code) — cost_usd trong
`llm_usage_logs` dùng để theo dõi XU HƯỚNG chi phí tương đối, KHÔNG phải hoá
đơn chính xác. Cập nhật hằng số này khi có bảng giá chính thức mới nhất.
"""
from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import LLMUsageLog

DAILY_CALL_LIMIT_DEFAULT = 100

# Ước tính tham khảo, USD / 1 triệu token (gemini-2.5-flash) — xem docstring trên.
_USD_PER_1M_TOKENS_IN = Decimal("0.30")
_USD_PER_1M_TOKENS_OUT = Decimal("2.50")


def estimate_cost_usd(tokens_in: int, tokens_out: int) -> Decimal:
    return (Decimal(tokens_in) * _USD_PER_1M_TOKENS_IN + Decimal(tokens_out) * _USD_PER_1M_TOKENS_OUT) / Decimal(1_000_000)


def count_calls_today(db: Session, company_id: str) -> int:
    # PHẢI lấy ngày theo UTC (`datetime.now(timezone.utc).date()`), KHÔNG
    # phải `date.today()` — `date.today()` trả về ngày theo múi giờ LOCAL của
    # máy chủ, rồi gán `tzinfo=UTC` sẽ tạo mốc "đầu ngày" LỆCH hẳn so với UTC
    # thật nếu server không chạy múi giờ UTC (vd server UTC+7: mốc "hôm nay"
    # bị đẩy sớm hơn thực tế ~7 tiếng). Hậu quả thật: mọi lệnh gọi LLM trong
    # khoảng lệch đó không được tính vào hạn mức trong ngày — hạn mức 100
    # call/ngày (mục 8) coi như vô tác dụng suốt khoảng thời gian đó. Phát
    # hiện qua `scripts/test_llm_quota.py` tự nhiên fail trên máy dev múi giờ
    # UTC+7 (SEAST), không phải lỗi ở test.
    today_start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    return db.execute(
        select(func.count()).select_from(LLMUsageLog).where(
            LLMUsageLog.company_id == company_id, LLMUsageLog.created_at >= today_start
        )
    ).scalar_one()


def has_quota_remaining(db: Session, company_id: str, limit: int = DAILY_CALL_LIMIT_DEFAULT) -> bool:
    return count_calls_today(db, company_id) < limit


def log_llm_call(
    db: Session,
    company_id: str,
    exception_id: "str | None",
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    prompt_version_id: "str | None",
    success: bool,
) -> LLMUsageLog:
    log = LLMUsageLog(
        company_id=company_id,
        exception_id=exception_id,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=estimate_cost_usd(tokens_in, tokens_out),
        latency_ms=latency_ms,
        prompt_version_id=prompt_version_id,
        success=success,
    )
    db.add(log)
    db.commit()
    return log
