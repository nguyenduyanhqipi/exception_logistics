"""api/decisions.py — mục 12: xác nhận phương án + nhập kết quả thực tế.

Không có bước riêng trong BUILD_PLAN.md cho 2 endpoint này (khoảng trống giữa
Giai đoạn 5-7, phát hiện lúc làm Giai đoạn 8) — bổ sung ở đây vì Dashboard
dispatcher (bước 8.6) không thể "xác nhận quyết định" nếu thiếu chúng.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from middleware.auth import get_current_user
from middleware.tenant import get_db
from models import AuditLog, Decision, Exception_, ExceptionGroup, Option, Outcome, ResourceLock
from schemas.decision import DecisionCreate, OutcomeCreate

router = APIRouter(prefix="/api", tags=["decisions"])


@router.post("/decisions", status_code=status.HTTP_201_CREATED)
def create_decision(
    payload: DecisionCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    option = db.get(Option, payload.selected_option_id)
    if option is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phương án")

    if payload.exception_id is not None:
        exc = db.get(Exception_, payload.exception_id)
        if exc is None or str(exc.company_id) != current_user["company_id"] or exc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy ngoại lệ {payload.exception_id}")
        if option.exception_id != exc.exception_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phương án này không thuộc ngoại lệ đã chọn")
        members_to_resolve = [exc]
    else:
        group = db.get(ExceptionGroup, payload.group_id)
        if group is None or str(group.company_id) != current_user["company_id"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy nhóm {payload.group_id}")
        if option.group_id != group.group_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phương án này không thuộc nhóm đã chọn")
        members_to_resolve = list(db.execute(select(Exception_).where(Exception_.exception_id.in_(group.exception_ids))).scalars())
        group.status = "resolved"

    decision = Decision(
        company_id=current_user["company_id"],
        exception_id=payload.exception_id,
        group_id=payload.group_id,
        selected_option_id=option.option_id,
        confirmed_by=current_user["user_id"],
        override_note=payload.override_note,
    )
    db.add(decision)

    for member in members_to_resolve:
        member.status = "resolved"
        # Dispatcher đã quyết định xong -> tài nguyên tạm khoá cho ngoại lệ
        # này không còn cần giữ nữa (mục 5.3/10: lock chỉ tồn tại "khi đang
        # chờ xác nhận"), dọn ngay thay vì đợi hết hạn 10 phút.
        db.query(ResourceLock).filter(ResourceLock.exception_id == member.exception_id).delete(synchronize_session=False)

    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="override" if payload.override_note else "confirm_decision",
            entity_type="exception" if payload.exception_id else "exception_group",
            entity_id=payload.exception_id or payload.group_id,
            detail={"selected_option_id": str(option.option_id), "override_note": payload.override_note},
        )
    )

    db.commit()
    db.refresh(decision)
    return {
        "decision_id": str(decision.decision_id),
        "exception_id": str(decision.exception_id) if decision.exception_id else None,
        "group_id": str(decision.group_id) if decision.group_id else None,
        "selected_option_id": str(decision.selected_option_id),
        "override_note": decision.override_note,
        "confirmed_at": decision.confirmed_at.isoformat(),
    }


@router.post("/outcomes", status_code=status.HTTP_201_CREATED)
def create_outcome(
    payload: OutcomeCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    decision = db.get(Decision, payload.decision_id)
    if decision is None or str(decision.company_id) != current_user["company_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy quyết định {payload.decision_id}")

    outcome = Outcome(
        decision_id=decision.decision_id,
        delivered_on_time=payload.delivered_on_time,
        actual_cost=payload.actual_cost,
        notes=payload.notes,
        recorded_by=current_user["user_id"],
    )
    db.add(outcome)

    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="record_outcome",
            entity_type="decision",
            entity_id=decision.decision_id,
            detail={"delivered_on_time": payload.delivered_on_time, "actual_cost": float(payload.actual_cost) if payload.actual_cost is not None else None},
        )
    )

    db.commit()
    db.refresh(outcome)
    return {
        "outcome_id": str(outcome.outcome_id),
        "decision_id": str(outcome.decision_id),
        "delivered_on_time": outcome.delivered_on_time,
        "actual_cost": float(outcome.actual_cost) if outcome.actual_cost is not None else None,
        "notes": outcome.notes,
        "recorded_at": outcome.recorded_at.isoformat(),
    }
