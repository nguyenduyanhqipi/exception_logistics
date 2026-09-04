from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from middleware.rbac import require_role
from middleware.tenant import get_db
from models import AuditLog, Company
from schemas.settings import DepotUpdate, OutcomeLockUpdate, WeightsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _serialize(company: Company) -> dict:
    return {
        "company_id": str(company.company_id),
        "name": company.name,
        "timezone": company.timezone,
        "ranking_weights": company.ranking_weights,
        "default_depot_address": company.default_depot_address,
        "default_depot_area": company.default_depot_area,
        "default_cost_per_km": float(company.default_cost_per_km),
        "outcome_edit_lock_days": company.outcome_edit_lock_days,
    }


@router.get("")
def get_settings(
    current_user: dict = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    company = db.execute(
        select(Company).where(Company.company_id == current_user["company_id"])
    ).scalar_one()
    return _serialize(company)


@router.put("/weights")
def update_weights(
    payload: WeightsUpdate,
    current_user: dict = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    company = db.execute(
        select(Company).where(Company.company_id == current_user["company_id"])
    ).scalar_one()

    old_weights = company.ranking_weights
    company.ranking_weights = payload.model_dump()
    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="update_settings",
            entity_type="company",
            entity_id=current_user["company_id"],
            detail={"field": "ranking_weights", "old": old_weights, "new": company.ranking_weights},
        )
    )
    db.commit()
    db.refresh(company)
    return _serialize(company)


@router.put("/depot")
def update_depot(
    payload: DepotUpdate,
    current_user: dict = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    company = db.execute(
        select(Company).where(Company.company_id == current_user["company_id"])
    ).scalar_one()

    changes = payload.model_dump(exclude_unset=True)
    old_values = {field: getattr(company, field) for field in changes}
    for field, value in changes.items():
        setattr(company, field, value)

    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="update_settings",
            entity_type="company",
            entity_id=current_user["company_id"],
            detail={"field": "depot", "old": {k: str(v) for k, v in old_values.items()}, "new": {k: str(v) for k, v in changes.items()}},
        )
    )
    db.commit()
    db.refresh(company)
    return _serialize(company)


@router.put("/outcome-lock")
def update_outcome_lock(
    payload: OutcomeLockUpdate,
    current_user: dict = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    """Đặt số ngày khoá sửa kết quả (việc 3). Áp dụng ở
    api/decisions.py::update_outcome."""
    company = db.execute(
        select(Company).where(Company.company_id == current_user["company_id"])
    ).scalar_one()

    old_value = company.outcome_edit_lock_days
    # 0 và None đều nghĩa là "không khoá" — chuẩn hoá về None để chỉ có 1 cách
    # biểu diễn trong DB.
    company.outcome_edit_lock_days = payload.outcome_edit_lock_days or None

    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action="update_settings",
            entity_type="company",
            entity_id=current_user["company_id"],
            detail={"field": "outcome_edit_lock_days", "old": old_value, "new": company.outcome_edit_lock_days},
        )
    )
    db.commit()
    db.refresh(company)
    return _serialize(company)
