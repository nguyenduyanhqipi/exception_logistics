"""Rule engine — phân loại sub_type và tính severity (mục 5 TECHNICAL_SPEC.md).

KHÔNG dùng LLM để phân loại — dispatcher trả lời câu hỏi trắc nghiệm cố định,
rule engine chốt sub_type/severity tất định (deterministic), LLM chỉ tham gia
ở bước sinh phương án (option_generator.py, Giai đoạn 6).
"""

# Đáp án câu hỏi trắc nghiệm (mục 5.1) -> sub_type. Đây là "answer_key" cố định
# dùng làm hợp đồng API giữa form frontend (Giai đoạn 8) và rule engine —
# KHÔNG phải nội dung câu hỏi hiển thị (nội dung tiếng Việt nằm ở frontend).
ANSWER_TO_SUBTYPE = {
    "delay": {
        # Tách 1 câu hỏi cũ ("xe đã xuất phát chưa") thành 2 đáp án cùng trỏ về
        # `late_departure`: cùng bản chất "xuất phát trễ" nên KHÔNG tách sub_type,
        # nhưng 2 trạng thái cần 2 con số khác nhau (ước tính vs thực tế) — phân
        # biệt bằng field `departure_status` trong input_context, không phải bằng
        # sub_type riêng.
        "chua_xuat_phat": "late_departure",
        "da_xuat_phat_nhung_tre": "late_departure",
        # THU HẸP NGHĨA (2026-09-08): chỉ còn đúng nghĩa "mất liên lạc". Nhánh cũ
        # "vẫn liên lạc được nhưng chậm không rõ lý do" bị bỏ vì lý do đó
        # dispatcher hỏi thẳng tài xế là biết ngay, rồi tự xếp vào 1 trong 2 đáp
        # án trên (hoặc nhóm khác) — giữ lại chỉ tạo 1 thùng rác phân loại.
        "mat_lien_lac_tai_xe": "unknown_delay",
    },
    "road_block": {
        "un_tac_van_di_duoc": "traffic_jam",
        "chan_hoan_toan": "road_closed",
    },
    "customer_reject": {
        "khong_co_nguoi_nhan": "customer_absent",
        "tu_choi_nhan_tranh_chap": "customer_dispute",
    },
    "customer_change": {
        "doi_gio_nhan": "change_time",
        "doi_dia_diem": "change_location",
    },
    "vehicle_issue": {
        "hong_nhe_van_chay_duoc": "minor_breakdown",
        "hong_nang_phai_dung": "major_breakdown",
        "tai_nan": "accident",
    },
}

# 3 sub_type bị RETIRE trong đợt redesign 2026-09-08 — KHÔNG còn tạo mới được
# (đã biến khỏi ANSWER_TO_SUBTYPE ở trên), nhưng vẫn tồn tại trong dữ liệu CŨ
# (`exceptions` thật + case bank lịch sử của RAG), nên mọi chỗ HIỂN THỊ vẫn phải
# đọc được chúng (frontend/src/labels.ts giữ nguyên nhãn tiếng Việt, prompt
# tương ứng trong scripts/seed_prompts.py cũng giữ để ngoại lệ cũ còn sinh lại
# phương án được):
# - `slow_loading`  -> hoà vào `late_departure` dưới dạng 1 lựa chọn của field
#                      `late_departure_cause` ("chậm bốc xếp tại kho").
# - `wrong_address` -> 2 nhánh xử lý của nó đã có đường đi rõ qua luồng mới của
#                      `customer_absent` (liên lạc được -> đổi địa điểm; không
#                      liên lạc được -> mang về), không cần sub_type riêng.
# - `cancel_order`  -> đơn ĐÃ BIẾT CHẮC bị huỷ không cần AI sinh phương án; đó
#                      là thao tác xoá điểm giao khỏi chuyến
#                      (DELETE /api/schedules/{id}/stops/{stop_id}), không phải
#                      "ngoại lệ cần quyết định".
RETIRED_SUB_TYPES = ("slow_loading", "wrong_address", "cancel_order")

VALID_EXCEPTION_GROUPS = set(ANSWER_TO_SUBTYPE)

