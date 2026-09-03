from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ExceptionCreate(BaseModel):
    schedule_id: UUID
    exception_group: str
    answer_key: str
    depot_on_time: Optional[bool] = None
    has_injury: Optional[bool] = None
    area: Optional[str] = None
    description: Optional[str] = None

    # Phạm vi điểm giao bị ảnh hưởng (mục 5, xem core/impact_analyzer.py):
    # to_stop_order=None -> ảnh hưởng dây chuyền đến hết chuyến (delay,
    # traffic_jam, road_closed, vehicle_issue); set to_stop_order=from_stop_order
    # cho vấn đề cục bộ 1 điểm (customer_reject, customer_change).
    from_stop_order: int = 1
    to_stop_order: Optional[int] = None
    delay_minutes: int = 0

    # Các tín hiệu định lượng riêng theo sub_type (mục 5.2) — dispatcher chỉ
    # điền field liên quan đến sub_type đã chọn, các field khác bỏ qua.
    departure_delay_min: Optional[int] = None
    driver_contact_lost_min: Optional[int] = None
    estimated_traffic_duration_min: Optional[int] = None
    is_repeat_delivery: Optional[bool] = None
    new_address_distance_km: Optional[float] = None
    has_time_conflict: Optional[bool] = None
    new_location_distance_km: Optional[float] = None
    estimated_repair_min: Optional[int] = None

    # Mục F — khách chủ động chấp nhận trễ tối đa bao nhiêu phút so với SLA
    # gốc (hỏi 2 bước, optional). CHỈ dùng ở ranker.py, KHÔNG ảnh hưởng
    # impact_analysis/sla_breach thật.
    customer_accepted_delay_min: Optional[int] = None


class ManualOptionCreate(BaseModel):
    description: str = Field(min_length=1)
    cost_estimate: Optional[Decimal] = None
    time_estimate_minutes: Optional[int] = None


class ExceptionResponse(BaseModel):
    exception_id: UUID
    schedule_id: UUID
    group_id: Optional[UUID]
    exception_group: str
    sub_type: str
    severity: Optional[str]
    vehicle_id: Optional[str]
    area: Optional[str]
    description: Optional[str]
    customer_accepted_delay_min: Optional[int] = None
    status: str

    model_config = {"from_attributes": True}
