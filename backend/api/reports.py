"""api/reports.py — mục 12 "Reports (manager only)".

REDESIGN 2026-09-08 (đợt code 5, Pha 5 —
Claude outputs/dot_code_5/reports_dashboard_redesign.md): cả trang Báo cáo dùng
CHUNG 1 bộ lọc kỳ (ngày/tuần/tháng/quý/năm) thay vì mỗi bảng một khung thời gian
cứng riêng ("30 ngày gần nhất"). Vì vậy 3 endpoint cũ `/kpi`, `/trends`,
`/cost-accuracy` gộp thành 1 endpoint `/summary` nhận kỳ làm tham số — 3 endpoint
riêng thì frontend phải gửi cùng 1 khoảng thời gian 3 lần và rất dễ lệch nhau.
`/llm-usage` giữ nguyên: đó là chỉ số KỸ THUẬT theo ngày, không đi theo kỳ báo
cáo nghiệp vụ.

MỐC THỜI GIAN của từng con số (cố ý KHÔNG dùng chung 1 mốc cho tất cả):
- Số liệu về NGOẠI LỆ (số lượng, phân bố mức độ/trạng thái) -> `reported_at`.
- Số liệu về QUYẾT ĐỊNH (thời gian xử lý) -> `Decision.confirmed_at`.
- Số liệu về KẾT QUẢ (đúng hạn, chi phí thực tế, độ chính xác ước tính) ->
  `Outcome.recorded_at`.
Một ngoại lệ báo cuối tháng 3 nhưng nhập kết quả đầu tháng 4 thì chi phí thật
của nó thuộc về tháng 4 — gán hết theo `reported_at` sẽ làm tổng chi phí của kỳ
đang xem đổi ngược về quá khứ mỗi lần có người nhập kết quả muộn.

LƯU Ý TENANT ISOLATION QUAN TRỌNG: `database.py::_TENANT_MODELS` chỉ tự động
lọc company_id cho Vehicle/User/Schedule/Exception_/ExceptionGroup/Decision.
`Option`/`ImpactAnalysis`/`Outcome` KHÔNG có cột `company_id` (join qua
Exception_/Decision đã lọc sẵn là đủ an toàn). `LLMUsageLog`/`AuditLog` CÓ
company_id nhưng KHÔNG nằm trong danh sách tự lọc — mọi truy vấn trực tiếp 2
bảng này trong file này PHẢI tự thêm `.where(company_id == ...)` bằng tay.
"""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Integer, distinct, func, or_, select
from sqlalchemy.orm import Session

from core.rule_engine import ANSWER_TO_SUBTYPE
from middleware.rbac import require_role
from middleware.tenant import get_db
from models import Decision, Exception_, LLMUsageLog, Option, Outcome

router = APIRouter(prefix="/api/reports", tags=["reports"])

PERIOD_TYPES = ("day", "week", "month", "quarter", "year")

# Thứ tự 5 nhóm ngoại lệ khi hiện bảng, lấy thẳng từ rule engine để không phải
# chép tay danh sách nhóm lần thứ hai (nhóm/sub_type đã đổi 1 lần ở Pha 1).
GROUP_ORDER = list(ANSWER_TO_SUBTYPE)
SUB_TYPES_BY_GROUP = {g: sorted(set(m.values())) for g, m in ANSWER_TO_SUBTYPE.items()}


def _local_tz():
    """Múi giờ ĐỊA PHƯƠNG của server (container chạy TZ=Asia/Ho_Chi_Minh).

    Kỳ báo cáo do người dùng chọn là ngày theo lịch địa phương, còn `reported_at`
    lưu timestamptz — phải quy đổi ở đúng ranh giới này, nếu không "tháng 3" sẽ
    lệch 7 tiếng và nuốt/nhả mất vài ngoại lệ ở 2 đầu tháng.
    """
    return datetime.now().astimezone().tzinfo


