"""rag_anonymization.py — pipeline ẩn danh hoá nạp case vào `rag_case_bank`
(TECHNICAL_SPEC.md mục 20.2).

Chạy trong BACKGROUND JOB, KHÔNG đồng bộ lúc dispatcher xác nhận quyết định
(mục 20.2 bước 1) — `run_pending_admissions()` là hàm driver, gọi định kỳ từ
1 job riêng (KHÔNG phải luồng `worker/job_processor.py::process_pending_jobs`
xử lý `analyze_exception`/`analyze_group` — cố ý tách biệt, nạp RAG không có
gì khẩn cấp/ưu tiên như phân tích ngoại lệ thật). Chưa wire vào
`run_forever()` của worker chính — xem ghi chú cuối file — nhưng logic pipeline
đã đầy đủ và có test (scripts/test_rag_anonymization.py).
"""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.impact_analyzer import compute_downstream_stops_affected, compute_has_priority_order
from core.rag_trace import encrypt_value
from models import Company, Decision, Exception_, ImpactAnalysis, Option, Outcome, RagCaseBank, RagCaseSourceMap, Schedule

# Ngưỡng k-anonymity (mục 20.2 bước 4) — cấu hình được qua rule_versions như
# các ngưỡng khác trong hệ thống, nhưng để đơn giản (chưa có UI cấu hình
# riêng cho ngưỡng này) hiện là hằng số; đổi ở đây nếu cần.
K_ANONYMITY_THRESHOLD = 5

# "toàn thành phố" khi generalize area_bucket (mục 20.2 bước 4) — đơn giản
# hoá có chủ đích: seed data hiện chỉ có các quận/huyện của Hà Nội, generalize
# 1 bậc luôn là "Hà Nội". Triển khai thật nhiều thành phố cần bảng tra quận/
# huyện -> thành phố thay vì 1 hằng số.
CITY_LEVEL_FALLBACK = "Hà Nội"

_PHONE_PATTERN = re.compile(r"(?:\+84|0)\d{9,10}\b")


def bucket_time_to_deadline(minutes: "int | None") -> "str | None":
    if minutes is None:
        return None
    if minutes < 30:
        return "<30p"
    if minutes <= 90:
        return "30-90p"
    return ">90p"


def bucket_volume_kg(volume_kg: "float | None") -> "str | None":
    if volume_kg is None:
        return None
    if volume_kg < 50:
        return "nhẹ(<50kg)"
    if volume_kg <= 200:
        return "vừa(50-200kg)"
    return "nặng(>200kg)"


def redact_notes(
    notes: "str | None",
    *,
    customer_name: "str | None" = None,
    driver_name: "str | None" = None,
    address: "str | None" = None,
) -> "str | None":
    """Mục 20.2 bước 3 — loại SĐT (regex số VN) + tên riêng/địa chỉ CỦA CHÍNH
    CASE ĐÓ nếu xuất hiện y nguyên trong text tự do. KHÔNG dùng LLM để diễn
    giải lại (rủi ro bịa thêm chi tiết) — chỉ xoá/thay thế token trùng khớp,
    đúng nguyên tắc spec."""
    if not notes:
        return notes

    redacted = _PHONE_PATTERN.sub("[SĐT]", notes)
    for token, placeholder in (
        (customer_name, "[TÊN KHÁCH]"),
        (driver_name, "[TÊN TÀI XẾ]"),
        (address, "[ĐỊA CHỈ]"),
    ):
        if token and token.strip():
            redacted = re.sub(re.escape(token.strip()), placeholder, redacted, flags=re.IGNORECASE)
    return redacted


def check_k_anonymity_count(
    db: Session, exception_group: str, sub_type: str, area_bucket: "str | None", shift_label: "str | None"
) -> int:
    """Đếm case HIỆN CÓ trong kho cùng tổ hợp (exception_group, sub_type,
    area_bucket, shift_label) — dùng để quyết định có cần generalize thêm
    area_bucket trước khi nạp case MỚI hay không (mục 20.2 bước 4)."""
    stmt = select(RagCaseBank).where(
        RagCaseBank.exception_group == exception_group,
        RagCaseBank.sub_type == sub_type,
        RagCaseBank.shift_label == shift_label,
    )
    stmt = stmt.where(RagCaseBank.area_bucket == area_bucket) if area_bucket is not None else stmt.where(RagCaseBank.area_bucket.is_(None))
    return len(db.execute(stmt).scalars().all())


