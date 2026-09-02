from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class VehicleCreate(BaseModel):
    vehicle_id: str = Field(min_length=1)
    driver_name: str = Field(min_length=1)
    driver_phone: str = Field(min_length=1)
    max_payload_kg: Decimal
    vehicle_type: Optional[str] = None
    cost_per_km: Optional[Decimal] = None
    status: str = "active"


class VehicleUpdate(BaseModel):
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    max_payload_kg: Optional[Decimal] = None
    vehicle_type: Optional[str] = None
    cost_per_km: Optional[Decimal] = None
    status: Optional[str] = None


class VehicleResponse(BaseModel):
    vehicle_id: str
    driver_name: str
    driver_phone: str
    max_payload_kg: Decimal
    vehicle_type: Optional[str]
    cost_per_km: Optional[Decimal]
    status: str

    model_config = {"from_attributes": True}
