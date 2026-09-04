"""api/reports.py — mục 12 "Reports (manager only)".

Không có bước riêng nào ở Giai đoạn 5-9 xây các endpoint này trước bước 9.1
cần chúng — bổ sung ở đây, cùng cách xử lý với khoảng trống decisions/outcomes
đã gặp ở Giai đoạn 8.

LƯU Ý TENANT ISOLATION QUAN TRỌNG: `database.py::_TENANT_MODELS` chỉ tự động
lọc company_id cho Vehicle/User/Schedule/Exception_/ExceptionGroup/Decision.
`Option`/`ImpactAnalysis`/`Outcome` KHÔNG có cột `company_id` (join qua
Exception_/Decision đã lọc sẵn là đủ an toàn). `LLMUsageLog`/`AuditLog` CÓ
company_id nhưng KHÔNG nằm trong danh sách tự lọc — mọi truy vấn trực tiếp 2
bảng này trong file này PHẢI tự thêm `.where(company_id == ...)` bằng tay.
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from middleware.rbac import require_role
from middleware.tenant import get_db
from models import Decision, Exception_, LLMUsageLog, Option, Outcome

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/kpi")
def get_kpi(
    current_user: dict = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    total = db.execute(select(func.count()).select_from(Exception_).where(Exception_.deleted_at.is_(None))).scalar_one()

    by_severity = dict(
        db.execute(
            select(Exception_.severity, func.count())
            .where(Exception_.deleted_at.is_(None))
            .group_by(Exception_.severity)
        ).all()
    )
    by_status = dict(
        db.execute(
            select(Exception_.status, func.count()).where(Exception_.deleted_at.is_(None)).group_by(Exception_.status)
        ).all()
    )
    # "resolved" = ĐÃ CÓ kết quả thực tế (outcome). Từ 2026-09-04, xác nhận
    # phương án chỉ đưa ngoại lệ sang "awaiting_outcome" (xem api/decisions.py)
    # — nên `resolved_rate` bên dưới KHÔNG còn đếm ngoại lệ mới chốt phương án
    # là "đã xử lý xong" nữa. Đây là hành vi ĐÚNG theo định nghĩa mới, không
    # phải hồi quy: chưa nhập kết quả thì chưa có gì nuôi on_time_rate /
    # total_actual_cost.
    resolved = by_status.get("resolved", 0)

    # Tính theo Decision.confirmed_at chứ không theo status -> KHÔNG bị ảnh
    # hưởng bởi việc tách awaiting_outcome; vẫn đúng nghĩa "trung bình bao lâu
    # từ lúc báo ngoại lệ đến lúc chốt được phương án".
    avg_resolution_minutes = db.execute(
        select(func.avg(func.extract("epoch", Decision.confirmed_at - Exception_.reported_at) / 60.0))
        .select_from(Decision)
        .join(Exception_, Exception_.exception_id == Decision.exception_id)
    ).scalar_one()

    # on_time_rate / total_actual_cost / cost-accuracy đều đi từ bảng `outcomes`
    # (không đọc `exceptions.status`) nên định nghĩa status mới không đụng tới.
    # Từ 2026-09-04 `delivered_on_time` là bắt buộc khi tạo outcome
    # (schemas/decision.py) nên `is_not(None)` chỉ còn để bao các outcome ghi
    # từ trước.
    on_time_count = db.execute(
        select(func.count())
        .select_from(Outcome)
        .join(Decision, Decision.decision_id == Outcome.decision_id)
        .where(Outcome.delivered_on_time.is_(True))
    ).scalar_one()
    outcome_total = db.execute(
        select(func.count())
        .select_from(Outcome)
        .join(Decision, Decision.decision_id == Outcome.decision_id)
        .where(Outcome.delivered_on_time.is_not(None))
    ).scalar_one()

    total_estimated_cost = db.execute(
        select(func.coalesce(func.sum(Option.cost_estimate), 0))
        .select_from(Decision)
        .join(Option, Option.option_id == Decision.selected_option_id)
    ).scalar_one()
    total_actual_cost = db.execute(
        select(func.coalesce(func.sum(Outcome.actual_cost), 0))
        .select_from(Outcome)
        .join(Decision, Decision.decision_id == Outcome.decision_id)
    ).scalar_one()

    return {
        "total_exceptions": total,
        "by_severity": {"warning": by_severity.get("warning", 0), "serious": by_severity.get("serious", 0), "critical": by_severity.get("critical", 0)},
        "by_status": {
            "pending": by_status.get("pending", 0),
            "analyzing": by_status.get("analyzing", 0),
            "awaiting_decision": by_status.get("awaiting_decision", 0),
            # PHẢI liệt kê rõ: dict trả về chốt cứng danh sách key, thiếu
            # "awaiting_outcome" thì số ngoại lệ ở trạng thái đó biến mất khỏi
            # báo cáo trong im lặng (tổng các key != total_exceptions).
            "awaiting_outcome": by_status.get("awaiting_outcome", 0),
            "resolved": resolved,
        },
        "resolved_rate": round(resolved / total, 4) if total else None,
        "avg_resolution_minutes": round(float(avg_resolution_minutes), 1) if avg_resolution_minutes is not None else None,
        "on_time_rate": round(on_time_count / outcome_total, 4) if outcome_total else None,
        "total_estimated_cost": float(total_estimated_cost),
        "total_actual_cost": float(total_actual_cost),
    }


@router.get("/trends")
def get_trends(
    days: int = 30,
    current_user: dict = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(func.date(Exception_.reported_at), Exception_.exception_group, func.count())
        .where(Exception_.deleted_at.is_(None), Exception_.reported_at >= since)
        .group_by(func.date(Exception_.reported_at), Exception_.exception_group)
        .order_by(func.date(Exception_.reported_at))
    ).all()

    by_date: dict[str, dict] = {}
    for day, group, count in rows:
        day_key = day.isoformat() if isinstance(day, date) else str(day)
        by_date.setdefault(day_key, {"date": day_key, "total": 0, "by_group": {}})
        by_date[day_key]["by_group"][group] = count
        by_date[day_key]["total"] += count

    return {"days": days, "trend": sorted(by_date.values(), key=lambda r: r["date"])}


@router.get("/cost-accuracy")
def get_cost_accuracy(
    current_user: dict = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Decision.decision_id, Option.cost_estimate, Outcome.actual_cost)
        .select_from(Decision)
        .join(Option, Option.option_id == Decision.selected_option_id)
        .join(Outcome, Outcome.decision_id == Decision.decision_id)
        .where(Option.cost_estimate.is_not(None), Outcome.actual_cost.is_not(None))
    ).all()

    items = []
    diffs_pct = []
    for decision_id, estimated, actual in rows:
        estimated_f, actual_f = float(estimated), float(actual)
        diff = actual_f - estimated_f
        diff_pct = (diff / estimated_f) if estimated_f else None
        if diff_pct is not None:
            diffs_pct.append(diff_pct)
        items.append(
            {
                "decision_id": str(decision_id),
                "estimated_cost": estimated_f,
                "actual_cost": actual_f,
                "diff": diff,
                "diff_pct": round(diff_pct, 4) if diff_pct is not None else None,
            }
        )

    return {
        "items": items,
        "count": len(items),
        "avg_diff_pct": round(sum(diffs_pct) / len(diffs_pct), 4) if diffs_pct else None,
    }


@router.get("/llm-usage")
def get_llm_usage(
    days: int = 30,
    current_user: dict = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    # LLMUsageLog KHÔNG nằm trong _TENANT_MODELS (xem docstring đầu file) —
    # PHẢI tự lọc company_id bằng tay ở đây, không dựa vào auto-filter.
    base_filter = (LLMUsageLog.company_id == current_user["company_id"]) & (LLMUsageLog.created_at >= since)

    rows = db.execute(
        select(
            func.date(LLMUsageLog.created_at),
            func.count(),
            func.coalesce(func.sum(LLMUsageLog.tokens_in), 0),
            func.coalesce(func.sum(LLMUsageLog.tokens_out), 0),
            func.coalesce(func.sum(LLMUsageLog.cost_usd), 0),
            func.sum(func.cast(LLMUsageLog.success, Integer)),
        )
        .where(base_filter)
        .group_by(func.date(LLMUsageLog.created_at))
        .order_by(func.date(LLMUsageLog.created_at))
    ).all()

    by_date = []
    for day, count, tokens_in, tokens_out, cost_usd, success_count in rows:
        day_key = day.isoformat() if isinstance(day, date) else str(day)
        by_date.append(
            {
                "date": day_key,
                "calls": count,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": round(float(cost_usd), 4),
                "success_rate": round((success_count or 0) / count, 4) if count else None,
            }
        )

    today_start = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc)
    calls_today = db.execute(
        select(func.count()).where(LLMUsageLog.company_id == current_user["company_id"], LLMUsageLog.created_at >= today_start)
    ).scalar_one()

    # `success_rate` bên trên đếm theo TỪNG LƯỢT GỌI HTTP, không phải theo mỗi
    # lần phân tích: 1 lần phân tích thất bại sinh tới MAX_LLM_RETRIES (=3)
    # dòng lỗi, còn 1 lần thành công ngay chỉ sinh 1 dòng — nên tỷ lệ này LUÔN
    # thấp hơn tỷ lệ phân tích thành công thật. Nhóm lỗi theo thông báo để
    # nhìn ra ngay nguyên nhân nào đang chiếm đa số.
    top_errors = db.execute(
        select(LLMUsageLog.error, func.count())
        .where(base_filter, LLMUsageLog.success.is_(False), LLMUsageLog.error.is_not(None))
        .group_by(LLMUsageLog.error)
        .order_by(func.count().desc())
        .limit(10)
    ).all()

    return {
        "days": days,
        "usage_by_date": by_date,
        "calls_today": calls_today,
        "top_errors": [{"error": e, "count": n} for e, n in top_errors],
    }
