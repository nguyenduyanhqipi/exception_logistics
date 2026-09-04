import uuid
from collections import OrderedDict
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.excel_parser import ExcelValidationError, parse_schedule_sheet
from middleware.auth import get_current_user
from middleware.tenant import get_db
from models import Exception_, Schedule, Vehicle
from schemas.schedule import ScheduleCreate, ScheduleCreateBody, ScheduleResponse, StopCreate

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _compute_planned_departure(arrival: time | None, loading_min: int | None) -> time | None:
    if arrival is None or loading_min is None:
        return None
    dt = datetime.combine(date.today(), arrival)
    return (dt + timedelta(minutes=loading_min)).time()


def _stop_to_dict(stop: StopCreate) -> dict:
    data = stop.model_dump(mode="json")
    data["stop_id"] = str(uuid.uuid4())
    return data


def _create_one_schedule(payload: ScheduleCreate, current_user: dict, db: Session) -> Schedule:
    existing = db.execute(
        select(Schedule).where(
            Schedule.vehicle_id == payload.vehicle_id,
            Schedule.shift_date == payload.shift_date,
            Schedule.shift_label == payload.shift_label,
            Schedule.trip_sequence == payload.trip_sequence,
            Schedule.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        _assert_not_locked_for_overwrite(db, existing)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Chuyến của xe {payload.vehicle_id} ngày {payload.shift_date} "
                f"{payload.shift_label} chuyến {payload.trip_sequence} đã tồn tại"
            ),
        )

    schedule = Schedule(
        company_id=current_user["company_id"],
        vehicle_id=payload.vehicle_id,
        shift_date=payload.shift_date,
        shift_label=payload.shift_label,
        trip_sequence=payload.trip_sequence,
        depot_arrival_time=payload.depot_arrival_time,
        depot_loading_duration_min=payload.depot_loading_duration_min,
        planned_departure_time=_compute_planned_departure(payload.depot_arrival_time, payload.depot_loading_duration_min),
        depot_address=payload.depot_address,
        stops=[_stop_to_dict(s) for s in sorted(payload.stops, key=lambda s: s.stop_order)],
        created_by=current_user["user_id"],
    )
    db.add(schedule)
    return schedule


@router.get("", response_model=list[ScheduleResponse])
def list_schedules(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Schedule).where(Schedule.deleted_at.is_(None)).order_by(Schedule.shift_date.desc())
    ).scalars().all()
    return rows


