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


# Kết quả cuối cùng của outcome "kiểu khách từ chối nhận hàng" (Pha 2, đợt code
# 5). PHẢI khớp đúng frontend/src/components/OutcomeForm.tsx::RESOLUTION_OPTIONS.
RESOLUTION_TYPES = ("redelivered", "returned_to_depot", "cancelled", "other")

# Trong 4 lựa chọn trên, CHỈ "giao lại thành công" mới có ý nghĩa về thời gian
# ("trễ bao nhiêu so với lần giao đầu"); 3 lựa chọn còn lại thì hàng không hề
# được giao nên mọi con số phút đều vô nghĩa.
RESOLUTION_WITH_DELAY = "redelivered"


def _validate_outcome_fields(
    delivered_on_time: "bool | None",
    delay_minutes: "int | None",
    actual_cost: Decimal,
    resolution_type: "str | None" = None,
):
    """Ràng buộc chung cho tạo MỚI và SỬA outcome (việc 2, 2026-09-04).

    Trước đây mọi field đều Optional nên ghi được 1 outcome rỗng hoàn toàn —
    exception vẫn chuyển sang "đã xử lý" mà KPI (on_time_rate, total_actual_cost)
    không có gì để tính. Nay bắt buộc đủ dữ liệu ngay từ tầng schema.

    Từ Pha 2 (đợt code 5) có 2 KIỂU outcome loại trừ nhau, `resolution_type`
    quyết định đang ở kiểu nào:
    - NULL  -> kiểu TIẾN ĐỘ (9/11 sub_type): `delivered_on_time` bắt buộc, cặp
      ràng buộc `delivered_on_time`/`delay_minutes` giữ nguyên như cũ.
    - có giá trị -> kiểu KHÁCH TỪ CHỐI (customer_absent/customer_dispute): form
      không hỏi đúng giờ/muộn giờ nữa nên `delivered_on_time` PHẢI để trống —
      tự suy ra giá trị hộ dispatcher là bịa số liệu cho KPI on_time_rate.
      `delay_minutes` chỉ được phép khi "giao lại thành công", và là TUỲ CHỌN
      (không phải trọng tâm của kiểu này).
    """
    if actual_cost < 0:
        raise ValueError("Chi phí thực tế không được âm")

    if resolution_type is not None:
        if resolution_type not in RESOLUTION_TYPES:
            raise ValueError(f"resolution_type không hợp lệ: {resolution_type}")
        if delivered_on_time is not None:
            raise ValueError(
                "Kết quả kiểu 'khách từ chối nhận hàng' không dùng đúng giờ/muộn giờ — "
                "để trống delivered_on_time"
            )
        if delay_minutes is not None:
            if resolution_type != RESOLUTION_WITH_DELAY:
                raise ValueError("Chỉ 'giao lại thành công' mới nhập được số phút trễ")
            if delay_minutes <= 0:
                raise ValueError("Số phút trễ phải lớn hơn 0")
        return

    if delivered_on_time is None:
        raise ValueError("Phải cho biết giao đúng giờ hay muộn giờ")
    if delivered_on_time is False:
        if delay_minutes is None:
            raise ValueError("Giao muộn giờ thì phải nhập số phút muộn")
        if delay_minutes <= 0:
            raise ValueError("Số phút muộn phải lớn hơn 0")
    else:
        if delay_minutes is not None:
            raise ValueError("Giao đúng giờ thì không được nhập số phút muộn")


class OutcomeCreate(BaseModel):
    decision_id: UUID
    # Optional Ở TẦNG KIỂU nhưng vẫn BẮT BUỘC với outcome kiểu tiến độ (nuôi KPI
    # "Tỷ lệ giao đúng hạn") — `_validate_outcome_fields` ép theo `resolution_type`.
    delivered_on_time: Optional[bool] = None
    delay_minutes: Optional[int] = None
    # 0 hợp lệ (xử lý xong mà không tốn thêm chi phí), âm thì không.
    actual_cost: Decimal
    resolution_type: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _check(self):
        _validate_outcome_fields(
            self.delivered_on_time, self.delay_minutes, self.actual_cost, self.resolution_type
        )
        return self


class OutcomeUpdate(BaseModel):
    """Sửa 1 outcome đã ghi. Gửi ĐỦ bộ field như lúc tạo (không phải patch
    từng field lẻ) để `_validate_outcome_fields` kiểm tra được tính nhất quán
    giữa `delivered_on_time` và `delay_minutes`.

    Ràng buộc CHIỀU đổi `delivered_on_time` (False -> True bị cấm) không nằm ở
    đây vì cần biết giá trị CŨ trong DB — kiểm ở api/decisions.py.
    """

    delivered_on_time: Optional[bool] = None
    delay_minutes: Optional[int] = None
    actual_cost: Decimal
    resolution_type: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _check(self):
        _validate_outcome_fields(
            self.delivered_on_time, self.delay_minutes, self.actual_cost, self.resolution_type
        )
        return self
