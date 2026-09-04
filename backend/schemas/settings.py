from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, model_validator


class WeightsUpdate(BaseModel):
    cost: float
    time: float
    sla_risk: float

    @model_validator(mode="after")
    def check_sum_to_one(self):
        total = self.cost + self.time + self.sla_risk
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Tổng 3 trọng số phải bằng 1.0 (hiện tại: {total})")
        return self


class DepotUpdate(BaseModel):
    default_depot_address: Optional[str] = None
    default_depot_area: Optional[str] = None
    default_cost_per_km: Optional[Decimal] = None


class OutcomeLockUpdate(BaseModel):
    """Việc 3 (2026-09-04) — số ngày sau khi ghi nhận kết quả thì khoá không
    cho sửa nữa. None hoặc 0 = không khoá."""

    outcome_edit_lock_days: Optional[int] = None

    @model_validator(mode="after")
    def check_non_negative(self):
        if self.outcome_edit_lock_days is not None and self.outcome_edit_lock_days < 0:
            raise ValueError("Số ngày khoá không được âm (để trống hoặc 0 = không khoá)")
        return self