def resolve_area_bucket(
    db: Session, exception_group: str, sub_type: str, area: "str | None", shift_label: "str | None",
    threshold: int = K_ANONYMITY_THRESHOLD,
) -> "str | None":
    """Mục 20.2 bước 4, BẮT BUỘC (không phải tuỳ chọn): nếu kho hiện có ÍT
    HƠN `threshold` case khác cùng tổ hợp (exception_group, sub_type,
    area_bucket=quận/huyện, shift_label) -> generalize area_bucket lên 1 bậc
    (quận/huyện -> toàn thành phố) TRƯỚC khi nạp, thay vì nạp thẳng 1 case
    "hiếm" dễ bị soi ra."""
    if area is None:
        return None
    existing = check_k_anonymity_count(db, exception_group, sub_type, area, shift_label)
    if existing >= threshold:
        return area
    return CITY_LEVEL_FALLBACK


def build_case_fields(
    *,
    exception_group: str,
    sub_type: str,
    severity: "str | None",
    area_bucket: "str | None",
    shift_label: "str | None",
    time_to_deadline_min: "int | None",
    downstream_stops_affected: "int | None",
    has_priority_order: "bool | None",
    cargo_type: "str | None",
    volume_kg: "float | None",
    notes: "str | None",
    customer_name: "str | None" = None,
    driver_name: "str | None" = None,
    address: "str | None" = None,
    option_cost_estimate: "Decimal | float | None" = None,
    option_time_estimate_minutes: "int | None" = None,
    option_sla_risk_remaining: "Decimal | float | None" = None,
    outcome_delivered_on_time: "bool | None" = None,
    outcome_cost_variance_pct: "Decimal | float | None" = None,
) -> dict:
    """Hàm THUẦN (không đụng DB) — nhận dữ liệu thật đã được caller gom lại,
    trả về dict CÁC TRƯỜNG ĐÃ ẨN DANH HOÁ sẵn sàng tạo `RagCaseBank`. Tách
    riêng khỏi phần truy vấn DB (`admit_from_decision`) để test được logic
    bucket hoá/redact độc lập, không cần DB thật."""
    return {
        "exception_group": exception_group,
        "sub_type": sub_type,
        "severity": severity,
        "area_bucket": area_bucket,
        "shift_label": shift_label,
        "time_to_deadline_bucket": bucket_time_to_deadline(time_to_deadline_min),
        "downstream_stops_affected": downstream_stops_affected,
        "has_priority_order": has_priority_order,
        "cargo_type": cargo_type,
        "volume_kg_bucket": bucket_volume_kg(volume_kg),
        "notes_redacted": redact_notes(notes, customer_name=customer_name, driver_name=driver_name, address=address),
        "option_cost_estimate": option_cost_estimate,
        "option_time_estimate_minutes": option_time_estimate_minutes,
        "option_sla_risk_remaining": option_sla_risk_remaining,
        "outcome_delivered_on_time": outcome_delivered_on_time,
        "outcome_cost_variance_pct": outcome_cost_variance_pct,
    }


def _deterministic_delay_days(outcome_id, min_delay_days: int, max_delay_days: int) -> int:
    """"Trễ nạp có chủ đích" (mục 20.2 bước 2) — độ trễ NGẪU NHIÊN nhưng ỔN
    ĐỊNH theo từng outcome (không đổi giữa các lần poll), suy ra từ hash của
    outcome_id thay vì lưu thêm 1 cột riêng cho "ngày dự kiến nạp"."""
    digest = hashlib.sha256(str(outcome_id).encode()).digest()
    span = max(max_delay_days - min_delay_days, 1)
    return min_delay_days + (int.from_bytes(digest[:4], "big") % span)


def find_admission_candidates(db: Session, min_delay_days: int = 3, max_delay_days: int = 14) -> list[Outcome]:
    """Outcome đủ điều kiện nạp: chưa nạp (`admitted_to_rag_at IS NULL`) và
    đã qua đúng độ trễ có chủ đích riêng của nó."""
    now = datetime.now(timezone.utc)
    candidates = db.execute(select(Outcome).where(Outcome.admitted_to_rag_at.is_(None))).scalars().all()
    eligible = []
    for outcome in candidates:
        delay_days = _deterministic_delay_days(outcome.outcome_id, min_delay_days, max_delay_days)
        if outcome.recorded_at + timedelta(days=delay_days) <= now:
            eligible.append(outcome)
    return eligible


