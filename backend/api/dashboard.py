"""Endpoint tổng hợp cho Dashboard "hoạt động sống hôm nay".

Chỉ ĐỌC (GET) — không đụng gì tới logic tạo/xử lý ngoại lệ hay cấu trúc dữ
liệu schedule/exception. Gom sẵn cây xe → ca → chuyến → đơn + ngoại lệ đang
mở ở BACKEND thay vì để frontend gọi 3 API (/api/vehicles, /api/schedules,
/api/exceptions) rồi tự join: join này cần cả `impact_analysis.affected_stops`
(để biết ngoại lệ gắn với đơn nào) — dữ liệu KHÔNG có trong
`GET /api/exceptions`, nên nếu join ở frontend thì vẫn phải gọi thêm
`GET /api/exceptions/{id}` cho từng ngoại lệ.
"""
from datetime import date, datetime, time

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from middleware.auth import get_current_user
from middleware.tenant import get_db
from models import Exception_, ImpactAnalysis, Schedule, Vehicle

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Ngoại lệ "đang mở" = mọi trạng thái KHÁC 'resolved' (giữ y hệt danh sách
# trong api/exceptions.py::ACTIVE_STATUSES — đã xử lý xong thì chuyển sang
# trang Lịch sử, không hiện ở dashboard nữa).
OPEN_STATUSES = ("pending", "analyzing", "awaiting_decision")

# Ca hiện tại suy ra từ GIỜ MÁY CHỦ, không hardcode. Phủ kín 24h để luôn có
# đúng 1 ca hiện tại (không có khoảng trống).
SHIFT_WINDOWS = (
    ("ca_sang", time(0, 0), time(11, 59, 59)),
    ("ca_chieu", time(12, 0), time(17, 59, 59)),
    ("ca_dem", time(18, 0), time(23, 59, 59)),
)

SHIFT_ORDER = {"ca_sang": 0, "ca_chieu": 1, "ca_dem": 2}


def current_shift_label(now: datetime) -> str:
    t = now.time()
    for label, start, end in SHIFT_WINDOWS:
        if start <= t <= end:
            return label
    return SHIFT_WINDOWS[-1][0]


def _exception_to_dict(exc: Exception_, affected_stop_ids: list[str], affected_order_ids: list[str]) -> dict:
    return {
        "exception_id": str(exc.exception_id),
        "schedule_id": str(exc.schedule_id),
        "group_id": str(exc.group_id) if exc.group_id else None,
        "exception_group": exc.exception_group,
        "sub_type": exc.sub_type,
        "severity": exc.severity,
        "status": exc.status,
        "area": exc.area,
        "description": exc.description,
        "reported_at": exc.reported_at.isoformat() if exc.reported_at else None,
        # Rỗng = ngoại lệ ảnh hưởng cả chuyến (chưa phân tích xong, hoặc
        # không khoanh vùng được điểm giao cụ thể) — frontend hiểu là gắn với
        # MỌI đơn của chuyến đó.
        "affected_stop_ids": affected_stop_ids,
        "affected_order_ids": affected_order_ids,
    }


@router.get("/today")
def dashboard_today(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now()
    today: date = now.date()
    shift_now = current_shift_label(now)

    schedules = db.execute(
        select(Schedule)
        .where(Schedule.shift_date == today, Schedule.deleted_at.is_(None))
        .order_by(Schedule.vehicle_id, Schedule.shift_label, Schedule.trip_sequence)
    ).scalars().all()

    # Ngoại lệ đang mở KHÔNG lọc theo ngày: một ngoại lệ mở từ hôm qua vẫn là
    # việc chưa xong của điều phối viên, phải thấy được ở dashboard.
    open_exceptions = db.execute(
        select(Exception_)
        .where(Exception_.status.in_(OPEN_STATUSES), Exception_.deleted_at.is_(None))
        .order_by(Exception_.reported_at.desc())
    ).scalars().all()

    impacts = {}
    if open_exceptions:
        rows = db.execute(
            select(ImpactAnalysis).where(
                ImpactAnalysis.exception_id.in_([e.exception_id for e in open_exceptions])
            )
        ).scalars().all()
        for imp in rows:
            impacts[imp.exception_id] = imp.affected_stops or []

    schedule_vehicle = {s.schedule_id: s.vehicle_id for s in schedules}

    exceptions_by_vehicle: dict[str, list[dict]] = {}
    for exc in open_exceptions:
        # `exceptions.vehicle_id` nullable — lấy từ chuyến gắn với ngoại lệ khi
        # thiếu, để ngoại lệ không bị rơi khỏi dashboard.
        vehicle_id = exc.vehicle_id or schedule_vehicle.get(exc.schedule_id)
        if vehicle_id is None:
            sched = db.get(Schedule, exc.schedule_id)
            vehicle_id = sched.vehicle_id if sched else None
        if vehicle_id is None:
            continue
        affected = impacts.get(exc.exception_id, [])
        exceptions_by_vehicle.setdefault(vehicle_id, []).append(
            _exception_to_dict(
                exc,
                [s["stop_id"] for s in affected if s.get("stop_id")],
                [s["order_id"] for s in affected if s.get("order_id")],
            )
        )

    vehicle_ids = set(schedule_vehicle.values()) | set(exceptions_by_vehicle)
    vehicles = {
        v.vehicle_id: v
        for v in db.execute(select(Vehicle).where(Vehicle.vehicle_id.in_(vehicle_ids))).scalars()
    } if vehicle_ids else {}

    schedules_by_vehicle: dict[str, list[Schedule]] = {}
    for s in schedules:
        schedules_by_vehicle.setdefault(s.vehicle_id, []).append(s)

    result = []
    for vehicle_id in sorted(vehicle_ids):
        vehicle = vehicles.get(vehicle_id)
        vehicle_schedules = schedules_by_vehicle.get(vehicle_id, [])

        shifts_map: dict[str, list[Schedule]] = {}
        for s in vehicle_schedules:
            shifts_map.setdefault(s.shift_label, []).append(s)

        shifts = []
        for shift_label in sorted(shifts_map, key=lambda x: SHIFT_ORDER.get(x, 99)):
            trips = []
            for s in sorted(shifts_map[shift_label], key=lambda x: x.trip_sequence):
                stops = list(s.stops or [])
                trips.append(
                    {
                        "schedule_id": str(s.schedule_id),
                        "trip_sequence": s.trip_sequence,
                        "depot_address": s.depot_address,
                        "depot_arrival_time": s.depot_arrival_time.isoformat() if s.depot_arrival_time else None,
                        "planned_departure_time": (
                            s.planned_departure_time.isoformat() if s.planned_departure_time else None
                        ),
                        "status": s.status,
                        "order_count": len(stops),
                        "stops": stops,
                    }
                )
            shifts.append(
                {
                    "shift_label": shift_label,
                    "trip_count": len(trips),
                    "order_count": sum(t["order_count"] for t in trips),
                    "trips": trips,
                }
            )

        current_shift = next((sh for sh in shifts if sh["shift_label"] == shift_now), None)
        result.append(
            {
                "vehicle_id": vehicle_id,
                "driver_name": vehicle.driver_name if vehicle else None,
                "driver_phone": vehicle.driver_phone if vehicle else None,
                "vehicle_type": vehicle.vehicle_type if vehicle else None,
                "vehicle_status": vehicle.status if vehicle else None,
                "current_shift_order_count": current_shift["order_count"] if current_shift else 0,
                "today_order_count": sum(sh["order_count"] for sh in shifts),
                "shifts": shifts,
                "open_exceptions": exceptions_by_vehicle.get(vehicle_id, []),
            }
        )

    return {
        "shift_date": today.isoformat(),
        "current_shift_label": shift_now,
        "server_time": now.isoformat(timespec="seconds"),
        "vehicles": result,
    }
