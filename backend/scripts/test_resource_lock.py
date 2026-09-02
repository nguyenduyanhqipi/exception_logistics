"""Test resource_lock.py (BUILD_PLAN.md bước 4.7) — cần DB thật (dùng bảng
resource_locks, exceptions, schedules, vehicles, users, companies đã seed)."""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from core.resource_lock import cleanup_expired_locks, create_lock, get_active_locks
from database import SessionLocal
from models import Exception_, ResourceLock, Schedule, User, Vehicle

passed = 0
failed = 0


def check(label, actual, expected):
    global passed, failed
    ok = actual == expected
    print(f"[{'OK' if ok else 'FAIL'}] {label}: got={actual!r} expected={expected!r}")
    if ok:
        passed += 1
    else:
        failed += 1


db = SessionLocal()
try:
    company_id = "00000000-0000-0000-0000-000000000001"
    user = db.execute(select(User).where(User.company_id == company_id)).scalars().first()
    vehicle = db.execute(select(Vehicle).where(Vehicle.company_id == company_id)).scalars().first()
    schedule = db.execute(select(Schedule).where(Schedule.company_id == company_id)).scalars().first()

    exc = Exception_(
        company_id=company_id,
        schedule_id=schedule.schedule_id,
        exception_group="vehicle_issue",
        sub_type="major_breakdown",
        severity="serious",
        vehicle_id=vehicle.vehicle_id,
        reported_by=user.user_id,
    )
    db.add(exc)
    db.commit()
    db.refresh(exc)

    # Lock CÒN hạn -> get_active_locks phải thấy
    active_lock = create_lock(db, exc.exception_id, "vehicle", vehicle.vehicle_id, user.user_id, ttl_minutes=10)
    check("Lock mới tạo có expires_at trong tương lai", active_lock.expires_at > datetime.now(timezone.utc), True)

    active = get_active_locks(db, resource_type="vehicle")
    check("get_active_locks thấy lock vừa tạo", any(l.lock_id == active_lock.lock_id for l in active), True)

    # Lock đã HẾT hạn (expires_at trong quá khứ) -> tạo trực tiếp qua model
    expired_lock = ResourceLock(
        exception_id=exc.exception_id,
        resource_type="vehicle",
        resource_id=vehicle.vehicle_id,
        locked_by=user.user_id,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db.add(expired_lock)
    db.commit()
    db.refresh(expired_lock)
    expired_lock_id = expired_lock.lock_id

    active_before = get_active_locks(db, resource_type="vehicle")
    check("get_active_locks KHÔNG thấy lock hết hạn", any(l.lock_id == expired_lock_id for l in active_before), False)

    deleted_count = cleanup_expired_locks(db)
    check("cleanup_expired_locks xóa đúng 1 lock hết hạn", deleted_count, 1)

    remaining = db.get(ResourceLock, expired_lock_id)
    check("Lock hết hạn đã bị xóa khỏi DB", remaining, None)

    still_active = db.get(ResourceLock, active_lock.lock_id)
    check("Lock còn hạn KHÔNG bị xóa nhầm", still_active is not None, True)

finally:
    db.query(ResourceLock).filter(ResourceLock.exception_id == exc.exception_id).delete(synchronize_session=False)
    db.query(Exception_).filter(Exception_.exception_id == exc.exception_id).delete(synchronize_session=False)
    db.commit()
    db.close()
    print("Đã dọn dữ liệu test.")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