def _bounds(start: date, end_inclusive: date) -> tuple:
    tz = _local_tz()
    lo = datetime.combine(start, time.min, tzinfo=tz)
    # Chặn trên là NỬA MỞ (< ngày kế tiếp) chứ không phải <= 23:59:59 — dùng
    # 23:59:59 sẽ bỏ sót mọi bản ghi rơi vào phần lẻ giây cuối ngày.
    hi = datetime.combine(end_inclusive + timedelta(days=1), time.min, tzinfo=tz)
    return lo, hi


def resolve_period(period_type: str, anchor: date) -> tuple:
    """(ngày đầu, ngày cuối, nhãn tiếng Việt) của kỳ CHỨA ngày `anchor`.

    Tuần: người dùng chọn 1 ngày bất kỳ, hệ thống tự suy ra tuần chứa nó (chốt
    thiết kế: không bắt chọn "tuần số mấy" — đếm tuần theo ISO là thứ gần như
    không ai nhẩm được trong đầu).
    """
    if period_type == "day":
        return anchor, anchor, f"Ngày {anchor.strftime('%d/%m/%Y')}"
    if period_type == "week":
        start = anchor - timedelta(days=anchor.weekday())  # weekday(): thứ 2 = 0
        end = start + timedelta(days=6)
        return start, end, f"Tuần {start.strftime('%d/%m')} - {end.strftime('%d/%m/%Y')}"
    if period_type == "month":
        start = anchor.replace(day=1)
        end = anchor.replace(day=monthrange(anchor.year, anchor.month)[1])
        return start, end, f"Tháng {anchor.month}/{anchor.year}"
    if period_type == "quarter":
        q = (anchor.month - 1) // 3 + 1
        start = date(anchor.year, 3 * (q - 1) + 1, 1)
        last_month = 3 * q
        end = date(anchor.year, last_month, monthrange(anchor.year, last_month)[1])
        return start, end, f"Quý {q}/{anchor.year}"
    if period_type == "year":
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31), f"Năm {anchor.year}"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"period_type phải là một trong {PERIOD_TYPES}",
    )


def sub_buckets(period_type: str, start: date, end: date) -> list:
    """Chia kỳ thành các kỳ CON để vẽ biểu đồ theo trục thời gian.

    Tuần/tháng chia theo NGÀY, quý/năm chia theo THÁNG — chia quý ra 90 cột ngày
    thì biểu đồ chỉ còn là một hàng rào, không đọc được xu hướng gì.
    Kỳ "ngày" không chia nhỏ hơn được nữa nên trả rỗng.
    """
    if period_type == "day":
        return []
    if period_type in ("week", "month"):
        out = []
        d = start
        while d <= end:
            out.append({"key": d.isoformat(), "label": d.strftime("%d/%m"), "start": d, "end": d})
            d += timedelta(days=1)
        return out
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        last = monthrange(y, m)[1]
        out.append(
            {
                "key": f"{y}-{m:02d}",
                "label": f"T{m}",
                "start": date(y, m, 1),
                "end": date(y, m, last),
            }
        )
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _exception_metrics(db: Session, lo, hi) -> dict:
    total = db.execute(
        select(func.count())
        .select_from(Exception_)
        .where(Exception_.deleted_at.is_(None), Exception_.reported_at >= lo, Exception_.reported_at < hi)
    ).scalar_one()

    by_severity = dict(
        db.execute(
            select(Exception_.severity, func.count())
            .where(Exception_.deleted_at.is_(None), Exception_.reported_at >= lo, Exception_.reported_at < hi)
            .group_by(Exception_.severity)
        ).all()
    )
    by_status = dict(
        db.execute(
            select(Exception_.status, func.count())
            .where(Exception_.deleted_at.is_(None), Exception_.reported_at >= lo, Exception_.reported_at < hi)
            .group_by(Exception_.status)
        ).all()
    )
    return {"total": total, "by_severity": by_severity, "by_status": by_status}


