"""option_generator.py — build CONTEXT + gọi LLM sinh phương án (mục 8, 9, 19).

Luồng: build_context() -> ghép [system prompt] + [prompt theo sub_type/group]
+ CONTEXT (JSON) -> llm_adapter.generate() -> parse JSON -> retry theo mục 8
nếu parse lỗi -> trả list dict phương án thô (chưa rank, ranker.py lo ở
Giai đoạn 7).
"""
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.conflict_detector import detect_conflict
from core.llm_adapter import MODEL_NAME, generate
from core.llm_usage import DAILY_CALL_LIMIT_DEFAULT, has_quota_remaining, log_llm_call
from models import Company, Exception_, ExceptionGroup, ImpactAnalysis, PromptVersion, Schedule, Vehicle

MAX_LLM_RETRIES = 3


class QuotaExceededError(RuntimeError):
    """Đã chạm `DAILY_CALL_LIMIT_DEFAULT` calls/company/ngày (mục 8) — caller
    (job_processor) bắt lỗi này để chuyển sang cho dispatcher nhập phương án
    thủ công, KHÔNG crash worker."""

_STOP_FIELDS_FOR_CONTEXT = (
    "stop_id",
    "order_id",
    "address",
    "area",
    "eta",
    "sla_deadline",
    "priority_tier",
    "sla_penalty",
    "volume_kg",
    "cargo_type",
    "notes",
)


def _get_active_prompt(db: Session, sub_type: str) -> str:
    prompt = db.execute(
        select(PromptVersion).where(PromptVersion.sub_type == sub_type, PromptVersion.is_active.is_(True))
    ).scalar_one_or_none()
    if prompt is None:
        raise RuntimeError(f"Không có prompt active cho sub_type='{sub_type}' — chạy scripts/seed_prompts.py")
    return prompt.content, prompt.version_id


def build_context(db: Session, exception: Exception_) -> dict:
    """CONTEXT cho 1 ngoại lệ đơn lẻ (mục 19 intro)."""
    schedule = db.get(Schedule, exception.schedule_id)
    vehicle = db.get(Vehicle, exception.vehicle_id) if exception.vehicle_id else None
    company = db.get(Company, exception.company_id)
    impact = db.execute(
        select(ImpactAnalysis).where(ImpactAnalysis.exception_id == exception.exception_id)
    ).scalar_one_or_none()

    cost_per_km = None
    if vehicle is not None:
        cost_per_km = vehicle.cost_per_km if vehicle.cost_per_km is not None else (company.default_cost_per_km if company else None)

    return {
        "exception_id": str(exception.exception_id),
        "exception": {
            "exception_group": exception.exception_group,
            "sub_type": exception.sub_type,
            "severity": exception.severity,
            "description": exception.description,
            "vehicle_id": exception.vehicle_id,
            "area": exception.area,
        },
        "vehicle": {
            "driver_name": vehicle.driver_name if vehicle else None,
            "max_payload_kg": float(vehicle.max_payload_kg) if vehicle else None,
            "cost_per_km": float(cost_per_km) if cost_per_km is not None else None,
            "vehicle_type": vehicle.vehicle_type if vehicle else None,
        },
        "trip": {
            "planned_departure_time": schedule.planned_departure_time.isoformat() if schedule and schedule.planned_departure_time else None,
            "stops": [
                {k: s.get(k) for k in _STOP_FIELDS_FOR_CONTEXT}
                for s in (schedule.stops if schedule else [])
            ],
        },
        "impact_analysis": {
            "affected_stops": impact.affected_stops if impact else [],
            "total_cost_estimate": float(impact.total_cost_estimate) if impact and impact.total_cost_estimate is not None else None,
        },
        "distance_info": None,  # Giai đoạn 7 (geocoder) sẽ điền, graceful degradation nếu thiếu (mục 14)
        "ranking_weights": company.ranking_weights if company else None,
    }


def _exception_to_conflict_dict(db: Session, exc: Exception_) -> dict:
    """Dựng lại dict cho `conflict_detector.detect_conflict` — CÙNG shape với
    `api/exceptions.py::_active_exceptions_as_dicts`, tái dùng để tránh viết
    lại (và làm sai lệch) logic phát hiện xung đột ở 2 nơi."""
    vehicle = db.get(Vehicle, exc.vehicle_id) if exc.vehicle_id else None
    impact = db.execute(select(ImpactAnalysis).where(ImpactAnalysis.exception_id == exc.exception_id)).scalar_one_or_none()
    return {
        "exception_id": str(exc.exception_id),
        "vehicle_id": exc.vehicle_id,
        "driver_name": vehicle.driver_name if vehicle else None,
        "schedule_id": str(exc.schedule_id),
        "affected_stop_ids": [s["stop_id"] for s in (impact.affected_stops or [])] if impact else [],
        "sub_type": exc.sub_type,
        "severity": exc.severity,
        "area": exc.area,
        "reported_at": exc.reported_at,
    }


