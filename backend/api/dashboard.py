"""Endpoint tổng hợp cho Dashboard "hoạt động sống hôm nay".

Chỉ ĐỌC (GET) — không đụng gì tới logic tạo/xử lý ngoại lệ hay cấu trúc dữ
liệu schedule/exception. Gom sẵn cây xe → ca → chuyến → đơn + ngoại lệ đang
mở ở BACKEND thay vì để frontend gọi 3 API (/api/vehicles, /api/schedules,
/api/exceptions) rồi tự join: join này cần cả `impact_analysis.affected_stops`
(để biết ngoại lệ gắn với đơn nào) — dữ liệu KHÔNG có trong
`GET /api/exceptions`, nên nếu join ở frontend thì vẫn phải gọi thêm
`GET /api/exceptions/{id}` cho từng ngoại lệ.
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from middleware.auth import get_current_user
from middleware.tenant import get_db
from models import Exception_, ImpactAnalysis, Schedule, Vehicle

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Ngoại lệ "đang mở" = mọi trạng thái KHÁC 'resolved'. `awaiting_outcome` (đã
# chốt phương án nhưng CHƯA nhập kết quả thực tế, xem api/decisions.py) VẪN là
# việc chưa xong của điều phối viên nên phải nằm ở đây — nếu thiếu, ngoại lệ
# biến mất khỏi Dashboard ngay sau khi xác nhận phương án và không còn đường
# nào để vào nhập kết quả.
#
# KHÁC với api/exceptions.py::ACTIVE_STATUSES (dùng cho detect_conflict): ở đó
# `awaiting_outcome` bị loại ĐÚNG chủ đích — ngoại lệ đã có quyết định rồi
# không được gộp nhóm với ngoại lệ mới nữa.
OPEN_STATUSES = ("pending", "analyzing", "awaiting_decision", "awaiting_outcome")

# Ngoại lệ "chưa hoàn thành" — mục riêng ở ĐẦU Dashboard (2026-09-04): đã phân
# tích xong nhưng còn chờ người quyết định/nhập kết quả. KHÔNG lọc theo ngày:
# việc chưa xong từ hôm kia vẫn phải đập vào mắt điều phối viên.
#
# HẸP hơn OPEN_STATUSES có chủ đích: pending/analyzing là ngoại lệ AI đang
# chạy, chưa cần ai làm gì — để nguyên trong "Hoạt động hôm nay".
BLOCKING_STATUSES = ("awaiting_decision", "awaiting_outcome")

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

    # MỌI kế hoạch chưa xoá, không chỉ hôm nay (2026-09-05): điều phối viên cần
    # thấy cả kế hoạch ngày mai đã nhập sẵn lẫn ngày cũ chưa dọn, chứ không chỉ
    # đúng 24h hiện tại. `shift_date` trả kèm theo TỪNG CHUYẾN vì 1 xe giờ có
    # thể có chuyến ở nhiều ngày khác nhau cùng lúc.
    schedules = db.execute(
        select(Schedule)
        .where(Schedule.deleted_at.is_(None))
        .order_by(Schedule.vehicle_id, Schedule.shift_date, Schedule.trip_sequence)
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

    # Tính mục "Ngoại lệ chưa hoàn thành" TRƯỚC (2026-09-05, sửa bug hiện trùng):
    # ngoại lệ nào đã nằm ở mục đó thì KHÔNG lặp lại ở cột trạng thái của xe
    # bên dưới nữa. Trước đây cùng 1 ngoại lệ hiện ở cả 2 chỗ.
    blocking = _blocking_section(db, open_exceptions, impacts)
    locked_ids = set(blocking["locked_schedule_ids"])

    schedule_vehicle = {s.schedule_id: s.vehicle_id for s in schedules}

    exceptions_by_vehicle: dict[str, list[dict]] = {}
    for exc in open_exceptions:
        if str(exc.schedule_id) in locked_ids:
            continue
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
        trips = [
            {
                "schedule_id": str(s.schedule_id),
                "shift_date": s.shift_date.isoformat(),
                "trip_sequence": s.trip_sequence,
                "depot_address": s.depot_address,
                "depot_arrival_time": s.depot_arrival_time.isoformat() if s.depot_arrival_time else None,
                "planned_departure_time": (
                    s.planned_departure_time.isoformat() if s.planned_departure_time else None
                ),
                "status": s.status,
                "order_count": len(s.stops or []),
                "stops": list(s.stops or []),
            }
            for s in sorted(
                schedules_by_vehicle.get(vehicle_id, []),
                key=lambda x: (x.shift_date, x.trip_sequence),
            )
        ]

        result.append(
            {
                "vehicle_id": vehicle_id,
                "driver_name": vehicle.driver_name if vehicle else None,
                "driver_phone": vehicle.driver_phone if vehicle else None,
                "vehicle_type": vehicle.vehicle_type if vehicle else None,
                "vehicle_status": vehicle.status if vehicle else None,
                "trips": trips,
                "today_order_count": sum(t["order_count"] for t in trips),
                "open_exceptions": exceptions_by_vehicle.get(vehicle_id, []),
            }
        )

    return {
        "shift_date": today.isoformat(),
        "server_time": now.isoformat(timespec="seconds"),
        "vehicles": result,
        **blocking,
    }


def _blocking_section(db: Session, open_exceptions: list, impacts: dict) -> dict:
    """Mục "Ngoại lệ chưa hoàn thành" + danh sách chuyến bị khoá theo nó.

    `blocking`: mỗi ngoại lệ đang chờ người xử lý, kèm xe và CÁC ĐƠN bị ảnh
    hưởng — không lọc theo ngày/ca.
    `locked_schedule_ids`: các chuyến xuất hiện ở mục trên, để "Hoạt động hôm
    nay" loại chúng khỏi accordion, tránh hiện trùng 2 chỗ. Các chuyến KHÁC
    của cùng xe (ca/chuyến khác) không bị loại.
    """
    items = []
    locked = set()
    for exc in open_exceptions:
        if exc.status not in BLOCKING_STATUSES:
            continue
        schedule = db.get(Schedule, exc.schedule_id)
        if schedule is None:
            continue
        locked.add(str(schedule.schedule_id))

        stops = list(schedule.stops or [])
        affected = impacts.get(exc.exception_id, [])
        affected_ids = {s.get("stop_id") for s in affected if s.get("stop_id")}
        # `affected_stop_ids` rỗng = chưa khoanh vùng được điểm nào -> ngoại lệ
        # ảnh hưởng cả chuyến, liệt kê toàn bộ đơn.
        picked = [st for st in stops if st.get("stop_id") in affected_ids] if affected_ids else stops

        vehicle = db.get(Vehicle, schedule.vehicle_id) if schedule.vehicle_id else None
        items.append(
            {
                "exception_id": str(exc.exception_id),
                "group_id": str(exc.group_id) if exc.group_id else None,
                "sub_type": exc.sub_type,
                "severity": exc.severity,
                "status": exc.status,
                "area": exc.area,
                "reported_at": exc.reported_at.isoformat() if exc.reported_at else None,
                "vehicle_id": schedule.vehicle_id,
                "driver_name": vehicle.driver_name if vehicle else None,
                "schedule_id": str(schedule.schedule_id),
                "shift_date": schedule.shift_date.isoformat(),
                "trip_sequence": schedule.trip_sequence,
                "orders": [
                    {
                        "stop_id": st.get("stop_id"),
                        "stop_order": st.get("stop_order"),
                        "order_id": st.get("order_id"),
                        "address": st.get("address"),
                        "eta": st.get("eta"),
                        "sla_deadline": st.get("sla_deadline"),
                    }
                    for st in picked
                ],
            }
        )

    items.sort(key=lambda i: (i["shift_date"], i["vehicle_id"] or "", i["trip_sequence"]))
    return {"blocking": items, "locked_schedule_ids": sorted(locked)}
