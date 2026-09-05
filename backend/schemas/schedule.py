from datetime import date, time
from decimal import Decimal
from typing import Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class StopCreate(BaseModel):
    stop_order: int = Field(gt=0)
    stop_type: str = "giao_hang"
    address: str = Field(min_length=1)
    area: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    customer_name: str = Field(min_length=1)
    customer_phone: str = Field(min_length=1)
    eta: time
    loading_duration_min: Optional[int] = None
    sla_deadline: time
    priority_tier: str = "thuong"
    sla_penalty: Optional[Decimal] = None
    volume_kg: Optional[Decimal] = None
    cargo_type: str = "normal"
    notes: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None

    @field_validator("stop_type")
    @classmethod
    def validate_stop_type(cls, v):
        if v not in ("lay_hang", "giao_hang"):
            raise ValueError("stop_type chỉ nhận 'lay_hang' hoặc 'giao_hang'")
        return v

    @field_validator("priority_tier")
    @classmethod
    def validate_priority_tier(cls, v):
        if v not in ("thuong", "vip", "hop_dong_phat"):
            raise ValueError("priority_tier chỉ nhận 'thuong'/'vip'/'hop_dong_phat'")
        return v

    @field_validator("cargo_type")
    @classmethod
    def validate_cargo_type(cls, v):
        if v not in ("normal", "bulky"):
            raise ValueError("cargo_type chỉ nhận 'normal' hoặc 'bulky'")
        return v


class ScheduleCreate(BaseModel):
    vehicle_id: str = Field(min_length=1)
    shift_date: date
    trip_sequence: int = 1
    depot_arrival_time: Optional[time] = None
    depot_loading_duration_min: Optional[int] = None
    depot_address: Optional[str] = None
    stops: list[StopCreate] = []

    @field_validator("stops")
    @classmethod
    def validate_unique_stop_order(cls, v):
        orders = [s.stop_order for s in v]
        if len(orders) != len(set(orders)):
            raise ValueError("stop_order bị trùng trong cùng một chuyến")
        return v


ScheduleCreateBody = Union[ScheduleCreate, list[ScheduleCreate]]


class ScheduleResponse(BaseModel):
    schedule_id: UUID
    vehicle_id: str
    shift_date: date
    trip_sequence: int
    depot_arrival_time: Optional[time]
    depot_loading_duration_min: Optional[int]
    planned_departure_time: Optional[time]
    depot_address: Optional[str]
    stops: list
    status: str

    model_config = {"from_attributes": True}
