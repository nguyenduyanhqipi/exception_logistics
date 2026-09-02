from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class DecisionCreate(BaseModel):
    exception_id: Optional[UUID] = None
    group_id: Optional[UUID] = None
    selected_option_id: UUID
    override_note: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_target(self):
        if (self.exception_id is None) == (self.group_id is None):
            raise ValueError("Phải cung cấp đúng 1 trong 2: exception_id hoặc group_id")
        return self


class OutcomeCreate(BaseModel):
    decision_id: UUID
    delivered_on_time: Optional[bool] = None
    actual_cost: Optional[Decimal] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