def _handling_minutes(db: Session, lo, hi):
    """Trung bình số phút từ lúc báo ngoại lệ tới lúc CHỐT phương án.

    Tính theo `Decision.confirmed_at` chứ không theo `status`: từ 2026-09-04
    "resolved" nghĩa là đã có kết quả thực tế, còn cái cần đo ở đây là tốc độ ra
    quyết định của dispatcher.
    """
    return db.execute(
        select(func.avg(func.extract("epoch", Decision.confirmed_at - Exception_.reported_at) / 60.0))
        .select_from(Decision)
        .join(Exception_, Exception_.exception_id == Decision.exception_id)
        .where(Decision.confirmed_at >= lo, Decision.confirmed_at < hi)
    ).scalar_one()


def _settlement_minutes(db: Session, lo, hi):
    """Trung bình số phút từ lúc báo ngoại lệ tới lúc GHI NHẬN KẾT QUẢ THỰC TẾ
    (`Outcome.recorded_at`) — khác `_handling_minutes()` ở trên (đo tới lúc CHỐT
    phương án). Đây là ước lượng THỜI GIAN GIẢI QUYẾT THỰC TẾ, thô hơn: đo tới
    lúc dispatcher NHẬP kết quả vào form, không chắc chắn là lúc hàng thực sự
    tới tay khách (dispatcher có thể nhập trễ hơn lúc việc thực sự xong).

    CÙNG GIỚI HẠN combined-mode như `_handling_minutes()` (xem đó) — quyết định
    GỘP nhiều ngoại lệ (`Decision.exception_id IS NULL`) chưa tính vào đây, để
    dành sửa cùng lúc nếu sau này gộp cả 2 hàm.
    """
    return db.execute(
        select(func.avg(func.extract("epoch", Outcome.recorded_at - Exception_.reported_at) / 60.0))
        .select_from(Outcome)
        .join(Decision, Decision.decision_id == Outcome.decision_id)
        .join(Exception_, Exception_.exception_id == Decision.exception_id)
        .where(Outcome.recorded_at >= lo, Outcome.recorded_at < hi)
    ).scalar_one()


def _outcome_metrics(db: Session, lo, hi) -> dict:
    """Đúng hạn / chi phí thực tế / độ chính xác ước tính của AI, theo
    `Outcome.recorded_at` (xem mốc thời gian ở docstring đầu file)."""
    in_period = (Outcome.recorded_at >= lo, Outcome.recorded_at < hi)

    on_time = db.execute(
        select(func.count()).select_from(Outcome).where(Outcome.delivered_on_time.is_(True), *in_period)
    ).scalar_one()
    # Mẫu số CHỈ gồm outcome có trả lời đúng giờ/muộn giờ. Kết quả kiểu "khách
    # từ chối nhận hàng" (Pha 2) cố ý để `delivered_on_time` NULL vì form không
    # hỏi câu đó — đưa vào mẫu số là bịa ra một tỷ lệ không ai khai.
    on_time_total = db.execute(
        select(func.count()).select_from(Outcome).where(Outcome.delivered_on_time.is_not(None), *in_period)
    ).scalar_one()

    total_actual = db.execute(
        select(func.coalesce(func.sum(Outcome.actual_cost), 0)).select_from(Outcome).where(*in_period)
    ).scalar_one()
    total_estimated = db.execute(
        select(func.coalesce(func.sum(Option.cost_estimate), 0))
        .select_from(Outcome)
        .join(Decision, Decision.decision_id == Outcome.decision_id)
        .join(Option, Option.option_id == Decision.selected_option_id)
        .where(*in_period)
    ).scalar_one()

    rows = db.execute(
        select(Option.cost_estimate, Outcome.actual_cost)
        .select_from(Outcome)
        .join(Decision, Decision.decision_id == Outcome.decision_id)
        .join(Option, Option.option_id == Decision.selected_option_id)
        .where(Option.cost_estimate.is_not(None), Outcome.actual_cost.is_not(None), *in_period)
    ).all()
    signed, absolute = [], []
    for estimated, actual in rows:
        est = float(estimated)
        if est == 0:
            # Chia cho 0 -> bỏ qua case này thay vì nhét một số vô nghĩa vào
            # trung bình. Ước tính 0đ mà thực tế cũng 0đ thì không có "sai số
            # phần trăm" nào để nói.
            continue
        diff_pct = (float(actual) - est) / est
        signed.append(diff_pct)
        absolute.append(abs(diff_pct))

    # Sai số TB dùng dấu (âm = AI ước tính cao hơn thực tế) để quản lý biết AI
    # đang lệch về phía nào; ĐỘ CHÍNH XÁC thì phải dùng trị tuyệt đối, nếu không
    # một lần vống lên và một lần hụt xuống sẽ triệt tiêu nhau thành "100% chính
    # xác".
    avg_abs = sum(absolute) / len(absolute) if absolute else None
    return {
        "on_time_rate": round(on_time / on_time_total, 4) if on_time_total else None,
        "outcome_count": on_time_total,
        "total_actual_cost": float(total_actual),
        "total_estimated_cost": float(total_estimated),
        "cost_accuracy_rate": round(max(0.0, 1 - avg_abs), 4) if avg_abs is not None else None,
        "cost_avg_diff_pct": round(sum(signed) / len(signed), 4) if signed else None,
        "cost_sample_size": len(signed),
    }