# Đáp án phụ "Khách muốn xử lý thế nào?" của `customer_absent` -> sub_type GỢI Ý.
# `huy` cố ý KHÔNG có gợi ý: huỷ đơn không còn là ngoại lệ (xem RETIRED_SUB_TYPES),
# frontend chỉ dẫn dispatcher sang thao tác xoá điểm giao.
CUSTOMER_REQUEST_TO_SUBTYPE = {
    "hen_giao_lai": "change_time",
    "doi_dia_diem": "change_location",
    "huy": None,
}


class InvalidAnswerError(ValueError):
    pass


def classify_sub_type(
    exception_group: str,
    answer_key: str,
    customer_request: str | None = None,
) -> dict:
    """Chốt sub_type từ câu trả lời trắc nghiệm (mục 5.1).

    Trả về dict {sub_type, suggested_sub_type}:
    - `suggested_sub_type`: chỉ có giá trị khi `customer_absent` mà dispatcher
      liên lạc được với khách và khách nói rõ muốn gì (`customer_request`) —
      gợi ý dispatcher cân nhắc đổi sang `change_time`/`change_location`, KHÔNG
      tự động đổi `sub_type` (spec mục 5.1: "không đổi sub_type"). Cơ chế này
      trước đây phục vụ câu hỏi phụ `depot_on_time` -> `slow_loading`; từ
      2026-09-08 `slow_loading` retire nên cùng cơ chế chuyển sang phục vụ
      luồng khách vắng mặt.

    Hàm này KHÔNG sinh câu mô tả cho `exceptions.description`. Mọi câu trả lời
    phụ đều đi thẳng vào `input_context` -> `calculate_severity()` và/hoặc
    CONTEXT gửi LLM (option_generator.py::_INPUT_CONTEXT_SIGNALS) dưới dạng
    structured field; kể lại chúng bằng lời trong `description` chỉ tạo nguồn
    sự thật thứ hai, lệch pha ngay khi dispatcher sửa ngoại lệ.
    """
    if exception_group not in VALID_EXCEPTION_GROUPS:
        raise InvalidAnswerError(f"exception_group không hợp lệ: {exception_group}")

    mapping = ANSWER_TO_SUBTYPE[exception_group]
    if answer_key not in mapping:
        raise InvalidAnswerError(
            f"answer_key '{answer_key}' không hợp lệ cho exception_group '{exception_group}'"
        )

    sub_type = mapping[answer_key]
    result = {"sub_type": sub_type, "suggested_sub_type": None}

    if sub_type == "customer_absent" and customer_request:
        result["suggested_sub_type"] = CUSTOMER_REQUEST_TO_SUBTYPE.get(customer_request)

    return result


SEVERITY_ORDER = {"warning": 0, "serious": 1, "critical": 2}


def _escalate(current: str, target: str) -> str:
    return current if SEVERITY_ORDER[current] >= SEVERITY_ORDER[target] else target


def _step_up(current: str) -> str:
    """Nâng đúng 1 bậc (warning->serious). serious/critical giữ nguyên — dùng
    cho quy tắc toàn cục #4 (mục 5.2: "nâng tối thiểu 1 bậc")."""
    if current == "warning":
        return "serious"
    return current


# Ngưỡng mặc định (mục 5.2) — company có thể tùy chỉnh qua `rule_versions`
# (Settings), các hàm dưới nhận `thresholds` làm tham số, KHÔNG hardcode giá
# trị trong logic so sánh.
DEFAULT_THRESHOLDS = {
    "late_departure_delay_min": 30,
    "unknown_delay_contact_lost_min": 15,
    "traffic_jam_duration_min": 60,
    "change_location_distance_km": 5,
    "priority_sla_penalty_vnd": 500_000,
    "minor_breakdown_repair_min": 30,
    "downstream_stops_threshold": 3,
    "critical_deadline_min": 30,
    "serious_deadline_min": 90,
    "bulky_cargo_multiplier": 1.7,
}

# Severity nền cố định cho sub_type "cố định" (không phụ thuộc context).
_FIXED_SEVERITY = {
    "road_closed": "serious",
    "customer_dispute": "serious",
    "major_breakdown": "serious",
    "accident": "critical",
}


