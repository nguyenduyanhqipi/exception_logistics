from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ExceptionCreate(BaseModel):
    schedule_id: UUID
    exception_group: str
    answer_key: str
    # Tách từ `has_injury` gộp chung (đợt 12, việc 2): tài xế bị thương thì
    # CHẮC CHẮN không lái tiếp được, người khác bị thương thì không suy ra
    # được điều đó — 2 tín hiệu này dẫn tới phương án khác hẳn nhau.
    driver_injured: Optional[bool] = None
    other_injured: Optional[bool] = None
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
    # `departure_delay_min` từ 2026-09-08 CHỈ còn dùng cho trạng thái "đã xuất
    # phát" (số THỰC TẾ); trường hợp chưa xuất phát dùng
    # `estimated_departure_delay_min` bên dưới.
    departure_delay_min: Optional[int] = None
    driver_contact_lost_min: Optional[int] = None
    estimated_traffic_duration_min: Optional[int] = None
    is_repeat_delivery: Optional[bool] = None
    has_time_conflict: Optional[bool] = None
    new_location_distance_km: Optional[float] = None
    estimated_repair_min: Optional[int] = None

    # --- Câu trả lời phụ, redesign 2026-09-08 (exception_intake_review.md) ---
    # Mỗi field chỉ có nghĩa với đúng 1-2 sub_type; dispatcher bỏ trống phần
    # còn lại. Tất cả đều Optional vì form chỉ hiện đúng câu hỏi của sub_type
    # đang chọn — bắt buộc ở đây sẽ chặn luôn 10 sub_type còn lại.
    #
    # delay:
    departure_status: Optional[str] = None          # chua_xuat_phat | da_xuat_phat
    late_departure_cause: Optional[str] = None      # chỉ khi chua_xuat_phat
    estimated_departure_delay_min: Optional[int] = None  # ƯỚC TÍNH, chưa xảy ra xong
    departed_late_cause: Optional[str] = None       # chỉ khi da_xuat_phat, tuỳ chọn
    # customer_reject:
    contacted_customer: Optional[bool] = None       # customer_absent
    customer_request: Optional[str] = None          # hen_giao_lai | doi_dia_diem | huy
    dispute_type: Optional[str] = None              # customer_dispute
    # vehicle_issue:
    can_transfer_cargo_safely: Optional[str] = None  # co | khong | chua_chac (major_breakdown)
    vehicle_movable: Optional[bool] = None          # accident
    # Vị trí xe hiện tại — dùng chung road_closed + major_breakdown, nuôi tính
    # năng bản đồ/định tuyến (map_routing_feature.md). Toạ độ tách riêng khỏi
    # `area` (chuỗi khu vực tự do đã có sẵn) vì `area` không định vị được trên
    # bản đồ, còn toạ độ thì không thay được cho tên khu vực khi hiển thị.
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    current_address: Optional[str] = None

    # Mục F — khách chủ động chấp nhận trễ tối đa bao nhiêu phút so với SLA
    # gốc (hỏi 2 bước, optional). CHỈ dùng ở ranker.py, KHÔNG ảnh hưởng
    # impact_analysis/sla_breach thật.
    customer_accepted_delay_min: Optional[int] = None


class ExceptionUpdate(BaseModel):
    """Sửa lại 1 ngoại lệ đã tạo (việc 5, 2026-09-04).

    CÙNG bộ field đầu vào như `ExceptionCreate` TRỪ `schedule_id` — sửa ngoại
    lệ sang chuyến khác không phải "sửa thông tin nhập sai" mà là ngoại lệ
    khác hẳn, xoá cái cũ rồi tạo mới mới đúng. Sau khi sửa, backend chạy lại
    y hệt luồng lúc tạo (classify_sub_type -> analyze_impact ->
    calculate_severity) rồi sinh job phân tích AI mới.
    """

    exception_group: str
    answer_key: str
    # Tách từ `has_injury` gộp chung (đợt 12, việc 2): tài xế bị thương thì
    # CHẮC CHẮN không lái tiếp được, người khác bị thương thì không suy ra
    # được điều đó — 2 tín hiệu này dẫn tới phương án khác hẳn nhau.
    driver_injured: Optional[bool] = None
    other_injured: Optional[bool] = None
    area: Optional[str] = None
    description: Optional[str] = None

    from_stop_order: int = 1
    to_stop_order: Optional[int] = None
    delay_minutes: int = 0

    departure_delay_min: Optional[int] = None
    driver_contact_lost_min: Optional[int] = None
    estimated_traffic_duration_min: Optional[int] = None
    is_repeat_delivery: Optional[bool] = None
    has_time_conflict: Optional[bool] = None
    new_location_distance_km: Optional[float] = None
    estimated_repair_min: Optional[int] = None

    # --- Câu trả lời phụ, redesign 2026-09-08 (exception_intake_review.md) ---
    # Mỗi field chỉ có nghĩa với đúng 1-2 sub_type; dispatcher bỏ trống phần
    # còn lại. Tất cả đều Optional vì form chỉ hiện đúng câu hỏi của sub_type
    # đang chọn — bắt buộc ở đây sẽ chặn luôn 10 sub_type còn lại.
    #
    # delay:
    departure_status: Optional[str] = None          # chua_xuat_phat | da_xuat_phat
    late_departure_cause: Optional[str] = None      # chỉ khi chua_xuat_phat
    estimated_departure_delay_min: Optional[int] = None  # ƯỚC TÍNH, chưa xảy ra xong
    departed_late_cause: Optional[str] = None       # chỉ khi da_xuat_phat, tuỳ chọn
    # customer_reject:
    contacted_customer: Optional[bool] = None       # customer_absent
    customer_request: Optional[str] = None          # hen_giao_lai | doi_dia_diem | huy
    dispute_type: Optional[str] = None              # customer_dispute
    # vehicle_issue:
    can_transfer_cargo_safely: Optional[str] = None  # co | khong | chua_chac (major_breakdown)
    vehicle_movable: Optional[bool] = None          # accident
    # Vị trí xe hiện tại — dùng chung road_closed + major_breakdown, nuôi tính
    # năng bản đồ/định tuyến (map_routing_feature.md). Toạ độ tách riêng khỏi
    # `area` (chuỗi khu vực tự do đã có sẵn) vì `area` không định vị được trên
    # bản đồ, còn toạ độ thì không thay được cho tên khu vực khi hiển thị.
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    current_address: Optional[str] = None

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
    # Tín hiệu định lượng đã nhập lúc tạo/sửa — form sửa nạp lại từ đây.
    input_context: Optional[dict] = None
    status: str

    model_config = {"from_attributes": True}
