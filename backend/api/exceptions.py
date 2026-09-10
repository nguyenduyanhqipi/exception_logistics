from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from api.decisions import outcome_to_dict
from core.conflict_detector import detect_conflict, nearest_available_vehicles
from core.impact_analyzer import analyze_impact
from core.rule_engine import calculate_severity, classify_sub_type
from middleware.auth import get_current_user
from middleware.tenant import get_db
from models import (
    AuditLog,
    BackgroundJob,
    Decision,
    Exception_,
    ExceptionGroup,
    ImpactAnalysis,
    Option,
    Outcome,
    ResourceLock,
    Schedule,
    User,
    Vehicle,
)
from schemas.exception import ExceptionCreate, ExceptionResponse, ExceptionUpdate, ManualOptionCreate

router = APIRouter(prefix="/api/exceptions", tags=["exceptions"])

ACTIVE_STATUSES = ("pending", "analyzing", "awaiting_decision")

# Các field đầu vào rule_engine tiêu thụ rồi bỏ (chỉ `severity` được lưu). Giữ
# nguyên bản vào `exceptions.input_context` để form SỬA nạp lại được — xem
# models/exception.py::Exception_.input_context.
_SIGNAL_FIELDS = (
    "answer_key",
    # Ghi chú NGƯỜI DÙNG gõ. Từ khi bỏ `description_note`, nó trùng đúng với
    # `exceptions.description`; vẫn giữ ở đây để form sửa có một nguồn duy
    # nhất cho mọi ô đã nhập, và để ngoại lệ CŨ (description còn dính note do
    # rule engine sinh) nạp lại được đúng phần người dùng viết.
    "description",
    "has_injury",
    "from_stop_order",
    "to_stop_order",
    "delay_minutes",
    "departure_delay_min",
    "driver_contact_lost_min",
    "estimated_traffic_duration_min",
    "is_repeat_delivery",
    "has_time_conflict",
    "new_location_distance_km",
    "estimated_repair_min",
    # Câu trả lời phụ thêm ở redesign 2026-09-08 (exception_intake_review.md).
    # `depot_on_time`/`new_address_distance_km` đã bỏ cùng lúc `slow_loading`/
    # `wrong_address` retire — input_context của ngoại lệ CŨ vẫn còn 2 key đó,
    # chỉ là từ nay không ghi thêm nữa.
    "departure_status",
    "late_departure_cause",
    "estimated_departure_delay_min",
    "departed_late_cause",
    "contacted_customer",
    "customer_request",
    "dispute_type",
    "can_transfer_cargo_safely",
    "vehicle_movable",
    "current_lat",
    "current_lng",
    "current_address",
)


def _input_context(payload) -> dict:
    return {"exception_group": payload.exception_group, **{f: getattr(payload, f) for f in _SIGNAL_FIELDS}}


def _active_exceptions_as_dicts(db: Session, exclude_id=None) -> list[dict]:
    rows = db.execute(
        select(Exception_, Schedule, Vehicle)
        .join(Schedule, Exception_.schedule_id == Schedule.schedule_id)
        .outerjoin(Vehicle, Exception_.vehicle_id == Vehicle.vehicle_id)
        # `deleted_at IS NULL` là BẮT BUỘC từ khi có xoá mềm ngoại lệ (việc 5):
        # ngoại lệ đã xoá vẫn giữ nguyên `status` cũ (analyzing/awaiting_decision),
        # thiếu điều kiện này thì detect_conflict còn gộp ngoại lệ MỚI vào chung
        # nhóm với một ngoại lệ đã bị xoá — bug thật, phát hiện lúc test trên
        # production.
        .where(Exception_.status.in_(ACTIVE_STATUSES), Exception_.deleted_at.is_(None))
    ).all()

    result = []
    for exc, schedule, vehicle in rows:
        if exclude_id is not None and exc.exception_id == exclude_id:
            continue
        impact = db.execute(
            select(ImpactAnalysis).where(ImpactAnalysis.exception_id == exc.exception_id)
        ).scalar_one_or_none()
        affected_stop_ids = [s["stop_id"] for s in (impact.affected_stops or [])] if impact else []
        result.append(
            {
                "exception_id": str(exc.exception_id),
                "vehicle_id": exc.vehicle_id,
                "driver_name": vehicle.driver_name if vehicle else None,
                "schedule_id": str(exc.schedule_id),
                "affected_stop_ids": affected_stop_ids,
                "sub_type": exc.sub_type,
                "severity": exc.severity,
                "area": exc.area,
                "reported_at": exc.reported_at,
            }
        )
    return result


