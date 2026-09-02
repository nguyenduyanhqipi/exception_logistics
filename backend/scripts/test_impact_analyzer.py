"""Test độc lập impact_analyzer.py (BUILD_PLAN.md bước 4.2, 4.5) — dùng đúng
dữ liệu Kịch bản 1 mục 15 TECHNICAL_SPEC.md, đối chiếu số liệu tính tay.
"""
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.impact_analyzer import analyze_impact, filter_vehicles_by_payload
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


# Kịch bản 1 mục 15: B01, trễ xuất phát 45 phút, nhập ngoại lệ lúc 07:45.
stops = [
    {"stop_id": "s1", "stop_order": 1, "order_id": "DH-101", "eta": "07:30", "sla_deadline": "09:00", "priority_tier": "thuong", "sla_penalty": None},
    {"stop_id": "s2", "stop_order": 2, "order_id": "DH-102", "eta": "08:10", "sla_deadline": "09:30", "priority_tier": "thuong", "sla_penalty": None},
    {"stop_id": "s3", "stop_order": 3, "order_id": "DH-103", "eta": "08:50", "sla_deadline": "10:00", "priority_tier": "thuong", "sla_penalty": None},
]

result = analyze_impact(
    stops=stops,
    delay_minutes=45,
    from_stop_order=1,
    shift_date=date(2026, 9, 1),
    now=datetime(2026, 9, 1, 7, 45),
)

check("downstream_stops_affected = 3 (tính tay: cả 3 điểm đều bị ảnh hưởng)", result["downstream_stops_affected"], 3)
check("time_to_deadline_min = 75 (tính tay: 09:00 - 07:45 = 75 phút)", result["time_to_deadline_min"], 75)
check("has_priority_order = False (tính tay: cả 3 điểm priority_tier=thuong)", result["has_priority_order"], False)
check("stop1 sla_breach=False (tính tay: eta mới 08:15 < deadline 09:00)", result["affected_stops"][0]["sla_breach"], False)
check("stop2 sla_breach=False (tính tay: eta mới 08:55 < deadline 09:30)", result["affected_stops"][1]["sla_breach"], False)
check("stop3 sla_breach=False (tính tay: eta mới 09:35 < deadline 10:00)", result["affected_stops"][2]["sla_breach"], False)

severity = calculate_severity(
    "late_departure",
    {
        "departure_delay_min": 45,
        "downstream_stops_affected": result["downstream_stops_affected"],
        "time_to_deadline_min": result["time_to_deadline_min"],
        "has_priority_order": result["has_priority_order"],
    },
)
check("Kịch bản 1: severity cuối cùng = serious (3 lý do trùng, mục 15)", severity, "serious")

# ---- 4.5: xử lý tải trọng/hàng cồng kềnh (mục 5.4) ----
class FakeVehicle:
    def __init__(self, vehicle_id, max_payload_kg):
        self.vehicle_id = vehicle_id
        self.max_payload_kg = max_payload_kg


vehicles = [FakeVehicle("B01", 1000), FakeVehicle("C01", 1500)]

# cargo_type=bulky nhân hệ số 1.7: 500kg bulky -> 850kg hiệu dụng
stops_bulky = [{"volume_kg": 500, "cargo_type": "bulky"}]
filtered = filter_vehicles_by_payload(vehicles, stops_bulky)
check("bulky 500kg*1.7=850kg -> cả 2 xe đều đủ (1000,1500 >= 850)", sorted(v.vehicle_id for v in filtered), ["B01", "C01"])

stops_bulky_heavy = [{"volume_kg": 700, "cargo_type": "bulky"}]  # 700*1.7=1190kg
filtered2 = filter_vehicles_by_payload(vehicles, stops_bulky_heavy)
check("bulky 700kg*1.7=1190kg -> chỉ C01 (1500) đủ, B01 (1000) bị loại", [v.vehicle_id for v in filtered2], ["C01"])

# volume_kg bỏ trống hoàn toàn -> không loại xe nào
stops_no_volume = [{"volume_kg": None, "cargo_type": "normal"}]
filtered3 = filter_vehicles_by_payload(vehicles, stops_no_volume)
check("volume_kg bỏ trống hoàn toàn -> không loại xe nào", sorted(v.vehicle_id for v in filtered3), ["B01", "C01"])

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