def admit_from_decision(db: Session, outcome: Outcome, key: bytes) -> "RagCaseBank | None":
    """Gom dữ liệu thật từ decision/exception/schedule/option/outcome liên
    quan tới `outcome`, ẩn danh hoá, nạp vào `rag_case_bank` + ghi
    `rag_case_source_map` (mã hoá). Trả None (KHÔNG nạp) nếu company chưa bật
    `rag_data_sharing_consent` — case của công ty chưa đồng ý chia sẻ KHÔNG
    được đưa vào kho chung dưới bất kỳ hình thức nào, kể cả đã ẩn danh hoá."""
    decision = db.get(Decision, outcome.decision_id, execution_options={"skip_tenant_filter": True})
    if decision is None:
        return None
    company = db.get(Company, decision.company_id, execution_options={"skip_tenant_filter": True})
    if company is None or not company.rag_data_sharing_consent:
        return None

    option = db.get(Option, decision.selected_option_id, execution_options={"skip_tenant_filter": True})
    exception_id = decision.exception_id
    if exception_id is None:
        # Combined-mode (group) decision — mục F cũng không xử lý group,
        # cùng lý do: 1 quyết định phối hợp gộp nhiều exception khác nhau,
        # ẩn danh hoá "1 case = 1 exception" không khớp mô hình group. Bỏ
        # qua nạp cho các outcome thuộc combined-mode ở giai đoạn này.
        return None

    exc = db.get(Exception_, exception_id, execution_options={"skip_tenant_filter": True})
    if exc is None:
        return None
    schedule = db.get(Schedule, exc.schedule_id, execution_options={"skip_tenant_filter": True})
    impact = db.execute(
        select(ImpactAnalysis).where(ImpactAnalysis.exception_id == exc.exception_id)
    ).scalar_one_or_none()
    affected_stops = impact.affected_stops if impact else []

    time_to_deadline_min = None
    if schedule is not None and affected_stops:
        deadlines = []
        for s in affected_stops:
            sla_deadline = s.get("sla_deadline")
            if sla_deadline:
                deadlines.append(datetime.combine(schedule.shift_date, datetime.fromisoformat(sla_deadline).time()))
        if deadlines:
            reported_at_local = exc.reported_at.replace(tzinfo=None)
            time_to_deadline_min = int((min(deadlines) - reported_at_local).total_seconds() // 60)

    first_stop = (schedule.stops[0] if schedule and schedule.stops else {}) or {}
    cost_variance_pct = None
    if outcome.actual_cost is not None and option is not None and option.cost_estimate:
        cost_variance_pct = (float(outcome.actual_cost) - float(option.cost_estimate)) / float(option.cost_estimate)

    # `schedules.shift_label` đã bị bỏ (migration c8d9e0f1a2b3) — kho case
    # dùng chung vẫn GIỮ cột `rag_case_bank.shift_label` cho case lịch sử, nên
    # case nạp từ nay truyền None. Bucket k-anonymity vì thế THÔ HƠN (gộp mọi
    # ca lại), tức là an toàn hơn chứ không lỏng hơn.
    area_bucket = resolve_area_bucket(db, exc.exception_group, exc.sub_type, exc.area, None)

    fields = build_case_fields(
        exception_group=exc.exception_group,
        sub_type=exc.sub_type,
        severity=exc.severity,
        area_bucket=area_bucket,
        shift_label=None,
        time_to_deadline_min=time_to_deadline_min,
        downstream_stops_affected=compute_downstream_stops_affected(affected_stops),
        has_priority_order=compute_has_priority_order(affected_stops),
        cargo_type=first_stop.get("cargo_type"),
        volume_kg=first_stop.get("volume_kg"),
        notes=exc.description,
        customer_name=first_stop.get("customer_name"),
        address=first_stop.get("address"),
        option_cost_estimate=option.cost_estimate if option else None,
        option_time_estimate_minutes=option.time_estimate_minutes if option else None,
        option_sla_risk_remaining=option.sla_risk_remaining if option else None,
        outcome_delivered_on_time=outcome.delivered_on_time,
        outcome_cost_variance_pct=cost_variance_pct,
    )

    case = RagCaseBank(**fields)
    db.add(case)
    db.flush()

    db.add(
        RagCaseSourceMap(
            case_id=case.case_id,
            company_id_encrypted=encrypt_value(str(decision.company_id), key),
            exception_id_encrypted=encrypt_value(str(exception_id), key),
        )
    )
    outcome.admitted_to_rag_at = datetime.now(timezone.utc)
    return case


def run_pending_admissions(db: Session, key: bytes, min_delay_days: int = 3, max_delay_days: int = 14) -> int:
    """Driver — gọi định kỳ từ 1 job riêng (KHÔNG wired vào
    `worker/job_processor.run_forever` — xem docstring đầu file). Trả về số
    case đã nạp thành công trong lần chạy này."""
    admitted = 0
    for outcome in find_admission_candidates(db, min_delay_days, max_delay_days):
        case = admit_from_decision(db, outcome, key)
        if case is not None:
            admitted += 1
        else:
            # Không đủ điều kiện nạp (chưa consent, combined-mode...) — vẫn
            # đánh dấu đã "xử lý" để không thử lại vô ích mỗi lần poll.
            outcome.admitted_to_rag_at = datetime.now(timezone.utc)
    db.commit()
    return admitted