def _infer_conflict_signals(db: Session, members: list[Exception_]) -> list[str]:
    """Tái dùng `detect_conflict` (KHÔNG viết lại logic riêng) để liệt kê mọi
    tín hiệu xung đột thật giữa các cặp thành viên trong nhóm — hiển thị cho
    LLM biết TẠI SAO chúng bị gộp (mục 19.2). `nearest_available_vehicles_fn`
    chưa truyền vào (cần geocoder, Giai đoạn 7) nên `resource_contention` giữa
    2 xe khác nhau chưa tự phát hiện lại được ở đây — nhóm vẫn đã được gộp
    đúng lúc tạo (api/exceptions.py), chỉ riêng NHÃN giải thích tạm thời chưa
    đầy đủ cho đến khi có Giai đoạn 7."""
    dicts = [_exception_to_conflict_dict(db, m) for m in members]
    signals = set()
    for i, a in enumerate(dicts):
        _, _, pair_signals = detect_conflict(a, dicts[i + 1 :])
        signals.update(pair_signals)
    return sorted(signals)


def build_group_context(db: Session, group: ExceptionGroup) -> dict:
    """CONTEXT cho combined mode (mục 19.2) — mảng đầy đủ các ngoại lệ + conflict_signals."""
    members = db.execute(select(Exception_).where(Exception_.exception_id.in_(group.exception_ids))).scalars().all()
    return {
        "group_id": str(group.group_id),
        "exceptions": [build_context(db, m) for m in members],
        "conflict_signals": _infer_conflict_signals(db, members),
    }


def _clean_json_text(text: str) -> str:
    """Bước 2 mục 8: dọn text thừa (code fence, giải thích ngoài JSON) trước khi thử parse lại."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


def _try_parse_options(text: str) -> "list[dict] | None":
    for candidate in (text, _clean_json_text(text)):
        try:
            data = json.loads(candidate)
            options = data.get("options")
            if isinstance(options, list) and len(options) > 0:
                return options
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


def _call_llm_with_retry(
    full_prompt: str,
    db: "Session | None" = None,
    company_id: "str | None" = None,
    exception_id: "str | None" = None,
    prompt_version_id: "str | None" = None,
    daily_limit: int = DAILY_CALL_LIMIT_DEFAULT,
) -> tuple["list[dict] | None", dict]:
    """Retry logic mục 8: gọi -> parse -> nếu fail, dọn text thử lại -> nếu vẫn
    fail, gọi lại kèm nhắc rõ 'respond ONLY with valid JSON' -> tối đa 3 lần.

    Nếu truyền `db`+`company_id`: kiểm tra hạn mức `DAILY_CALL_LIMIT_DEFAULT`
    (mục 8) TRƯỚC mỗi lần gọi thật (kể cả các lần retry — mỗi lần đều tính vào
    hạn mức), và ghi `llm_usage_logs` (mục 9) sau mỗi lần gọi. Bỏ trống `db`
    để test logic parse/retry thuần (xem `scripts/test_llm_retry.py`) mà
    không đụng DB.
    """
    usage = {"tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "success": False, "error": None}
    prompt = full_prompt
    track_usage = db is not None and company_id is not None

    for attempt in range(MAX_LLM_RETRIES):
        if track_usage and not has_quota_remaining(db, company_id, limit=daily_limit):
            usage["error"] = f"Đã chạm giới hạn {daily_limit} lượt gọi AI/ngày cho công ty này"
            raise QuotaExceededError(usage["error"])

        result = generate(prompt)
        usage["tokens_in"] += result.tokens_in
        usage["tokens_out"] += result.tokens_out
        usage["latency_ms"] += result.latency_ms

        if track_usage:
            log_llm_call(
                db, company_id, exception_id, MODEL_NAME,
                result.tokens_in, result.tokens_out, result.latency_ms,
                prompt_version_id, result.success,
            )

        if not result.success:
            usage["error"] = result.error
            continue

        options = _try_parse_options(result.text)
        if options is not None:
            usage["success"] = True
            return options, usage

        usage["error"] = "Không parse được JSON từ response LLM"
        prompt = full_prompt + "\n\nIMPORTANT: respond ONLY with valid JSON, no other text."

    return None, usage


def generate_options_for_exception(db: Session, exception: Exception_) -> tuple["list[dict] | None", dict]:
    system_prompt, _ = _get_active_prompt(db, "system")
    sub_prompt, prompt_version_id = _get_active_prompt(db, exception.sub_type)
    context = build_context(db, exception)

    full_prompt = f"{system_prompt}\n\n{sub_prompt}\n\nCONTEXT: {json.dumps(context, ensure_ascii=False)}"
    options, usage = _call_llm_with_retry(
        full_prompt, db=db, company_id=str(exception.company_id),
        exception_id=str(exception.exception_id), prompt_version_id=prompt_version_id,
    )
    usage["prompt_version_id"] = prompt_version_id
    return options, usage


def generate_options_for_group(db: Session, group: ExceptionGroup) -> tuple["list[dict] | None", dict]:
    system_prompt, _ = _get_active_prompt(db, "system")
    group_prompt, prompt_version_id = _get_active_prompt(db, "group")
    context = build_group_context(db, group)

    full_prompt = f"{system_prompt}\n\n{group_prompt}\n\nCONTEXT: {json.dumps(context, ensure_ascii=False)}"
    options, usage = _call_llm_with_retry(
        full_prompt, db=db, company_id=str(group.company_id),
        exception_id=None, prompt_version_id=prompt_version_id,
    )
    usage["prompt_version_id"] = prompt_version_id
    return options, usage