@router.post("", response_model=list[ScheduleResponse], status_code=status.HTTP_201_CREATED)
def create_schedules(
    payload: ScheduleCreateBody,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = payload if isinstance(payload, list) else [payload]
    created = [_create_one_schedule(item, current_user, db) for item in items]
    db.commit()
    for s in created:
        db.refresh(s)
    return created


@router.post("/{schedule_id}/stops", response_model=ScheduleResponse)
def add_or_update_stop(
    schedule_id: str,
    payload: StopCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = db.get(Schedule, schedule_id)
    if schedule is None or str(schedule.company_id) != current_user["company_id"] or schedule.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy chuyến {schedule_id}")

    stops = list(schedule.stops or [])
    existing_idx = next((i for i, s in enumerate(stops) if s["stop_order"] == payload.stop_order), None)
    new_stop = _stop_to_dict(payload)
    if existing_idx is not None:
        new_stop["stop_id"] = stops[existing_idx]["stop_id"]
        stops[existing_idx] = new_stop
    else:
        stops.append(new_stop)

    schedule.stops = sorted(stops, key=lambda s: s["stop_order"])
    db.commit()
    db.refresh(schedule)
    return schedule


def _row_to_stop_dict(r: dict) -> dict:
    return {
        "stop_id": str(uuid.uuid4()),
        "stop_order": r["stop_order"],
        "stop_type": r["stop_type"],
        "address": r["stop_address"],
        "area": r["stop_area"],
        "order_id": r["order_id"],
        "customer_name": r["customer_name"],
        "customer_phone": r["customer_phone"],
        "eta": r["eta"].isoformat() if r.get("eta") else None,
        "loading_duration_min": r.get("loading_duration_min"),
        "sla_deadline": r["sla_deadline"].isoformat() if r.get("sla_deadline") else None,
        "priority_tier": r["priority_tier"],
        "sla_penalty": float(r["sla_penalty"]) if r.get("sla_penalty") is not None else None,
        "volume_kg": float(r["volume_kg"]) if r.get("volume_kg") is not None else None,
        "cargo_type": r["cargo_type"],
        "notes": r.get("notes"),
    }


@router.post("/upload")
async def upload_schedules(
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await file.read()
    try:
        rows, _ = parse_schedule_sheet(content)
    except ExcelValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors})

    vehicle_ids = {r["vehicle_id"] for r in rows}
    active_vehicles = {
        v.vehicle_id
        for v in db.execute(
            select(Vehicle).where(Vehicle.vehicle_id.in_(vehicle_ids), Vehicle.status == "active")
        ).scalars()
    }
    missing = sorted(vehicle_ids - active_vehicles)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errors": [
                    f"Xe {vid} chưa có trong Danh_muc_xe (hoặc đang tạm ngừng hoạt động) — thêm xe trước khi nhập kế hoạch"
                    for vid in missing
                ]
            },
        )

    groups: "OrderedDict[tuple, list[dict]]" = OrderedDict()
    for r in rows:
        key = (r["vehicle_id"], r["shift_date"], r["shift_label"], r["trip_sequence"])
        groups.setdefault(key, []).append(r)

    created, updated = 0, 0
    for (vehicle_id, shift_date, shift_label, trip_sequence), group_rows in groups.items():
        first = group_rows[0]
        depot_arrival = first.get("depot_arrival_time")
        depot_loading = first.get("depot_loading_duration_min")
        planned_departure = _compute_planned_departure(depot_arrival, depot_loading)
        stops = [_row_to_stop_dict(r) for r in sorted(group_rows, key=lambda x: x["stop_order"])]

        existing = db.execute(
            select(Schedule).where(
                Schedule.vehicle_id == vehicle_id,
                Schedule.shift_date == shift_date,
                Schedule.shift_label == shift_label,
                Schedule.trip_sequence == trip_sequence,
                Schedule.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

        if existing is not None:
            # UPSERT theo khoá -> phải chặn ghi đè lên chuyến đang bị ngoại lệ
            # chưa giải quyết trỏ vào (xem _assert_not_locked_for_overwrite).
            _assert_not_locked_for_overwrite(db, existing)
            existing.depot_arrival_time = depot_arrival
            existing.depot_loading_duration_min = depot_loading
            existing.planned_departure_time = planned_departure
            existing.stops = stops
            updated += 1
        else:
            db.add(
                Schedule(
                    company_id=current_user["company_id"],
                    vehicle_id=vehicle_id,
                    shift_date=shift_date,
                    shift_label=shift_label,
                    trip_sequence=trip_sequence,
                    depot_arrival_time=depot_arrival,
                    depot_loading_duration_min=depot_loading,
                    planned_departure_time=planned_departure,
                    stops=stops,
                    created_by=current_user["user_id"],
                )
            )
            created += 1

    db.commit()
    return {"created": created, "updated": updated, "trips": len(groups), "total_stops": len(rows)}


UNFINISHED = "còn ngoại lệ chưa xong"


def _blocked_schedule_ids(db: Session, schedule_ids: list) -> set:
    """`schedule_id` nào đang bị 1 ngoại lệ CHƯA giải quyết trỏ tới.

    "Chưa giải quyết" = `status != 'resolved'` và chưa xoá mềm. Từ khi tách
    "chọn phương án" khỏi "nhập kết quả" (api/decisions.py), điều kiện này tự
    phủ cả 2 trường hợp còn dở: chưa chọn phương án, và đã chọn phương án
    nhưng chưa nhập kết quả.
    """
    if not schedule_ids:
        return set()
    rows = db.execute(
        select(Exception_.schedule_id).where(
            Exception_.schedule_id.in_(schedule_ids),
            Exception_.deleted_at.is_(None),
            Exception_.status != "resolved",
        )
    ).scalars().all()
    return set(rows)


def _partition_deletable(db: Session, schedules: list) -> tuple:
    """Chia danh sách chuyến thành (xoá được, giữ lại kèm lý do).

    Trước 2026-09-04 chiều, chỉ cần 1 chuyến vướng ngoại lệ là CHẶN TOÀN BỘ
    lệnh xoá — muốn dọn kế hoạch sai của 9 xe phải chờ giải quyết xong ngoại
    lệ của xe thứ 10. Nay xoá phần xoá được, giữ lại phần vướng và nói rõ giữ
    xe nào, vì sao.
    """
    blocked = _blocked_schedule_ids(db, [s.schedule_id for s in schedules])
    deletable, skipped = [], []
    for sched in schedules:
        if sched.schedule_id in blocked:
            skipped.append(
                {
                    "vehicle_id": sched.vehicle_id,
                    "schedule_id": str(sched.schedule_id),
                    "shift_label": sched.shift_label,
                    "trip_sequence": sched.trip_sequence,
                    "reason": UNFINISHED,
                }
            )
        else:
            deletable.append(sched)
    return deletable, skipped


def _assert_not_locked_for_overwrite(db: Session, existing) -> None:
    """Chặn GHI ĐÈ lên đúng 1 chuyến đang có ngoại lệ chưa giải quyết.

    `create_schedules` báo trùng khoá sẵn, nhưng `upload_schedules` thì UPSERT
    theo khoá (xe + ngày + ca + số chuyến) — nạp lại file Excel sẽ thay sạch
    `stops` của chuyến mà 1 ngoại lệ đang phân tích/chờ nhập kết quả trỏ vào,
    khiến `impact_analysis.affected_stops` chỉ tới những `stop_id` không còn
    tồn tại. Đổi ca hoặc đổi ngày thì khoá đã khác nên không đụng độ — chỉ
    chặn đúng trường hợp trùng cả 4 field.
    """
    if existing is None:
        return
    if existing.schedule_id in _blocked_schedule_ids(db, [existing.schedule_id]):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Chuyến của xe {existing.vehicle_id} ngày {existing.shift_date} "
                f"{existing.shift_label} chuyến {existing.trip_sequence} đang có ngoại lệ chưa xử lý xong — "
                "không ghi đè được. Hãy xử lý xong ngoại lệ đó, hoặc nhập vào số chuyến khác."
            ),
        )