def _ai_option_rate(db: Session, company_id: str, lo, hi) -> dict:
    """Tỷ lệ SINH PHƯƠNG ÁN thành công = số ngoại lệ có ít nhất 1 phương án do AI
    sinh ÷ số ngoại lệ thực sự có gọi AI trong kỳ.

    KHÁC HẲN "tỷ lệ gọi API thành công" ở bảng Chi phí AI: cái kia đếm từng lượt
    HTTP nên 1 lần phân tích hỏng sinh tới 3 dòng lỗi (MAX_LLM_RETRIES) còn 1 lần
    thành công ngay chỉ sinh 1 dòng — nó là chỉ số vận hành, không phải chất
    lượng sản phẩm. Cái ở đây mới trả lời được "dispatcher có phương án để chọn
    hay không".

    Phân biệt phương án AI với phương án dispatcher tự nhập bằng 2 dấu hiệu,
    CHẤP NHẬN 1 trong 2 là đủ:
    - `prompt_version_id` — nguồn chuẩn, nhưng `job_processor` mới bắt đầu ghi
      từ 2026-09-10, nên mọi phương án sinh TRƯỚC đó đều để trống;
    - `llm_explanation` — chỉ phương án LLM mới có (`create_manual_option` và
      phương án placeholder khi AI lỗi đều để trống), nên đây là cách duy nhất
      nhận ra dữ liệu cũ.
    Chỉ dựa vào `prompt_version_id` thì chỉ số này báo 0% cho toàn bộ dữ liệu
    lịch sử — đã kiểm chứng bằng dữ liệu thật trước khi sửa.
    """
    called = db.execute(
        select(func.count(distinct(LLMUsageLog.exception_id))).where(
            LLMUsageLog.company_id == company_id,
            LLMUsageLog.exception_id.is_not(None),
            LLMUsageLog.created_at >= lo,
            LLMUsageLog.created_at < hi,
        )
    ).scalar_one()
    if not called:
        return {"ai_option_rate": None, "ai_called_exceptions": 0}

    called_ids = select(distinct(LLMUsageLog.exception_id)).where(
        LLMUsageLog.company_id == company_id,
        LLMUsageLog.exception_id.is_not(None),
        LLMUsageLog.created_at >= lo,
        LLMUsageLog.created_at < hi,
    )
    with_options = db.execute(
        select(func.count(distinct(Option.exception_id))).where(
            Option.exception_id.in_(called_ids),
            or_(Option.prompt_version_id.is_not(None), Option.llm_explanation.is_not(None)),
        )
    ).scalar_one()
    return {"ai_option_rate": round(with_options / called, 4), "ai_called_exceptions": called}


