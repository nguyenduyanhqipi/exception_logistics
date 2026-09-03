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
from schemas.decision import DecisionCreate, OutcomeCreate, OutcomeUpdate

router = APIRouter(prefix="/api", tags=["decisions"])

# Vòng đời status của 1 ngoại lệ:
#   pending -> analyzing -> awaiting_decision -> awaiting_outcome -> resolved
#
# `awaiting_outcome` = ĐÃ chọn phương án nhưng CHƯA nhập kết quả thực tế.
# Trước 2026-09-04, `create_decision` set thẳng "resolved" nên "resolved" thực
# chất chỉ có nghĩa "đã chọn phương án" — KPI on_time_rate/total_actual_cost
# không có gì để tính, mà ngoại lệ đã bị khoá không sửa được nữa. Nay
# `create_outcome` là chỗ DUY NHẤT trong toàn hệ thống chuyển sang "resolved",
# nên "resolved" = "đã có outcome" đúng nghĩa.
AWAITING_OUTCOME = "awaiting_outcome"
RESOLVED = "resolved"


def _members_of(decision: Decision, db: Session) -> list:
    """Các ngoại lệ mà 1 quyết định chi phối: 1 ngoại lệ đơn lẻ, hoặc TOÀN BỘ
    thành viên của nhóm combined mode (1 quyết định phối hợp cho cả nhóm —
    mục 5.3, 10). Bỏ qua thành viên đã xoá mềm."""
    if decision.exception_id is not None:
        exc = db.get(Exception_, decision.exception_id)
        return [exc] if exc is not None and exc.deleted_at is None else []
    group = db.get(ExceptionGroup, decision.group_id)
    if group is None:
        return []
    return list(
        db.execute(
            select(Exception_).where(
                Exception_.exception_id.in_(group.exception_ids), Exception_.deleted_at.is_(None)
            )
        ).scalars()
    )


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
        group.status = AWAITING_OUTCOME

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
        # KHÔNG phải "resolved" — mới chỉ chốt phương án, chưa có kết quả thực
        # tế. Chuyển sang "resolved" là việc của create_outcome bên dưới.
        member.status = AWAITING_OUTCOME
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


def _outcome_to_dict(outcome: Outcome) -> dict:
    return {
        "outcome_id": str(outcome.outcome_id),
        "decision_id": str(outcome.decision_id),
        "delivered_on_time": outcome.delivered_on_time,
        "delay_minutes": outcome.delay_minutes,
        "actual_cost": float(outcome.actual_cost) if outcome.actual_cost is not None else None,
        "notes": outcome.notes,
        "recorded_at": outcome.recorded_at.isoformat(),
    }


@router.post("/outcomes", status_code=status.HTTP_201_CREATED)
def create_outcome(
    payload: OutcomeCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ghi nhận kết quả thực tế — CHỖ DUY NHẤT chuyển ngoại lệ sang "resolved"."""
    decision = db.get(Decision, payload.decision_id)
    if decision is None or str(decision.company_id) != current_user["company_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy quyết định {payload.decision_id}")

    existing = db.execute(
        select(Outcome).where(Outcome.decision_id == decision.decision_id)
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quyết định này đã có kết quả rồi — dùng chức năng sửa kết quả nếu cần chỉnh lại.",
        )

    outcome = Outcome(
        decision_id=decision.decision_id,
        delivered_on_time=payload.delivered_on_time,
        delay_minutes=payload.delay_minutes,
        actual_cost=payload.actual_cost,
        notes=payload.notes,
        recorded_by=current_user["user_id"],
    )
    db.add(outcome)

    # Đã có kết quả thực tế -> ngoại lệ (hoặc CẢ nhóm, giống cách
    # create_decision duyệt members_to_resolve) mới thật sự xong.
    for member in _members_of(decision, db):
        member.status = RESOLVED
    if decision.group_id is not None:
        group = db.get(ExceptionGroup, decision.group_id)
        if group is not None:
            group.status = RESOLVED

    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="record_outcome",
            entity_type="decision",
            entity_id=decision.decision_id,
            detail={
                "delivered_on_time": payload.delivered_on_time,
                "delay_minutes": payload.delay_minutes,
                "actual_cost": float(payload.actual_cost),
            },
        )
    )

    db.commit()
    db.refresh(outcome)
    return _outcome_to_dict(outcome)


@router.patch("/outcomes/{outcome_id}")
def update_outcome(
    outcome_id: str,
    payload: OutcomeUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sửa kết quả đã ghi. KHÔNG có endpoint xoá outcome — outcome là bản ghi
    KPI, xoá nó sẽ đưa ngoại lệ về trạng thái "đã quyết định nhưng chưa có kết
    quả" mà không để lại dấu vết gì.

    `delay_minutes`/`actual_cost`/`notes` sửa tự do (chi phí về 0 được).
    `delivered_on_time` chỉ đổi được True -> False.
    """
    outcome = db.get(Outcome, outcome_id)
    if outcome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy kết quả {outcome_id}")
    # `Outcome` KHÔNG có company_id (xem docstring api/reports.py) nên không
    # được tenant filter tự động — phải kiểm tra chủ sở hữu qua `Decision`.
    decision = db.get(Decision, outcome.decision_id)
    if decision is None or str(decision.company_id) != current_user["company_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy kết quả {outcome_id}")

    if outcome.delivered_on_time is False and payload.delivered_on_time is True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Không thể đổi từ 'muộn giờ' về 'đúng giờ'. Đơn đã ghi nhận là giao muộn — "
                "chỉ sửa được số phút muộn, chi phí và ghi chú."
            ),
        )

    before = {
        "delivered_on_time": outcome.delivered_on_time,
        "delay_minutes": outcome.delay_minutes,
        "actual_cost": float(outcome.actual_cost) if outcome.actual_cost is not None else None,
    }
    outcome.delivered_on_time = payload.delivered_on_time
    outcome.delay_minutes = payload.delay_minutes
    outcome.actual_cost = payload.actual_cost
    outcome.notes = payload.notes

    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="update_outcome",
            entity_type="decision",
            entity_id=decision.decision_id,
            detail={
                "outcome_id": str(outcome.outcome_id),
                "before": before,
                "after": {
                    "delivered_on_time": payload.delivered_on_time,
                    "delay_minutes": payload.delay_minutes,
                    "actual_cost": float(payload.actual_cost),
                },
            },
        )
    )

    db.commit()
    db.refresh(outcome)
    return _outcome_to_dict(outcome)
