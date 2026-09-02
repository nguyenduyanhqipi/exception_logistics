"""resource_lock.py — khóa tài nguyên tạm thời khi đang chờ xác nhận (mục 5.3, 10).

Worker (job_processor.py, Giai đoạn 5) gọi `cleanup_expired_locks()` định kỳ
mỗi 5 phút.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ResourceLock

DEFAULT_TTL_MINUTES = 10


def create_lock(
    db: Session,
    exception_id: str,
    resource_type: str,
    resource_id: str,
    locked_by: str,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> ResourceLock:
    lock = ResourceLock(
        exception_id=exception_id,
        resource_type=resource_type,
        resource_id=resource_id,
        locked_by=locked_by,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    )
    db.add(lock)
    db.commit()
    db.refresh(lock)
    return lock


def get_active_locks(db: Session, resource_type: "str | None" = None) -> list[ResourceLock]:
    """Chỉ trả về lock có `expires_at > now()` (mục 5.3, bước 3 conflict_detector)."""
    now = datetime.now(timezone.utc)
    stmt = select(ResourceLock).where(ResourceLock.expires_at > now)
    if resource_type is not None:
        stmt = stmt.where(ResourceLock.resource_type == resource_type)
    return list(db.execute(stmt).scalars().all())


def cleanup_expired_locks(db: Session) -> int:
    """Xóa mọi lock đã hết hạn. Trả về số lock đã xóa."""
    now = datetime.now(timezone.utc)
    expired = db.execute(select(ResourceLock).where(ResourceLock.expires_at <= now)).scalars().all()
    count = len(expired)
    for lock in expired:
        db.delete(lock)
    db.commit()
    return count