def _group_breakdown(db: Session, lo, hi) -> list:
    """Bảng "Ngoại lệ theo loại": 5 nhóm lớn, mỗi nhóm mở ra được 11 sub_type.

    Chi phí/thời gian join qua `decisions` nên quyết định PHỐI HỢP cả nhóm
    (combined mode, `decisions.exception_id` NULL) không được tính vào đây — số
    "số lần xảy ra" vẫn đủ, chỉ 2 cột tiền/thời gian là thiếu phần đó. Chấp nhận
    có chủ đích: gán chi phí chung của 1 quyết định phối hợp cho từng thành viên
    thì phải chia tiền theo một quy tắc bịa ra, sai nhiều hơn là thiếu.
    """
    rows = db.execute(
        select(
            Exception_.exception_group,
            Exception_.sub_type,
            func.count(distinct(Exception_.exception_id)),
            func.coalesce(func.sum(Outcome.actual_cost), 0),
            func.coalesce(
                func.sum(func.extract("epoch", Decision.confirmed_at - Exception_.reported_at) / 60.0), 0
            ),
            func.count(distinct(Decision.decision_id)),
        )
        .select_from(Exception_)
        .outerjoin(Decision, Decision.exception_id == Exception_.exception_id)
        .outerjoin(Outcome, Outcome.decision_id == Decision.decision_id)
        .where(Exception_.deleted_at.is_(None), Exception_.reported_at >= lo, Exception_.reported_at < hi)
        .group_by(Exception_.exception_group, Exception_.sub_type)
    ).all()

    groups: dict = {}
    for group, sub_type, count, cost, minutes, decided in rows:
        g = groups.setdefault(
            group, {"group": group, "count": 0, "actual_cost": 0.0, "handling_minutes": 0.0, "decided": 0, "sub_types": []}
        )
        g["count"] += count
        g["actual_cost"] += float(cost)
        g["handling_minutes"] += float(minutes)
        g["decided"] += decided
        g["sub_types"].append(
            {
                "sub_type": sub_type,
                "count": count,
                "actual_cost": float(cost),
                "handling_minutes": round(float(minutes), 1),
                "handling_minutes_avg": round(float(minutes) / decided, 1) if decided else None,
            }
        )

    out = []
    for group in GROUP_ORDER:
        g = groups.pop(group, None)
        if g is None:
            continue
        g["handling_minutes"] = round(g["handling_minutes"], 1)
        g["handling_minutes_avg"] = round(g["handling_minutes"] / g["decided"], 1) if g["decided"] else None
        g["sub_types"].sort(key=lambda s: -s["count"])
        out.append(g)
    # Nhóm lạ (dữ liệu cũ mang exception_group không còn trong rule engine) vẫn
    # phải hiện, xếp cuối — im lặng bỏ đi là báo cáo thiếu mà không ai biết.
    for g in groups.values():
        g["handling_minutes"] = round(g["handling_minutes"], 1)
        g["handling_minutes_avg"] = round(g["handling_minutes"] / g["decided"], 1) if g["decided"] else None
        out.append(g)
    return out


def _bucket_series(db: Session, period_type: str, start: date, end: date) -> list:
    """Số liệu cho biểu đồ kỳ con. Gom bằng Python trên 2 truy vấn gộp sẵn thay
    vì chạy 1 truy vấn cho MỖI cột (tháng 31 ngày = 31 lượt gọi DB)."""
    buckets = sub_buckets(period_type, start, end)
    if not buckets:
        return []
    lo, hi = _bounds(start, end)
    index = {}
    for b in buckets:
        b_key = b["key"]
        index[b_key] = {
            "key": b_key,
            "label": b["label"],
            "total": 0,
            "by_group": {},
            "actual_cost": 0.0,
        }

    def bucket_key(d: date) -> str:
        return d.isoformat() if period_type in ("week", "month") else f"{d.year}-{d.month:02d}"

    tz = _local_tz()
    for reported_at, group, count in db.execute(
        select(Exception_.reported_at, Exception_.exception_group, func.count())
        .where(Exception_.deleted_at.is_(None), Exception_.reported_at >= lo, Exception_.reported_at < hi)
        .group_by(Exception_.reported_at, Exception_.exception_group)
    ).all():
        slot = index.get(bucket_key(reported_at.astimezone(tz).date()))
        if slot is None:
            continue
        slot["total"] += count
        slot["by_group"][group] = slot["by_group"].get(group, 0) + count

    for recorded_at, cost in db.execute(
        select(Outcome.recorded_at, Outcome.actual_cost).where(
            Outcome.recorded_at >= lo, Outcome.recorded_at < hi, Outcome.actual_cost.is_not(None)
        )
    ).all():
        slot = index.get(bucket_key(recorded_at.astimezone(tz).date()))
        if slot is not None:
            slot["actual_cost"] += float(cost)

    return [{**v, "actual_cost": round(v["actual_cost"], 2)} for v in index.values()]