@router.delete("", status_code=status.HTTP_200_OK)
def delete_schedules_by_shift(
    shift_date: date = Query(..., description="Ngày chạy cần xoá (YYYY-MM-DD)"),
    shift_label: str = Query(..., description="Ca cần xoá: ca_sang / ca_chieu / ca_dem"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Xoá mềm kế hoạch của 1 ngày + 1 ca, THEO TỪNG XE — chuyến của xe đang có
    ngoại lệ chưa giải quyết được giữ lại, phần còn lại vẫn xoá."""
    if shift_label not in ("ca_sang", "ca_chieu", "ca_dem"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ca chỉ nhận 'ca_sang', 'ca_chieu' hoặc 'ca_dem'",
        )

    schedules = db.execute(
        select(Schedule).where(
            Schedule.shift_date == shift_date,
            Schedule.shift_label == shift_label,
            Schedule.deleted_at.is_(None),
        )
    ).scalars().all()
    if not schedules:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không có kế hoạch nào cho ngày {shift_date} ca {shift_label}",
        )

    deletable, skipped = _partition_deletable(db, schedules)
    now = datetime.now(timezone.utc)
    for sched in deletable:
        sched.deleted_at = now
    db.commit()
    return {
        "deleted": len(deletable),
        "vehicles": sorted({s.vehicle_id for s in deletable}),
        "skipped": skipped,
        "shift_date": shift_date.isoformat(),
        "shift_label": shift_label,
    }


@router.delete("/{schedule_id}", status_code=status.HTTP_200_OK)
def delete_schedule(
    schedule_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Xoá mềm 1 chuyến. Cùng luật với xoá theo ngày+ca: chuyến đang có ngoại
    lệ chưa giải quyết thì giữ lại (`deleted: 0` + `skipped`), không xoá."""
    schedule = db.get(Schedule, schedule_id)
    if schedule is None or str(schedule.company_id) != current_user["company_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy chuyến {schedule_id}")

    deletable, skipped = _partition_deletable(db, [schedule])
    for sched in deletable:
        sched.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"deleted": len(deletable), "vehicles": [s.vehicle_id for s in deletable], "skipped": skipped}
