"""Test độc lập rule_engine.py (BUILD_PLAN.md bước 4.1, 4.3, 4.4) — không cần
DB/UI. Chạy: python scripts/test_rule_engine.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.rule_engine import calculate_severity, classify_sub_type

passed = 0
failed = 0


def check(label, actual, expected):
    global passed, failed
    ok = actual == expected
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {label}: got={actual!r} expected={expected!r}")
    if ok:
        passed += 1
    else:
        failed += 1


# ---- 4.1: classify_sub_type cho cả 5 nhóm ----
check("delay/chua_xuat_phat", classify_sub_type("delay", "chua_xuat_phat")["sub_type"], "late_departure")
check("delay/dang_boc_do_cham", classify_sub_type("delay", "dang_boc_do_cham")["sub_type"], "slow_loading")
check(
    "delay/dang_di_chuyen_cham_khong_ro_ly_do",
    classify_sub_type("delay", "dang_di_chuyen_cham_khong_ro_ly_do")["sub_type"],
    "unknown_delay",
)
check("road_block/un_tac_van_di_duoc", classify_sub_type("road_block", "un_tac_van_di_duoc")["sub_type"], "traffic_jam")
check("road_block/chan_hoan_toan", classify_sub_type("road_block", "chan_hoan_toan")["sub_type"], "road_closed")
check(
    "customer_reject/khong_co_nguoi_nhan",
    classify_sub_type("customer_reject", "khong_co_nguoi_nhan")["sub_type"],
    "customer_absent",
)
check(
    "customer_reject/tu_choi_nhan_tranh_chap",
    classify_sub_type("customer_reject", "tu_choi_nhan_tranh_chap")["sub_type"],
    "customer_dispute",
)
check("customer_reject/sai_dia_chi", classify_sub_type("customer_reject", "sai_dia_chi")["sub_type"], "wrong_address")
check("customer_change/doi_gio_nhan", classify_sub_type("customer_change", "doi_gio_nhan")["sub_type"], "change_time")
check("customer_change/doi_dia_diem", classify_sub_type("customer_change", "doi_dia_diem")["sub_type"], "change_location")
check("customer_change/huy_don", classify_sub_type("customer_change", "huy_don")["sub_type"], "cancel_order")
check(
    "vehicle_issue/hong_nhe_van_chay_duoc",
    classify_sub_type("vehicle_issue", "hong_nhe_van_chay_duoc")["sub_type"],
    "minor_breakdown",
)
check(
    "vehicle_issue/hong_nang_phai_dung",
    classify_sub_type("vehicle_issue", "hong_nang_phai_dung")["sub_type"],
    "major_breakdown",
)
check("vehicle_issue/tai_nan", classify_sub_type("vehicle_issue", "tai_nan")["sub_type"], "accident")

# Câu hỏi phụ delay: depot_on_time=True -> suggested_sub_type=slow_loading, KHÔNG đổi sub_type
r = classify_sub_type("delay", "chua_xuat_phat", depot_on_time=True)
check("delay câu phụ (đến kho đúng giờ) sub_type giữ nguyên", r["sub_type"], "late_departure")
check("delay câu phụ (đến kho đúng giờ) suggested", r["suggested_sub_type"], "slow_loading")
r2 = classify_sub_type("delay", "chua_xuat_phat", depot_on_time=False)
check("delay câu phụ (đến kho trễ) suggested=None", r2["suggested_sub_type"], None)

# ---- 4.3 + 4.4: severity theo bảng mục 5.2 + 14 sub-type, cả 2 phía ngưỡng ----
check("late_departure delay=30 (không escalate)", calculate_severity("late_departure", {"departure_delay_min": 30, "downstream_stops_affected": 0}), "warning")
check("late_departure delay=31 (escalate)", calculate_severity("late_departure", {"departure_delay_min": 31, "downstream_stops_affected": 0}), "serious")
check("late_departure downstream=3 (escalate)", calculate_severity("late_departure", {"departure_delay_min": 0, "downstream_stops_affected": 3}), "serious")
check("late_departure downstream=2 (không escalate)", calculate_severity("late_departure", {"departure_delay_min": 0, "downstream_stops_affected": 2}), "warning")

check("slow_loading downstream=2", calculate_severity("slow_loading", {"downstream_stops_affected": 2}), "warning")
check("slow_loading downstream=3", calculate_severity("slow_loading", {"downstream_stops_affected": 3}), "serious")

check("unknown_delay contact_lost=15 (không escalate)", calculate_severity("unknown_delay", {"driver_contact_lost_min": 15}), "warning")
check("unknown_delay contact_lost=16 (escalate)", calculate_severity("unknown_delay", {"driver_contact_lost_min": 16}), "serious")

check("traffic_jam duration=60 (không escalate)", calculate_severity("traffic_jam", {"estimated_traffic_duration_min": 60}), "warning")
check("traffic_jam duration=61 (escalate)", calculate_severity("traffic_jam", {"estimated_traffic_duration_min": 61}), "serious")

check("road_closed (cố định serious)", calculate_severity("road_closed", {}), "serious")

check("customer_absent thường (không escalate)", calculate_severity("customer_absent", {}), "warning")
check("customer_absent has_priority_order (escalate)", calculate_severity("customer_absent", {"has_priority_order": True}), "serious")
check("customer_absent giao lại lần 2 (escalate)", calculate_severity("customer_absent", {"is_repeat_delivery": True}), "serious")

check("customer_dispute (cố định serious)", calculate_severity("customer_dispute", {}), "serious")

check("wrong_address 5km (không escalate)", calculate_severity("wrong_address", {"new_address_distance_km": 5}), "warning")
check("wrong_address 5.1km (escalate)", calculate_severity("wrong_address", {"new_address_distance_km": 5.1}), "serious")

check("change_time không xung đột", calculate_severity("change_time", {"has_time_conflict": False}), "warning")
check("change_time có xung đột (escalate)", calculate_severity("change_time", {"has_time_conflict": True}), "serious")

check("change_location 5km (không escalate)", calculate_severity("change_location", {"new_location_distance_km": 5}), "warning")
check("change_location 5.1km (escalate)", calculate_severity("change_location", {"new_location_distance_km": 5.1}), "serious")

check("cancel_order thường", calculate_severity("cancel_order", {}), "warning")
check("cancel_order has_priority_order (escalate)", calculate_severity("cancel_order", {"has_priority_order": True}), "serious")

check("minor_breakdown repair=30 (không escalate)", calculate_severity("minor_breakdown", {"estimated_repair_min": 30}), "warning")
check("minor_breakdown repair=31 (escalate)", calculate_severity("minor_breakdown", {"estimated_repair_min": 31}), "serious")

check("major_breakdown (cố định serious)", calculate_severity("major_breakdown", {}), "serious")

check("accident không thương (vẫn critical, cố định)", calculate_severity("accident", {"has_injury": False}), "critical")
check("accident có thương (critical)", calculate_severity("accident", {"has_injury": True}), "critical")

# ---- 4.4: 4 quy tắc ghi đè toàn cục, test riêng lẻ ----
check("Quy tắc #1: has_injury -> critical bất kể sub_type", calculate_severity("late_departure", {"has_injury": True, "departure_delay_min": 0, "downstream_stops_affected": 0}), "critical")
check("Quy tắc #2: time_to_deadline<30 -> critical", calculate_severity("customer_absent", {"time_to_deadline_min": 25}), "critical")
check("Quy tắc #2 biên: time_to_deadline=29 -> critical", calculate_severity("customer_absent", {"time_to_deadline_min": 29}), "critical")
check("Quy tắc #3: time_to_deadline=30 -> serious (sàn)", calculate_severity("customer_absent", {"time_to_deadline_min": 30}), "serious")
check("Quy tắc #3: time_to_deadline=90 -> serious (sàn)", calculate_severity("customer_absent", {"time_to_deadline_min": 90}), "serious")
check("Quy tắc #3 biên ngoài: time_to_deadline=91 -> warning (không escalate)", calculate_severity("customer_absent", {"time_to_deadline_min": 91}), "warning")
check("Quy tắc #3 không hạ critical xuống", calculate_severity("accident", {"time_to_deadline_min": 200}), "critical")
check("Quy tắc #4: downstream>=3 nâng 1 bậc (warning->serious)", calculate_severity("customer_absent", {"downstream_stops_affected": 3}), "serious")
check("Quy tắc #4 không đẩy serious lên critical", calculate_severity("road_closed", {"downstream_stops_affected": 3}), "serious")
check("Quy tắc #4 không đẩy critical", calculate_severity("accident", {"downstream_stops_affected": 3, "has_injury": True}), "critical")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
