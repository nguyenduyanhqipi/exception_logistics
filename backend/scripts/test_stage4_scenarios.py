"""Test tổng Giai đoạn 4 (BUILD_PLAN.md bước 4.8) — chạy rule engine thuần
(chưa cần AI/UI) trên cả 6 kịch bản demo mục 15 TECHNICAL_SPEC.md, đối chiếu
với "Kết quả rule engine kỳ vọng" ghi trong spec. PHẢI khớp 100%.
"""
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.conflict_detector import detect_conflict
from core.impact_analyzer import analyze_impact
from core.rule_engine import calculate_severity

passed = 0
failed = 0


def check(label, actual, expected):
    global passed, failed
    ok = actual == expected
    print(f"[{'OK' if ok else 'FAIL'}] {label}: got={actual!r} expected={expected!r}")
    if ok:
        passed += 1
    else:
        failed += 1


DAY = date(2026, 9, 1)

# ============================================================
# Kịch bản 1 — delay/late_departure, B01, leo thang serious (3 lý do trùng)
# ============================================================
stops1 = [
    {"stop_order": 1, "eta": "07:30", "sla_deadline": "09:00", "priority_tier": "thuong"},
    {"stop_order": 2, "eta": "08:10", "sla_deadline": "09:30", "priority_tier": "thuong"},
    {"stop_order": 3, "eta": "08:50", "sla_deadline": "10:00", "priority_tier": "thuong"},
]
impact1 = analyze_impact(stops1, delay_minutes=45, from_stop_order=1, shift_date=DAY, now=datetime(2026, 9, 1, 7, 45))
sev1 = calculate_severity("late_departure", {"departure_delay_min": 45, **impact1})
check("KB1 downstream_stops_affected=3", impact1["downstream_stops_affected"], 3)
check("KB1 time_to_deadline_min=75", impact1["time_to_deadline_min"], 75)
check("KB1 has_priority_order=False", impact1["has_priority_order"], False)
check("KB1 severity=serious", sev1, "serious")

# ============================================================
# Kịch bản 2 — road_block/road_closed, B03, leo thang critical (deadline sát)
# ============================================================
stops2 = [
    {"stop_order": 1, "eta": "14:30", "sla_deadline": "15:00", "priority_tier": "thuong"},
    {"stop_order": 2, "eta": "15:10", "sla_deadline": "16:00", "priority_tier": "thuong"},
]
impact2 = analyze_impact(stops2, delay_minutes=0, from_stop_order=1, shift_date=DAY, now=datetime(2026, 9, 1, 14, 35))
sev2 = calculate_severity("road_closed", impact2)
check("KB2 downstream_stops_affected=2", impact2["downstream_stops_affected"], 2)
check("KB2 time_to_deadline_min=25", impact2["time_to_deadline_min"], 25)
check("KB2 severity=critical (road_closed serious cố định + deadline<30)", sev2, "critical")

# ============================================================
# Kịch bản 3 — customer_reject/customer_absent, B02, GIỮ warning (đối trọng KB1&2)
# Chỉ điểm giao thứ 2 bị ảnh hưởng, điểm 3 "Chưa bị ảnh hưởng" (ghi rõ trong spec)
# ============================================================
stops3 = [
    {"stop_order": 2, "eta": "09:40", "sla_deadline": "12:00", "priority_tier": "thuong"},
    {"stop_order": 3, "eta": "10:20", "sla_deadline": "13:00", "priority_tier": "thuong"},
]
impact3 = analyze_impact(stops3, delay_minutes=0, from_stop_order=2, to_stop_order=2, shift_date=DAY, now=datetime(2026, 9, 1, 9, 45))
sev3 = calculate_severity("customer_absent", {"has_priority_order": impact3["has_priority_order"], "is_repeat_delivery": False, **impact3})
check("KB3 chỉ 1 điểm bị ảnh hưởng (điểm 3 không tính)", impact3["downstream_stops_affected"], 1)
check("KB3 time_to_deadline_min=135", impact3["time_to_deadline_min"], 135)
check("KB3 severity=warning (không báo động giả)", sev3, "warning")

