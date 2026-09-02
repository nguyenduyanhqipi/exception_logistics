from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.conflict_detector import detect_conflict
from core.impact_analyzer import analyze_impact
from core.rule_engine import calculate_severity, classify_sub_type
from middleware.auth import get_current_user
from middleware.tenant import get_db
from models import (
    AuditLog,
    BackgroundJob,
    Exception_,
    ExceptionGroup,
    ImpactAnalysis,
    Option,
    Schedule,
    Vehicle,
)
from schemas.exception import ExceptionCreate, ExceptionResponse, ManualOptionCreate

router = APIRouter(prefix="/api/exceptions", tags=["exceptions"])

ACTIVE_STATUSES = ("pending", "analyzing", "awaiting_decision")


def _active_exceptions_as_dicts(db: Session, exclude_id=None) -> list[dict]:
    rows = db.execute(
        select(Exception_, Schedule, Vehicle)
        .join(Schedule, Exception_.schedule_id == Schedule.schedule_id)
        .outerjoin(Vehicle, Exception_.vehicle_id == Vehicle.vehicle_id)
        .where(Exception_.status.in_(ACTIVE_STATUSES))
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
    # nearest_available_vehicles_fn=None ở Giai đoạn 5 (chưa có geocoder,
    # Giai đoạn 7) -> tín hiệu resource_contention tạm thời không kích hoạt
    # được, các tín hiệu same_vehicle/same_driver/same_stop vẫn hoạt động đủ.
    mode, conflicting, signals = detect_conflict(new_exc_dict, active_exceptions, nearest_available_vehicles_fn=None)

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
        stmt = stmt.where(Exception_.status == status_filter)
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

    members = db.execute(select(Exception_).where(Exception_.exception_id.in_(group.exception_ids))).scalars().all()
    return {
        "group_id": str(group.group_id),
        "mode": group.mode,
        "status": group.status,
        "exceptions": [ExceptionResponse.model_validate(m).model_dump(mode="json") for m in members],
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
    return {
        "option_id": str(option.option_id),
        "description": option.description,
        "cost_estimate": float(option.cost_estimate) if option.cost_estimate is not None else None,
        "time_estimate_minutes": option.time_estimate_minutes,
    }


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

    return {
        **ExceptionResponse.model_validate(exc).model_dump(mode="json"),
        "impact_analysis": {
            "affected_stops": impact.affected_stops,
            "total_cost_estimate": float(impact.total_cost_estimate) if impact and impact.total_cost_estimate is not None else None,
        } if impact else None,
        "job": {"job_id": str(job.job_id), "status": job.status} if job else None,
    }