def _option_to_dict(option: Option) -> dict:
    return {
        "option_id": str(option.option_id),
        "description": option.description,
        "cost_estimate": float(option.cost_estimate) if option.cost_estimate is not None else None,
        "time_estimate_minutes": option.time_estimate_minutes,
        "sla_risk_remaining": float(option.sla_risk_remaining) if option.sla_risk_remaining is not None else None,
        "llm_explanation": option.llm_explanation,
        "score": float(option.score) if option.score is not None else None,
        "rank": option.rank,
    }


@router.post("", response_model=ExceptionResponse, status_code=status.HTTP_201_CREATED)
def create_exception(
    payload: ExceptionCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = db.get(Schedule, payload.schedule_id)
    if schedule is None or str(schedule.company_id) != current_user["company_id"] or schedule.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy chuyến")

    try:
        classification = classify_sub_type(payload.exception_group, payload.answer_key, payload.customer_request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    sub_type = classification["sub_type"]
    reported_at = datetime.now(timezone.utc)
    # `stops[].eta`/`sla_deadline` là giờ địa phương (naive) theo companies.timezone
    # (mục 4) — dùng datetime naive khi so khớp, KHÔNG dùng datetime UTC-aware
    # (khác kiểu, Python không trừ được offset-naive với offset-aware).
    now_local = datetime.now()

    impact = analyze_impact(
        stops=schedule.stops or [],
        delay_minutes=payload.delay_minutes,
        from_stop_order=payload.from_stop_order,
        to_stop_order=payload.to_stop_order,
        shift_date=schedule.shift_date,
        now=now_local,
    )

    rule_context = {
        "departure_delay_min": payload.departure_delay_min,
        "driver_contact_lost_min": payload.driver_contact_lost_min,
        "estimated_traffic_duration_min": payload.estimated_traffic_duration_min,
        "is_repeat_delivery": payload.is_repeat_delivery,
        "has_time_conflict": payload.has_time_conflict,
        "new_location_distance_km": payload.new_location_distance_km,
        "estimated_repair_min": payload.estimated_repair_min,
        "has_injury": payload.has_injury,
        # `late_departure` gộp 2 trạng thái từ 2026-09-08 nên rule engine phải
        # biết trạng thái nào để đọc đúng con số phút (ước tính vs thực tế) —
        # xem rule_engine._base_and_escalation.
        "departure_status": payload.departure_status,
        "estimated_departure_delay_min": payload.estimated_departure_delay_min,
        **impact,
    }
    severity = calculate_severity(sub_type, rule_context)

    exception = Exception_(
        company_id=current_user["company_id"],
        schedule_id=schedule.schedule_id,
        exception_group=payload.exception_group,
        sub_type=sub_type,
        severity=severity,
        vehicle_id=schedule.vehicle_id,
        area=payload.area,
        # CHỈ ghi chú dispatcher tự gõ — đúng nhãn UI "Ghi chú thêm (không dùng
        # để phân loại)". Câu mô tả do rule engine sinh (depot_on_time/
        # has_injury) đã bỏ: hai tín hiệu đó nay vào thẳng CONTEXT dưới dạng
        # structured field (option_generator.py), kể lại bằng lời ở đây chỉ tạo
        # thêm một nguồn sự thật thứ hai có thể lệch pha sau khi dispatcher sửa.
        description=payload.description or None,
        customer_accepted_delay_min=payload.customer_accepted_delay_min,
        input_context=_input_context(payload),
        status="pending",
        reported_by=current_user["user_id"],
        reported_at=reported_at,
    )
    db.add(exception)
    db.flush()

    db.add(ImpactAnalysis(exception_id=exception.exception_id, affected_stops=impact["affected_stops"]))

    vehicle = db.get(Vehicle, schedule.vehicle_id)
    new_exc_dict = {
        "exception_id": str(exception.exception_id),
        "vehicle_id": exception.vehicle_id,
        "driver_name": vehicle.driver_name if vehicle else None,
        "schedule_id": str(exception.schedule_id),
        "affected_stop_ids": [s["stop_id"] for s in impact["affected_stops"]],
        "sub_type": sub_type,
        "severity": severity,
        "area": exception.area,
        "reported_at": reported_at,
    }
    active_exceptions = _active_exceptions_as_dicts(db, exclude_id=exception.exception_id)
    nearest_fn = lambda e, top_n: nearest_available_vehicles(db, current_user["company_id"], e, top_n)  # noqa: E731
    mode, conflicting, signals = detect_conflict(new_exc_dict, active_exceptions, nearest_available_vehicles_fn=nearest_fn)

    if mode == "combined" and conflicting is not None:
        existing_exc = db.get(Exception_, conflicting["exception_id"])
        if existing_exc.group_id is not None:
            group = db.get(ExceptionGroup, existing_exc.group_id)
            group.exception_ids = list(group.exception_ids) + [exception.exception_id]
        else:
            group = ExceptionGroup(
                company_id=current_user["company_id"],
                exception_ids=[existing_exc.exception_id, exception.exception_id],
                mode="combined",
            )
            db.add(group)
            db.flush()
            existing_exc.group_id = group.group_id
        exception.group_id = group.group_id

        # Thành viên có sẵn (existing_exc) có thể còn 1 job 'analyze_exception'
        # tạo TRƯỚC khi bị gộp nhóm mà worker chưa kịp xử lý — nếu để nguyên,
        # job đó chạy độc lập và sinh ra 1 phương án ngoài luồng, phá vỡ đúng
        # tinh thần "1 quyết định phối hợp duy nhất" (mục 5.3, 10). Huỷ mọi job
        # còn dở của TOÀN BỘ thành viên nhóm (trừ job mới sắp tạo cho combined
        # mode) trước khi tiếp tục.
        db.execute(
            update(BackgroundJob)
            .where(BackgroundJob.exception_id.in_(group.exception_ids), BackgroundJob.status.in_(("pending", "running")))
            .values(status="failed", error="Đã gộp vào nhóm combined mode, xem job analyze_group của nhóm thay thế")
        )
        job = BackgroundJob(company_id=current_user["company_id"], exception_id=exception.exception_id, job_type="analyze_group")
    else:
        job = BackgroundJob(company_id=current_user["company_id"], exception_id=exception.exception_id, job_type="analyze_exception")

    exception.status = "analyzing"
    db.add(job)

    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="create_exception",
            entity_type="exception",
            entity_id=exception.exception_id,
            detail={"sub_type": sub_type, "severity": severity, "conflict_mode": mode, "conflict_signals": signals},
        )
    )

    db.commit()
    db.refresh(exception)
    return exception


