from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

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
    # Ghi chú NGƯỜI DÙNG gõ, tách khỏi `exceptions.description` (đã bị nối
    # thêm `description_note` do rule engine sinh) để form sửa nạp lại đúng
    # phần người dùng viết, không nối chồng note cũ.
    "description",
    "depot_on_time",
    "has_injury",
    "from_stop_order",
    "to_stop_order",
    "delay_minutes",
    "departure_delay_min",
    "driver_contact_lost_min",
    "estimated_traffic_duration_min",
    "is_repeat_delivery",
    "new_address_distance_km",
    "has_time_conflict",
    "new_location_distance_km",
    "estimated_repair_min",
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
        classification = classify_sub_type(
            payload.exception_group, payload.answer_key, payload.depot_on_time, payload.has_injury
        )
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
        "new_address_distance_km": payload.new_address_distance_km,
        "has_time_conflict": payload.has_time_conflict,
        "new_location_distance_km": payload.new_location_distance_km,
        "estimated_repair_min": payload.estimated_repair_min,
        "has_injury": payload.has_injury,
        **impact,
    }
    severity = calculate_severity(sub_type, rule_context)

    description_parts = [p for p in [payload.description, classification["description_note"]] if p]

    exception = Exception_(
        company_id=current_user["company_id"],
        schedule_id=schedule.schedule_id,
        exception_group=payload.exception_group,
        sub_type=sub_type,
        severity=severity,
        vehicle_id=schedule.vehicle_id,
        area=payload.area,
        description=" | ".join(description_parts) if description_parts else None,
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
        "outcome": {
            "outcome_id": str(outcome.outcome_id),
            "delivered_on_time": outcome.delivered_on_time,
            "delay_minutes": outcome.delay_minutes,
            "actual_cost": float(outcome.actual_cost) if outcome.actual_cost is not None else None,
            "notes": outcome.notes,
            "recorded_at": outcome.recorded_at.isoformat(),
            "recorded_by_name": _user_name(db, outcome.recorded_by),
        } if outcome is not None else None,
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
    quyết định nào được xác nhận.

    Chặn từ `awaiting_outcome` chứ không phải chỉ `resolved` (từ 2026-09-04,
    xem api/decisions.py): `awaiting_outcome` nghĩa là dispatcher ĐÃ chốt
    phương án, `decisions.selected_option_id` đã trỏ vào 1 option. Cho sửa lúc
    này thì `_reset_analysis` sẽ xoá đúng option đang bị quyết định tham chiếu
    (vỡ khoá ngoại), còn cho xoá thì để lại 1 quyết định mồ côi vẫn được KPI
    đếm. Muốn đổi phương án đã chốt là nghiệp vụ khác, không phải "sửa thông
    tin nhập sai"."""
    exc = db.get(Exception_, exception_id)
    if exc is None or str(exc.company_id) != current_user["company_id"] or exc.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy ngoại lệ {exception_id}")
    if exc.status == "resolved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngoại lệ đã xử lý xong (đã có kết quả thực tế) — không sửa/xoá được nữa để giữ đúng số liệu KPI đã chốt.",
        )
    if exc.status == "awaiting_outcome":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngoại lệ đã xác nhận phương án xử lý — không sửa/xoá được nữa, hãy nhập kết quả thực tế để hoàn tất.",
        )
    return exc


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

    schedule = db.get(Schedule, exc.schedule_id)
    if schedule is None or schedule.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy chuyến của ngoại lệ này")

    try:
        classification = classify_sub_type(
            payload.exception_group, payload.answer_key, payload.depot_on_time, payload.has_injury
        )
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
        "new_address_distance_km": payload.new_address_distance_km,
        "has_time_conflict": payload.has_time_conflict,
        "new_location_distance_km": payload.new_location_distance_km,
        "estimated_repair_min": payload.estimated_repair_min,
        "has_injury": payload.has_injury,
        **impact,
    }
    severity_before = exc.severity
    severity = calculate_severity(sub_type, rule_context)

    # Không nối chồng `description_note` nếu nó đã nằm sẵn trong ghi chú (xảy
    # ra với ngoại lệ tạo trước khi có `input_context`: form sửa nạp lại cả
    # phần note đã nối lần trước).
    note = classification["description_note"]
    description_parts = [p for p in [payload.description] if p]
    if note and (not payload.description or note not in payload.description):
        description_parts.append(note)

    exc.exception_group = payload.exception_group
    exc.sub_type = sub_type
    exc.severity = severity
    exc.area = payload.area
    exc.description = " | ".join(description_parts) if description_parts else None
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