def _base_and_escalation(sub_type: str, context: dict, thresholds: dict) -> str:
    """Severity nền + leo thang theo sub_type (bảng mục 5.2), CHƯA áp quy tắc
    toàn cục."""
    if sub_type in _FIXED_SEVERITY:
        return _FIXED_SEVERITY[sub_type]

    downstream = context.get("downstream_stops_affected") or 0

    if sub_type == "late_departure":
        # Từ redesign 2026-09-08, `late_departure` gộp CẢ 2 trạng thái nên có 2
        # con số phút khác nhau, KHÔNG dùng lẫn: xe chưa lăn bánh thì con số
        # dispatcher nhập chỉ là ƯỚC TÍNH (`estimated_departure_delay_min`), xe
        # đã đi rồi thì là số THỰC TẾ đo được (`departure_delay_min`). Dùng
        # chung 1 ngưỡng vì bản chất tác động lên SLA là như nhau — cái khác là
        # độ tin cậy của con số, và đó là việc của AI/dispatcher, không phải của
        # severity.
        if context.get("departure_status") == "chua_xuat_phat":
            delay_min = context.get("estimated_departure_delay_min") or 0
        else:
            delay_min = context.get("departure_delay_min") or 0
        if delay_min > thresholds["late_departure_delay_min"] or downstream >= thresholds["downstream_stops_threshold"]:
            return "serious"
        return "warning"

    if sub_type == "unknown_delay":
        contact_lost_min = context.get("driver_contact_lost_min") or 0
        if contact_lost_min > thresholds["unknown_delay_contact_lost_min"]:
            return "serious"
        return "warning"

    if sub_type == "traffic_jam":
        duration_min = context.get("estimated_traffic_duration_min") or 0
        if duration_min > thresholds["traffic_jam_duration_min"]:
            return "serious"
        return "warning"

    if sub_type == "customer_absent":
        if context.get("has_priority_order") or context.get("is_repeat_delivery"):
            return "serious"
        return "warning"

    if sub_type == "change_time":
        if context.get("has_time_conflict"):
            return "serious"
        return "warning"

    if sub_type == "change_location":
        distance_km = context.get("new_location_distance_km") or 0
        if distance_km > thresholds["change_location_distance_km"]:
            return "serious"
        return "warning"

    if sub_type == "minor_breakdown":
        repair_min = context.get("estimated_repair_min") or 0
        if repair_min > thresholds["minor_breakdown_repair_min"]:
            return "serious"
        return "warning"

    if sub_type in RETIRED_SUB_TYPES:
        raise InvalidAnswerError(
            f"sub_type '{sub_type}' đã ngừng dùng từ 2026-09-08 (xem RETIRED_SUB_TYPES) — "
            "ngoại lệ cũ mang sub_type này chỉ để XEM, sửa lại phải chọn lại loại ngoại lệ mới"
        )
    raise InvalidAnswerError(f"sub_type không hợp lệ: {sub_type}")


def calculate_severity(sub_type: str, context: dict, thresholds: dict | None = None) -> str:
    """Tính severity cuối cùng: severity nền + leo thang theo sub_type, sau đó
    áp 4 quy tắc ghi đè toàn cục (mục 5.2) — escalation chỉ tăng, không giảm.

    `context` (mọi key optional, tùy sub_type):
    - departure_status, departure_delay_min, estimated_departure_delay_min,
      downstream_stops_affected, driver_contact_lost_min,
      estimated_traffic_duration_min, has_priority_order, is_repeat_delivery,
      has_time_conflict, new_location_distance_km, estimated_repair_min,
      has_injury, time_to_deadline_min
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    severity = _base_and_escalation(sub_type, context, thresholds)

    # Quy tắc toàn cục #1: an toàn con người -> critical, bất kể sub_type.
    if context.get("has_injury"):
        severity = "critical"

    # Quy tắc toàn cục #2 và #3: theo time_to_deadline_min.
    time_to_deadline = context.get("time_to_deadline_min")
    if time_to_deadline is not None:
        if time_to_deadline < thresholds["critical_deadline_min"]:
            severity = _escalate(severity, "critical")
        elif time_to_deadline <= thresholds["serious_deadline_min"]:
            severity = _escalate(severity, "serious")

    # Quy tắc toàn cục #4: downstream_stops_affected >= ngưỡng -> nâng 1 bậc.
    downstream = context.get("downstream_stops_affected") or 0
    if downstream >= thresholds["downstream_stops_threshold"]:
        severity = _step_up(severity)

    return severity
