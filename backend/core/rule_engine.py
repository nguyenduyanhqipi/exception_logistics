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
        "chua_xuat_phat": "late_departure",
        "dang_boc_do_cham": "slow_loading",
        "dang_di_chuyen_cham_khong_ro_ly_do": "unknown_delay",
    },
    "road_block": {
        "un_tac_van_di_duoc": "traffic_jam",
        "chan_hoan_toan": "road_closed",
    },
    "customer_reject": {
        "khong_co_nguoi_nhan": "customer_absent",
        "tu_choi_nhan_tranh_chap": "customer_dispute",
        "sai_dia_chi": "wrong_address",
    },
    "customer_change": {
        "doi_gio_nhan": "change_time",
        "doi_dia_diem": "change_location",
        "huy_don": "cancel_order",
    },
    "vehicle_issue": {
        "hong_nhe_van_chay_duoc": "minor_breakdown",
        "hong_nang_phai_dung": "major_breakdown",
        "tai_nan": "accident",
    },
}

VALID_EXCEPTION_GROUPS = set(ANSWER_TO_SUBTYPE)


class InvalidAnswerError(ValueError):
    pass


def classify_sub_type(
    exception_group: str,
    answer_key: str,
    depot_on_time: bool | None = None,
    has_injury: bool | None = None,
) -> dict:
    """Chốt sub_type từ câu trả lời trắc nghiệm (mục 5.1).

    Trả về dict {sub_type, suggested_sub_type, description_note}:
    - `suggested_sub_type`: chỉ có giá trị cho câu hỏi phụ của `delay` khi
      `depot_on_time=True` — gợi ý dispatcher cân nhắc đổi sang `slow_loading`,
      KHÔNG tự động đổi `sub_type` (spec mục 5.1: "không đổi sub_type").
    - `description_note`: câu trả lời phụ, dispatcher/LLM dùng để hiểu đúng
      gốc rễ — ghi vào `exceptions.description`, không dùng để phân loại.
    """
    if exception_group not in VALID_EXCEPTION_GROUPS:
        raise InvalidAnswerError(f"exception_group không hợp lệ: {exception_group}")

    mapping = ANSWER_TO_SUBTYPE[exception_group]
    if answer_key not in mapping:
        raise InvalidAnswerError(
            f"answer_key '{answer_key}' không hợp lệ cho exception_group '{exception_group}'"
        )

    sub_type = mapping[answer_key]
    result = {"sub_type": sub_type, "suggested_sub_type": None, "description_note": None}

    if exception_group == "delay" and sub_type == "late_departure" and depot_on_time is not None:
        if depot_on_time:
            result["suggested_sub_type"] = "slow_loading"
            result["description_note"] = (
                "Xe/tài xế có mặt tại kho đúng giờ nhưng xuất phát trễ — "
                "nguyên nhân thực chất là bốc hàng chậm tại kho."
            )
        else:
            result["description_note"] = "Xe/tài xế đến kho đã trễ (không phải do bốc hàng chậm)."

    if exception_group == "vehicle_issue" and sub_type == "accident" and has_injury is not None:
        result["description_note"] = "Có người bị thương." if has_injury else "Không có người bị thương."

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
    "wrong_address_distance_km": 5,
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
        delay_min = context.get("departure_delay_min") or 0
        if delay_min > thresholds["late_departure_delay_min"] or downstream >= thresholds["downstream_stops_threshold"]:
            return "serious"
        return "warning"

    if sub_type == "slow_loading":
        if downstream >= thresholds["downstream_stops_threshold"]:
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

    if sub_type == "wrong_address":
        distance_km = context.get("new_address_distance_km") or 0
        if distance_km > thresholds["wrong_address_distance_km"]:
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

    if sub_type == "cancel_order":
        if context.get("has_priority_order"):
            return "serious"
        return "warning"

    if sub_type == "minor_breakdown":
        repair_min = context.get("estimated_repair_min") or 0
        if repair_min > thresholds["minor_breakdown_repair_min"]:
            return "serious"
        return "warning"

    raise InvalidAnswerError(f"sub_type không hợp lệ: {sub_type}")


def calculate_severity(sub_type: str, context: dict, thresholds: dict | None = None) -> str:
    """Tính severity cuối cùng: severity nền + leo thang theo sub_type, sau đó
    áp 4 quy tắc ghi đè toàn cục (mục 5.2) — escalation chỉ tăng, không giảm.

    `context` (mọi key optional, tùy sub_type):
    - departure_delay_min, downstream_stops_affected, driver_contact_lost_min,
      estimated_traffic_duration_min, has_priority_order, is_repeat_delivery,
      new_address_distance_km, has_time_conflict, new_location_distance_km,
      estimated_repair_min, has_injury, time_to_deadline_min
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
