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