@router.get("", response_model=list[ExceptionResponse])
def list_exceptions(
    status_filter: "str | None" = None,
    severity_filter: "str | None" = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Exception_).where(Exception_.deleted_at.is_(None))
    if status_filter:
        # Nhận cả danh sách ngăn cách bằng dấu phẩy — trang Lịch sử cần lấy
        # cùng lúc "awaiting_outcome" và "resolved" (mọi ngoại lệ đã có quyết
        # định) trong 1 lần gọi. 1 giá trị đơn vẫn chạy y như trước.
        wanted = [v.strip() for v in status_filter.split(",") if v.strip()]
        stmt = stmt.where(Exception_.status.in_(wanted))
    if severity_filter:
        stmt = stmt.where(Exception_.severity == severity_filter)
    stmt = stmt.order_by(Exception_.reported_at.desc())
    return db.execute(stmt).scalars().all()


@router.get("/groups/{group_id}")
def get_exception_group(
    group_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = db.get(ExceptionGroup, group_id)
    if group is None or str(group.company_id) != current_user["company_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy nhóm {group_id}")

    members = db.execute(
        select(Exception_).where(Exception_.exception_id.in_(group.exception_ids), Exception_.deleted_at.is_(None))
    ).scalars().all()
    options = db.execute(select(Option).where(Option.group_id == group.group_id).order_by(Option.rank)).scalars().all()
    job = db.execute(
        select(BackgroundJob)
        .where(BackgroundJob.exception_id.in_(group.exception_ids), BackgroundJob.job_type == "analyze_group")
        .order_by(BackgroundJob.created_at.desc())
    ).scalars().first()
    return {
        "group_id": str(group.group_id),
        "mode": group.mode,
        "status": group.status,
        "exceptions": [
            {
                **ExceptionResponse.model_validate(m).model_dump(mode="json"),
                "reported_at": m.reported_at.isoformat() if m.reported_at else None,
            }
            for m in members
        ],
        "options": [_option_to_dict(o) for o in options],
        "job": {"job_id": str(job.job_id), "status": job.status, "error": job.error} if job else None,
        # Nhóm cũng cần quyết định/kết quả: ExceptionDetail chuyển hướng mọi
        # ngoại lệ có group_id sang trang này, nên đây là đường DUY NHẤT để
        # nhập/xem kết quả thực tế của ngoại lệ đã gộp nhóm.
        **_group_decision_bundle(db, group),
    }


@router.post("/{exception_id}/manual-option", status_code=status.HTTP_201_CREATED)
def create_manual_option(
    exception_id: str,
    payload: ManualOptionCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fallback mục 8: dispatcher tự nhập phương án khi LLM lỗi/hết hạn mức
    (hoặc đơn giản là muốn thêm phương án riêng ngoài các phương án AI đã sinh)."""
    exc = db.get(Exception_, exception_id)
    if exc is None or str(exc.company_id) != current_user["company_id"] or exc.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy ngoại lệ {exception_id}")

    option = Option(
        exception_id=exc.exception_id,
        description=payload.description,
        cost_estimate=payload.cost_estimate,
        time_estimate_minutes=payload.time_estimate_minutes,
    )
    db.add(option)

    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="create_manual_option",
            entity_type="exception",
            entity_id=exc.exception_id,
            detail={"description": payload.description},
        )
    )
    db.commit()
    db.refresh(option)
    return _option_to_dict(option)


def _user_name(db: Session, user_id) -> "str | None":
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return (user.full_name or user.email) if user is not None else None


def _bundle_from_decision(db: Session, decision: "Decision | None") -> dict:
    """Quyết định đã xác nhận + phương án đã chọn + kết quả thực tế (việc 3,
    2026-09-04).

    Ghép sẵn ở BACKEND thay vì để trang chi tiết gọi thêm 3-4 API lẻ
    (decision -> option -> outcome -> tên người dùng).
    """
    if decision is None:
        return {"decision": None, "outcome": None}

    option = db.get(Option, decision.selected_option_id)
    outcome = db.execute(
        select(Outcome).where(Outcome.decision_id == decision.decision_id)
    ).scalars().first()

    return {
        "decision": {
            "decision_id": str(decision.decision_id),
            "confirmed_at": decision.confirmed_at.isoformat(),
            "confirmed_by_name": _user_name(db, decision.confirmed_by),
            "override_note": decision.override_note,
            "is_group_decision": decision.group_id is not None,
            "selected_option": _option_to_dict(option) if option is not None else None,
        },
        # Dùng CHUNG helper với api/decisions.py thay vì tự dựng dict ở đây —
        # bản dựng tay cũ đã bỏ sót `resolution_type`/`editable` ngay lần đầu
        # thêm field, đúng kiểu lỗi mà việc gộp 1 chỗ tránh được.
        "outcome": outcome_to_dict(db, outcome, recorded_by_name=_user_name(db, outcome.recorded_by))
        if outcome is not None
        else None,
    }


def _decision_bundle(db: Session, exc: Exception_) -> dict:
    """Ngoại lệ trong nhóm combined mode dùng chung 1 quyết định gắn với
    `group_id`, không phải `exception_id` — phải tra cả 2 chiều."""
    if exc.group_id is not None:
        stmt = select(Decision).where(
            (Decision.exception_id == exc.exception_id) | (Decision.group_id == exc.group_id)
        )
    else:
        stmt = select(Decision).where(Decision.exception_id == exc.exception_id)
    return _bundle_from_decision(db, db.execute(stmt.order_by(Decision.confirmed_at.desc())).scalars().first())


def _group_decision_bundle(db: Session, group: ExceptionGroup) -> dict:
    return _bundle_from_decision(
        db,
        db.execute(
            select(Decision).where(Decision.group_id == group.group_id).order_by(Decision.confirmed_at.desc())
        ).scalars().first(),
    )


@router.get("/{exception_id}")
def get_exception_detail(
    exception_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exc = db.get(Exception_, exception_id)
    if exc is None or str(exc.company_id) != current_user["company_id"] or exc.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy ngoại lệ {exception_id}")

    impact = db.execute(select(ImpactAnalysis).where(ImpactAnalysis.exception_id == exc.exception_id)).scalar_one_or_none()
    job = db.execute(
        select(BackgroundJob).where(BackgroundJob.exception_id == exc.exception_id).order_by(BackgroundJob.created_at.desc())
    ).scalars().first()
    # exception thuộc combined mode: options gắn vào group_id, không phải
    # exception_id riêng lẻ (mục 5.3, 19.2) — vẫn hiển thị ở đây để dispatcher
    # xem trực tiếp từ màn hình 1 trong 2 exception member cũng thấy được.
    options = db.execute(
        select(Option).where(
            (Option.exception_id == exc.exception_id) | (Option.group_id == exc.group_id if exc.group_id else False)
        ).order_by(Option.rank)
    ).scalars().all()

    return {
        **ExceptionResponse.model_validate(exc).model_dump(mode="json"),
        "reported_at": exc.reported_at.isoformat() if exc.reported_at else None,
        "impact_analysis": {
            "affected_stops": impact.affected_stops,
            "total_cost_estimate": float(impact.total_cost_estimate) if impact and impact.total_cost_estimate is not None else None,
        } if impact else None,
        "job": {"job_id": str(job.job_id), "status": job.status, "error": job.error} if job else None,
        "options": [_option_to_dict(o) for o in options],
        **_decision_bundle(db, exc),
    }


def _load_editable_exception(exception_id: str, current_user: dict, db: Session) -> Exception_:
    """Ngoại lệ được phép sửa/xoá: đúng công ty, chưa soft-delete, và CHƯA có
    kết quả thực tế.

    NỚI TỚI `awaiting_outcome` (Quyết định 4, 2026-09-08). Trước đó chặn từ
    `awaiting_outcome` vì lý do KỸ THUẬT: lúc đó đã có `decisions` trỏ vào 1
    `option`, nên `_reset_analysis` xoá option là vỡ khoá ngoại, còn xoá ngoại
    lệ thì để lại quyết định mồ côi vẫn được KPI đếm. Lý do đó nay xử lý thẳng
    bằng `_discard_pending_decision()` (huỷ luôn quyết định chưa có kết quả)
    thay vì cấm người dùng — dispatcher nhập nhầm rồi lỡ bấm xác nhận phương án
    là chuyện có thật, bắt họ nhập một kết quả giả để "hoàn tất" một ngoại lệ
    không có thật còn làm hỏng KPI nặng hơn.

    RANH GIỚI CỨNG vẫn là `resolved`: đã có `outcomes` thì thôi. `Decision`/
    `Option` không có `deleted_at` nên phải xoá cứng, mà `outcomes.decision_id`
    là FK NOT NULL — xoá quyết định của case đã resolved sẽ kéo mất luôn kết
    quả thực tế, tức mất số liệu KPI thật.

    ĐỪNG NHẦM với `outcome.editable` (Gap 1, api/decisions.py): cái đó nói
    outcome còn sửa được không SAU khi đã resolved — hai entity khác nhau."""
    exc = db.get(Exception_, exception_id)
    if exc is None or str(exc.company_id) != current_user["company_id"] or exc.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy ngoại lệ {exception_id}")
    if exc.status == "resolved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngoại lệ đã xử lý xong (đã có kết quả thực tế) — không sửa/xoá được nữa để giữ đúng số liệu KPI đã chốt.",
        )
    return exc


def _discard_pending_decision(db: Session, exc: Exception_) -> None:
    """Xoá cứng quyết định CHƯA có kết quả thực tế của 1 ngoại lệ (và của cả
    nhóm nếu nó thuộc combined mode), kèm `resource_locks` đang giữ chỗ.

    Gọi TRƯỚC `_reset_analysis()` hoặc trước khi xoá ngoại lệ: quyết định trỏ
    vào 1 `option`, mà cả 2 đường đó đều xoá option — không dọn quyết định
    trước thì vỡ khoá ngoại.

    An toàn với KPI: chỉ đụng quyết định KHÔNG có `outcomes` nào trỏ vào.
    Trường hợp có outcome đã bị `_load_editable_exception` chặn từ trước
    (status = resolved); nhánh kiểm tra ở đây là lớp chặn thứ hai cho các
    đường gọi khác (vd cascade khi xoá chuyến/điểm giao).
    """
    scope_ids = [exc.exception_id]
    if exc.group_id is not None:
        group = db.get(ExceptionGroup, exc.group_id)
        if group is not None:
            scope_ids = list(group.exception_ids)

    conditions = [Decision.exception_id.in_(scope_ids)]
    if exc.group_id is not None:
        conditions.append(Decision.group_id == exc.group_id)

    for decision in db.execute(select(Decision).where(or_(*conditions))).scalars().all():
        has_outcome = db.execute(
            select(Outcome).where(Outcome.decision_id == decision.decision_id)
        ).scalars().first()
        if has_outcome is not None:
            continue
        db.delete(decision)

    db.query(ResourceLock).filter(ResourceLock.exception_id.in_(scope_ids)).delete(synchronize_session=False)


def cascade_delete_exception_rows(db: Session, exceptions: list, current_user: dict, reason: str) -> list:
    """Xoá mềm đúng những ngoại lệ được truyền vào, kèm dọn quyết định treo /
    phương án / job còn dở (Quyết định 4, 2026-09-08). Trả về list exception_id.

    Dùng khi người dùng đụng vào chuyến/điểm giao mà ngoại lệ đang dựa vào:
    phân tích của nó gắn với dữ liệu vừa biến mất (`impact_analysis.
    affected_stops` trỏ vào `stop_id` không còn tồn tại), giữ lại chỉ sinh ra
    phương án nói về những đơn không có thật.

    Ngoại lệ `resolved` bị BỎ QUA hoàn toàn (không xoá, không báo lỗi): đó là
    số liệu KPI đã chốt, và xoá nó sẽ kéo theo `decisions`/`outcomes` — xem
    `_load_editable_exception`. Chuyến đã xoá mềm thì ngoại lệ resolved của nó
    vẫn tra cứu lịch sử được bình thường.
    """
    now = datetime.now(timezone.utc)
    deleted = []
    for exc in exceptions:
        if exc.deleted_at is not None or exc.status == "resolved":
            continue
        status_before = exc.status
        _discard_pending_decision(db, exc)
        for opt in db.execute(select(Option).where(Option.exception_id == exc.exception_id)).scalars().all():
            db.delete(opt)
        db.execute(
            update(BackgroundJob)
            .where(BackgroundJob.exception_id == exc.exception_id, BackgroundJob.status.in_(("pending", "running")))
            .values(status="failed", error=reason)
        )
        exc.deleted_at = now
        exc.group_id = None
        deleted.append(exc.exception_id)
        db.add(
            AuditLog(
                company_id=current_user["company_id"],
                user_id=current_user["user_id"],
                action="cascade_delete_exception",
                entity_type="exception",
                entity_id=exc.exception_id,
                detail={"reason": reason, "status_before": status_before},
            )
        )
    return deleted


def cascade_delete_exceptions_of_schedules(db: Session, schedule_ids: list, current_user: dict, reason: str) -> list:
    """Bản tiện dụng của `cascade_delete_exception_rows` cho trường hợp xoá cả
    chuyến: tự tìm mọi ngoại lệ chưa xong đang trỏ vào các chuyến đó."""
    if not schedule_ids:
        return []
    rows = db.execute(
        select(Exception_).where(
            Exception_.schedule_id.in_(schedule_ids),
            Exception_.deleted_at.is_(None),
            Exception_.status != "resolved",
        )
    ).scalars().all()
    return cascade_delete_exception_rows(db, rows, current_user, reason)


def _reset_analysis(db: Session, exc: Exception_, current_user: dict) -> BackgroundJob:
    """Huỷ job đang dở + xoá phương án cũ của ngoại lệ (hoặc của cả nhóm nếu
    nó thuộc combined mode) rồi tạo job phân tích mới. Bắt buộc sau khi sửa:
    phương án cũ được sinh từ thông tin SAI, để nguyên là dispatcher xác nhận
    nhầm phương án dựa trên dữ liệu đã bị thay."""
    if exc.group_id is not None:
        group = db.get(ExceptionGroup, exc.group_id)
        scope_ids = list(group.exception_ids)
        for opt in db.execute(select(Option).where(Option.group_id == group.group_id)).scalars().all():
            db.delete(opt)
        job_type = "analyze_group"
    else:
        scope_ids = [exc.exception_id]
        job_type = "analyze_exception"

    for opt in db.execute(select(Option).where(Option.exception_id.in_(scope_ids))).scalars().all():
        db.delete(opt)

    db.execute(
        update(BackgroundJob)
        .where(BackgroundJob.exception_id.in_(scope_ids), BackgroundJob.status.in_(("pending", "running")))
        .values(status="failed", error="Ngoại lệ đã được sửa, job này phân tích trên dữ liệu cũ — xem job mới thay thế")
    )

    # Cả nhóm phải quay lại 'analyzing': phương án phối hợp của nhóm vừa bị
    # xoá nên KHÔNG thành viên nào còn phương án để xác nhận.
    for member in db.execute(select(Exception_).where(Exception_.exception_id.in_(scope_ids))).scalars():
        member.status = "analyzing"

    job = BackgroundJob(company_id=current_user["company_id"], exception_id=exc.exception_id, job_type=job_type)
    db.add(job)
    return job


@router.put("/{exception_id}", response_model=ExceptionResponse)
def update_exception(
    exception_id: str,
    payload: ExceptionUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sửa lại thông tin đã nhập của 1 ngoại lệ chưa xử lý xong (việc 5).

    Chạy lại ĐÚNG luồng lúc tạo (classify_sub_type -> analyze_impact ->
    calculate_severity) trên `schedule` cũ — `schedule_id` KHÔNG đổi được.
    KHÔNG chạy lại `detect_conflict`: việc gom/tách nhóm là quyết định khác,
    sửa thông tin không nên âm thầm kéo ngoại lệ ra/vào nhóm sau lưng
    dispatcher — nhóm hiện tại giữ nguyên, chỉ phương án được sinh lại.
    """
    exc = _load_editable_exception(exception_id, current_user, db)
    # Có thể đang ở `awaiting_outcome`: quyết định cũ được chốt dựa trên đúng
    # thông tin sắp bị sửa nên giữ lại là vô nghĩa — và `_reset_analysis` bên
    # dưới sẽ xoá đúng option mà nó đang trỏ vào.
    _discard_pending_decision(db, exc)

    schedule = db.get(Schedule, exc.schedule_id)
    if schedule is None or schedule.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy chuyến của ngoại lệ này")

    try:
        classification = classify_sub_type(payload.exception_group, payload.answer_key, payload.customer_request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    sub_type = classification["sub_type"]
    # Cùng lý do như create_exception: stops[].eta là giờ địa phương (naive).
    now_local = datetime.now()
    impact = analyze_impact(
        stops=schedule.stops or [],
        delay_minutes=payload.delay_minutes,
        from_stop_order=payload.from_stop_order,
        to_stop_order=payload.to_stop_order,
        shift_date=schedule.shift_date,
        now=now_local,
    )
    rule_context = {
        "departure_delay_min": payload.departure_delay_min,
        "driver_contact_lost_min": payload.driver_contact_lost_min,
        "estimated_traffic_duration_min": payload.estimated_traffic_duration_min,
        "is_repeat_delivery": payload.is_repeat_delivery,
        "has_time_conflict": payload.has_time_conflict,
        "new_location_distance_km": payload.new_location_distance_km,
        "estimated_repair_min": payload.estimated_repair_min,
        "has_injury": payload.has_injury,
        # `late_departure` gộp 2 trạng thái từ 2026-09-08 nên rule engine phải
        # biết trạng thái nào để đọc đúng con số phút (ước tính vs thực tế) —
        # xem rule_engine._base_and_escalation.
        "departure_status": payload.departure_status,
        "estimated_departure_delay_min": payload.estimated_departure_delay_min,
        **impact,
    }
    severity_before = exc.severity
    severity = calculate_severity(sub_type, rule_context)

    exc.exception_group = payload.exception_group
    exc.sub_type = sub_type
    exc.severity = severity
    exc.area = payload.area
    # Cùng lý do như create_exception: description chỉ còn ghi chú dispatcher
    # gõ. Với ngoại lệ CŨ, lần sửa này cũng là lúc câu note rule engine từng
    # nối vào biến mất khỏi description — đúng ý muốn, vì tín hiệu thật đã nằm
    # ở input_context/CONTEXT.
    exc.description = payload.description or None
    exc.customer_accepted_delay_min = payload.customer_accepted_delay_min
    exc.input_context = _input_context(payload)

    existing_impact = db.execute(
        select(ImpactAnalysis).where(ImpactAnalysis.exception_id == exc.exception_id)
    ).scalar_one_or_none()
    if existing_impact is None:
        db.add(ImpactAnalysis(exception_id=exc.exception_id, affected_stops=impact["affected_stops"]))
    else:
        existing_impact.affected_stops = impact["affected_stops"]

    _reset_analysis(db, exc, current_user)

    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="update_exception",
            entity_type="exception",
            entity_id=exc.exception_id,
            detail={"sub_type": sub_type, "severity_before": severity_before, "severity_after": severity},
        )
    )
    db.commit()
    db.refresh(exc)
    return exc


@router.delete("/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exception(
    exception_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Xoá mềm 1 ngoại lệ nhập nhầm (việc 5). Chỉ khi CHƯA resolved."""
    exc = _load_editable_exception(exception_id, current_user, db)
    _discard_pending_decision(db, exc)

    exc.deleted_at = datetime.now(timezone.utc)
    # Job/phương án còn dở của ngoại lệ vừa xoá là rác — huỷ luôn, tránh
    # worker chạy tiếp rồi ghi phương án cho 1 ngoại lệ không còn tồn tại.
    db.execute(
        update(BackgroundJob)
        .where(BackgroundJob.exception_id == exc.exception_id, BackgroundJob.status.in_(("pending", "running")))
        .values(status="failed", error="Ngoại lệ đã bị xoá")
    )

    # Gỡ khỏi nhóm combined mode. `exception_groups.exception_ids` là nguồn duy
    # nhất mà option_generator/job_processor/decisions đọc để biết thành viên
    # nhóm — để nguyên id đã xoá trong đó là phương án phối hợp vẫn tiếp tục
    # được sinh quanh 1 ngoại lệ không còn tồn tại.
    if exc.group_id is not None:
        group = db.get(ExceptionGroup, exc.group_id)
        remaining = [i for i in group.exception_ids if i != exc.exception_id]
        group.exception_ids = remaining
        exc.group_id = None

        survivors = db.execute(
            select(Exception_).where(Exception_.exception_id.in_(remaining), Exception_.deleted_at.is_(None))
        ).scalars().all() if remaining else []

        # Nhóm chỉ còn 1 thành viên thì không còn là "quyết định phối hợp" nữa
        # — tách nó ra chạy phân tích đơn lẻ lại từ đầu, vì phương án cũ của
        # nhóm được sinh dựa trên cả ngoại lệ vừa bị xoá.
        if len(survivors) <= 1:
            for opt in db.execute(select(Option).where(Option.group_id == group.group_id)).scalars().all():
                db.delete(opt)
            for survivor in survivors:
                survivor.group_id = None
                _reset_analysis(db, survivor, current_user)

    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="delete_exception",
            entity_type="exception",
            entity_id=exc.exception_id,
            detail={"sub_type": exc.sub_type, "severity": exc.severity},
        )
    )
    db.commit()
    return None


# Số lần dispatcher được bấm "Thử lại phân tích AI" cho 1 ngoại lệ (việc 4,
# 2026-09-04). Đếm ở BACKEND qua `background_jobs` chứ không chỉ ẩn nút:
# ẩn nút chỉ chặn được người dùng bình thường, gọi thẳng API vẫn lách được và
# mỗi lần thử là 1-3 lượt gọi LLM thật, ăn vào hạn mức ngày của công ty.
MAX_MANUAL_RETRIES = 2
_RETRY_JOB_TYPES = ("analyze_exception", "analyze_group")


@router.post("/{exception_id}/retry-analysis", status_code=status.HTTP_202_ACCEPTED)
def retry_analysis(
    exception_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Chạy lại job phân tích AI cho 1 ngoại lệ mà job trước đã lỗi (việc 4).

    Chỉ cho khi ngoại lệ CHƯA có quyết định (dùng chung
    `_load_editable_exception`) — đã chốt phương án rồi thì phân tích lại
    không còn ý nghĩa, mà lại xoá mất phương án đang được quyết định tham
    chiếu.
    """
    exc = _load_editable_exception(exception_id, current_user, db)

    last_job = db.execute(
        select(BackgroundJob)
        .where(BackgroundJob.exception_id == exc.exception_id, BackgroundJob.job_type.in_(_RETRY_JOB_TYPES))
        .order_by(BackgroundJob.created_at.desc())
    ).scalars().first()
    if last_job is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngoại lệ này chưa từng chạy phân tích AI nên không có gì để thử lại.",
        )
    if last_job.status in ("pending", "running"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đang có một lượt phân tích chạy dở — chờ nó xong đã.",
        )

    used = db.execute(
        select(func.count())
        .select_from(BackgroundJob)
        .where(
            BackgroundJob.exception_id == exc.exception_id,
            BackgroundJob.job_type.in_(_RETRY_JOB_TYPES),
            BackgroundJob.result["manual_retry"].as_boolean().is_(True),
        )
    ).scalar_one()
    if used >= MAX_MANUAL_RETRIES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Đã thử lại phân tích AI {used}/{MAX_MANUAL_RETRIES} lần cho ngoại lệ này. "
                "Vui lòng dùng \"Tự nhập phương án khác\" để xử lý thủ công."
            ),
        )

    job = _reset_analysis(db, exc, current_user)
    # Đánh dấu ngay lúc tạo để lần đếm sau thấy được, kể cả khi job này lại lỗi.
    job.result = {"manual_retry": True}

    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="retry_analysis",
            entity_type="exception",
            entity_id=exc.exception_id,
            detail={"attempt": used + 1, "max": MAX_MANUAL_RETRIES, "previous_error": last_job.error},
        )
    )
    db.commit()
    db.refresh(job)
    return {
        "job_id": str(job.job_id),
        "job_type": job.job_type,
        "retries_used": used + 1,
        "retries_left": MAX_MANUAL_RETRIES - (used + 1),
    }