def _period_payload(db: Session, company_id: str, period_type: str, anchor: date, with_buckets: bool) -> dict:
    start, end, label = resolve_period(period_type, anchor)
    lo, hi = _bounds(start, end)

    exc = _exception_metrics(db, lo, hi)
    outcome = _outcome_metrics(db, lo, hi)
    settle_minutes = _settlement_minutes(db, lo, hi)
    avg_minutes = _handling_minutes(db, lo, hi)
    resolved = exc["by_status"].get("resolved", 0)

    return {
        "period": {
            "type": period_type,
            "anchor": anchor.isoformat(),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "label": label,
        },
        "kpi": {
            "total_exceptions": exc["total"],
            "by_severity": {k: exc["by_severity"].get(k, 0) for k in ("warning", "serious", "critical")},
            "by_status": {
                k: exc["by_status"].get(k, 0)
                for k in ("pending", "analyzing", "awaiting_decision", "awaiting_outcome", "resolved")
            },
            "resolved_rate": round(resolved / exc["total"], 4) if exc["total"] else None,
            "avg_resolution_minutes": round(float(avg_minutes), 1) if avg_minutes is not None else None,
            "avg_resolution_minutes_note": (
                "Thời gian RA QUYẾT ĐỊNH (từ lúc báo tới lúc chốt phương án), "
                "chỉ tính ngoại lệ có quyết định RIÊNG LẺ — quyết định GỘP nhiều "
                "ngoại lệ cùng lúc chưa tính vào số này."
            ),
            "avg_settlement_minutes": round(float(settle_minutes), 1) if settle_minutes is not None else None,
            **outcome,
            **_ai_option_rate(db, company_id, lo, hi),
        },
        "by_group": _group_breakdown(db, lo, hi),
        "buckets": _bucket_series(db, period_type, start, end) if with_buckets else [],
    }


@router.get("/summary")
def get_summary(
    period_type: str = Query(default="month", description="day|week|month|quarter|year"),
    anchor: date = Query(default=None, description="Ngày bất kỳ NẰM TRONG kỳ cần xem. Bỏ trống = hôm nay."),
    compare_anchor: date = Query(default=None, description="Bật so sánh 2 kỳ — CÙNG period_type với kỳ A."),
    with_buckets: bool = Query(default=False, description="Kèm số liệu kỳ con để vẽ biểu đồ."),
    current_user: dict = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    """Toàn bộ số liệu của trang Báo cáo cho 1 kỳ (và 1 kỳ so sánh, nếu có).

    So sánh BẮT BUỘC cùng `period_type` (thiết kế chốt: so ngày với ngày, tháng
    với tháng) nên chỉ nhận thêm 1 mốc `compare_anchor`, không nhận cả loại kỳ
    thứ hai — như vậy sai lệch kiểu "so 1 ngày với cả năm" không tồn tại được.
    """
    if period_type not in PERIOD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"period_type phải là một trong {PERIOD_TYPES}",
        )
    anchor = anchor or datetime.now(_local_tz()).date()
    company_id = current_user["company_id"]

    result = _period_payload(db, company_id, period_type, anchor, with_buckets)
    result["sub_types_by_group"] = SUB_TYPES_BY_GROUP
    if compare_anchor is not None:
        result["compare"] = _period_payload(db, company_id, period_type, compare_anchor, with_buckets)
    return result


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
    # thấp hơn tỷ lệ SINH PHƯƠNG ÁN thành công (`ai_option_rate` ở /summary).
    # Lượt bị cắt vì quá `MAX_ATTEMPT_LLM_SECONDS` cũng được ghi thành 1 dòng
    # success=False nên tính đúng vào đây (xem core/option_generator.py).
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