# ============================================================
# Kịch bản 4 — customer_change/cancel_order, B04, leo thang serious (giá trị đơn cao)
# ============================================================
stops4 = [{"stop_order": 1, "eta": "13:50", "sla_deadline": "15:30", "priority_tier": "hop_dong_phat", "sla_penalty": 600_000}]
impact4 = analyze_impact(stops4, delay_minutes=0, from_stop_order=1, to_stop_order=1, shift_date=DAY, now=datetime(2026, 9, 1, 13, 55))
sev4 = calculate_severity("cancel_order", {"has_priority_order": impact4["has_priority_order"], **impact4})
check("KB4 has_priority_order=True (hop_dong_phat + sla_penalty 600k>500k)", impact4["has_priority_order"], True)
check("KB4 time_to_deadline_min=95", impact4["time_to_deadline_min"], 95)
check("KB4 severity=serious", sev4, "serious")

# ============================================================
# Kịch bản 5 — vehicle_issue/major_breakdown, C02
# ============================================================
stops5 = [
    {"stop_order": 1, "eta": "10:15", "sla_deadline": "11:00", "priority_tier": "thuong", "volume_kg": 55, "cargo_type": "normal"},
    {"stop_order": 2, "eta": "10:45", "sla_deadline": "12:30", "priority_tier": "thuong", "volume_kg": 20, "cargo_type": "normal"},
]
impact5 = analyze_impact(stops5, delay_minutes=0, from_stop_order=1, shift_date=DAY, now=datetime(2026, 9, 1, 9, 50))
sev5 = calculate_severity("major_breakdown", impact5)
check("KB5 time_to_deadline_min=70", impact5["time_to_deadline_min"], 70)
check("KB5 severity=serious (sàn 30-90, không đẩy thêm critical)", sev5, "serious")
total_volume_kb5 = sum(s["volume_kg"] for s in stops5)
check("KB5 tổng volume_kg=75 (nhỏ hơn nhiều so với mọi max_payload_kg)", total_volume_kb5, 75)

# ============================================================
# Kịch bản bonus — 2 ngoại lệ cùng lúc, resource_contention -> combined
# ============================================================
stopsA = [
    {"stop_order": 1, "eta": "10:05", "sla_deadline": "11:00", "priority_tier": "thuong"},
    {"stop_order": 2, "eta": "10:05", "sla_deadline": "11:45", "priority_tier": "thuong"},
]
impactA = analyze_impact(stopsA, delay_minutes=0, from_stop_order=1, shift_date=DAY, now=datetime(2026, 9, 1, 10, 5))
sevA = calculate_severity("minor_breakdown", {"estimated_repair_min": 50, **impactA})
check("Bonus A (minor_breakdown sửa 50') severity=serious", sevA, "serious")

stopsB = [{"stop_order": 1, "eta": "10:08", "sla_deadline": "11:15", "priority_tier": "vip"}]
impactB = analyze_impact(stopsB, delay_minutes=0, from_stop_order=1, shift_date=DAY, now=datetime(2026, 9, 1, 10, 8))
sevB = calculate_severity("major_breakdown", {"has_priority_order": impactB["has_priority_order"], **impactB})
check("Bonus B (major_breakdown, vip) severity=serious (priority không đổi vì đã serious)", sevB, "serious")

exc_a = {"vehicle_id": "B01", "sub_type": "minor_breakdown", "severity": sevA}
exc_b = {"vehicle_id": "C02", "sub_type": "major_breakdown", "severity": sevB}


def nearest_vehicles_fn(exc, top_n):
    return ["C03", "C04"] if exc["vehicle_id"] == "B01" else ["C03", "C05"]


mode, _, signals = detect_conflict(exc_a, [exc_b], nearest_available_vehicles_fn=nearest_vehicles_fn)
check("Bonus: mode=combined (resource_contention qua C03)", mode, "combined")
check("Bonus: signals chứa resource_contention", "resource_contention" in signals, True)

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
print("\n=> Giai đoạn 4 khớp 100% với 'Kết quả rule engine kỳ vọng' của cả 6 kịch bản demo mục 15.")
