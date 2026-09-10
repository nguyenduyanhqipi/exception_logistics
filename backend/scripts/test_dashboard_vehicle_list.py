"""Test danh sách xe của GET /api/dashboard/today qua HTTP THẬT.

Bug được chốt lại ở đây (sửa 2026-09-10): endpoint dựng danh sách xe bằng cách
suy ra từ `schedules`/ngoại lệ đang mở, nên xe KHÔNG có chuyến nào hôm nay biến
mất hẳn khỏi bảng "Xe & Kế hoạch" — trái Quyết định 5 ("xe không có chuyến hôm
nay vẫn hiện 0 đơn · 0 chuyến, không để trống để khỏi lẫn với lỗi tải dữ
liệu"). Bug bị che rất lâu vì bản seed dữ liệu lịch sử CŨ nhét cho mỗi xe vài
dòng schedule rỗng; dọn sạch đống đó (đợt code 6, Việc 4) là 5/10 xe demo rơi
khỏi Dashboard ngay.

4 điều kiện phải giữ CÙNG LÚC — sửa 1 cái mà làm hỏng cái khác là quay lại bug
cũ ở dạng khác:
  1. Xe `active` không có chuyến nào  -> VẪN hiện, 0 đơn · 0 chuyến.
  2. Xe của công ty KHÁC              -> KHÔNG lọt (tenant isolation).
  3. Xe `inactive` không có chuyến    -> KHÔNG hiện ("Xoá xe" = chuyển sang
     inactive, xem api/vehicles.py::delete_vehicle — xoá xong mà Dashboard vẫn
     y nguyên thì nút xoá coi như vô nghĩa).
  4. Xe `inactive` NHƯNG còn chuyến   -> VẪN hiện (ẩn đi là giấu luôn việc chưa
     xong của điều phối viên).

Cần server đang chạy ở http://127.0.0.1:8000.
Chạy: python scripts/test_dashboard_vehicle_list.py
"""
import sys
import uuid
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.security import create_access_token
from database import SessionLocal
from models import Company, Schedule, User, Vehicle

BASE_URL = "http://127.0.0.1:8000"
COMPANY_A = "00000000-0000-0000-0000-000000000001"  # công ty demo có sẵn
COMPANY_B = str(uuid.uuid4())
USER_B = str(uuid.uuid4())

SUFFIX = uuid.uuid4().hex[:6]
V_IDLE = f"TEST-IDLE-{SUFFIX}"        # active, không có chuyến -> phải hiện
V_INACTIVE = f"TEST-OFF-{SUFFIX}"     # inactive, không có chuyến -> phải ẩn
V_INACTIVE_BUSY = f"TEST-OFFBUSY-{SUFFIX}"  # inactive nhưng còn chuyến -> phải hiện
V_OTHER_COMPANY = f"TEST-OTHER-{SUFFIX}"    # công ty B -> không được lọt

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


def _vehicle(vehicle_id, company_id, status):
    return Vehicle(
        vehicle_id=vehicle_id,
        company_id=company_id,
        driver_name=f"Tài xế {vehicle_id}",
        driver_phone="0900000000",
        max_payload_kg=1000,
        status=status,
    )


db = SessionLocal()
schedule_id = None
try:
    db.add(Company(company_id=COMPANY_B, name=f"Test Company B ({SUFFIX})"))
    db.add(
        User(
            user_id=USER_B,
            company_id=COMPANY_B,
            email=f"test-dash-b-{SUFFIX}@test.local",
            password_hash="x",
            role="dispatcher",
            full_name="Test User B",
        )
    )
    db.add(_vehicle(V_IDLE, COMPANY_A, "active"))
    db.add(_vehicle(V_INACTIVE, COMPANY_A, "inactive"))
    db.add(_vehicle(V_INACTIVE_BUSY, COMPANY_A, "inactive"))
    db.add(_vehicle(V_OTHER_COMPANY, COMPANY_B, "active"))
    db.flush()

    # `trip_sequence` lấy dải riêng để không đụng uq_schedules_vehicle_trip với
    # dữ liệu demo/lịch sử đang có trên cùng DB.
    busy = Schedule(
        company_id=COMPANY_A,
        vehicle_id=V_INACTIVE_BUSY,
        shift_date=date.today(),
        trip_sequence=8100,
        stops=[],
    )
    db.add(busy)
    db.commit()
    schedule_id = busy.schedule_id

    user_a = db.query(User).filter(User.company_id == COMPANY_A).first()
    token_a = create_access_token(str(user_a.user_id), COMPANY_A, "dispatcher")

    res = httpx.get(
        f"{BASE_URL}/api/dashboard/today",
        headers={"Authorization": f"Bearer {token_a}"},
        timeout=30,
    )
    check(f"GET /api/dashboard/today trả 200 (got {res.status_code})", res.status_code == 200)

    rows = {v["vehicle_id"]: v for v in res.json()["vehicles"]}

    check("1. Xe active KHÔNG có chuyến vẫn nằm trong danh sách", V_IDLE in rows)
    if V_IDLE in rows:
        idle = rows[V_IDLE]
        check(
            f"1b. Xe rảnh báo 0 đơn / 0 chuyến hôm nay "
            f"(got {idle['today_order_count']}/{idle['today_trip_count']})",
            idle["today_order_count"] == 0 and idle["today_trip_count"] == 0,
        )
        check("1c. Xe rảnh có đủ thông tin tài xế (không phải dòng rỗng)", bool(idle["driver_name"]))
        check("1d. Xe rảnh không kèm ngoại lệ đang mở", idle["open_exceptions"] == [])

    check("2. Xe của công ty KHÁC không lọt vào Dashboard", V_OTHER_COMPANY not in rows)
    check("3. Xe inactive không có chuyến thì KHÔNG hiện", V_INACTIVE not in rows)
    check("4. Xe inactive nhưng CÒN chuyến thì vẫn hiện", V_INACTIVE_BUSY in rows)

    # Mọi xe active của công ty A đều phải có mặt — đây mới là điều kiện tổng
    # quát, 4 ca trên chỉ là các trường hợp biên của nó.
    active_ids = {
        v.vehicle_id
        for v in db.query(Vehicle).filter(Vehicle.company_id == COMPANY_A, Vehicle.status == "active").all()
    }
    missing = sorted(active_ids - set(rows))
    check(f"5. Không sót xe active nào của công ty (thiếu: {missing})", not missing)

finally:
    if schedule_id is not None:
        db.query(Schedule).filter(Schedule.schedule_id == schedule_id).delete(synchronize_session=False)
    db.query(Vehicle).filter(
        Vehicle.vehicle_id.in_([V_IDLE, V_INACTIVE, V_INACTIVE_BUSY, V_OTHER_COMPANY])
    ).delete(synchronize_session=False)
    db.query(User).filter(User.user_id == USER_B).delete(synchronize_session=False)
    db.query(Company).filter(Company.company_id == COMPANY_B).delete(synchronize_session=False)
    db.commit()
    db.close()

print(f"\n{passed} PASS, {failed} FAIL")
sys.exit(1 if failed else 0)
