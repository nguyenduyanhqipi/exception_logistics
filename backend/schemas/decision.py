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


def _validate_outcome_fields(delivered_on_time: bool, delay_minutes: "int | None", actual_cost: Decimal):
    """Ràng buộc chung cho tạo MỚI và SỬA outcome (việc 2, 2026-09-04).

    Trước đây mọi field đều Optional nên ghi được 1 outcome rỗng hoàn toàn —
    exception vẫn chuyển sang "đã xử lý" mà KPI (on_time_rate, total_actual_cost)
    không có gì để tính. Nay bắt buộc đủ dữ liệu ngay từ tầng schema.
    """
    if delivered_on_time is False:
        if delay_minutes is None:
            raise ValueError("Giao muộn giờ thì phải nhập số phút muộn")
        if delay_minutes <= 0:
            raise ValueError("Số phút muộn phải lớn hơn 0")
    else:
        if delay_minutes is not None:
            raise ValueError("Giao đúng giờ thì không được nhập số phút muộn")
    if actual_cost < 0:
        raise ValueError("Chi phí thực tế không được âm")


class OutcomeCreate(BaseModel):
    decision_id: UUID
    # BẮT BUỘC (không Optional): đây là dữ liệu nuôi KPI "Tỷ lệ giao đúng hạn".
    delivered_on_time: bool
    delay_minutes: Optional[int] = None
    # 0 hợp lệ (xử lý xong mà không tốn thêm chi phí), âm thì không.
    actual_cost: Decimal
    notes: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _check(self):
        _validate_outcome_fields(self.delivered_on_time, self.delay_minutes, self.actual_cost)
        return self


class OutcomeUpdate(BaseModel):
    """Sửa 1 outcome đã ghi. Gửi ĐỦ bộ field như lúc tạo (không phải patch
    từng field lẻ) để `_validate_outcome_fields` kiểm tra được tính nhất quán
    giữa `delivered_on_time` và `delay_minutes`.

    Ràng buộc CHIỀU đổi `delivered_on_time` (False -> True bị cấm) không nằm ở
    đây vì cần biết giá trị CŨ trong DB — kiểm ở api/decisions.py.
    """

    delivered_on_time: bool
    delay_minutes: Optional[int] = None
    actual_cost: Decimal
    notes: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _check(self):
        _validate_outcome_fields(self.delivered_on_time, self.delay_minutes, self.actual_cost)
        return self
