"""Test độc lập conflict_detector.py (BUILD_PLAN.md bước 4.6)."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.conflict_detector import detect_conflict

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


# 2 ngoại lệ không liên quan gì -> independent
new_exc = {"vehicle_id": "B02", "schedule_id": "sch-2", "sub_type": "customer_absent", "area": "Đống Đa", "reported_at": datetime(2026, 9, 1, 9, 0)}
existing = {"vehicle_id": "B01", "schedule_id": "sch-1", "sub_type": "late_departure", "area": "Cầu Giấy", "reported_at": datetime(2026, 9, 1, 7, 0)}
mode, conflict, signals = detect_conflict(new_exc, [existing])
check("2 ngoại lệ không liên quan -> independent", mode, "independent")

# same_vehicle -> combined
new_exc2 = {"vehicle_id": "B01", "schedule_id": "sch-3"}
existing_same_vehicle = {"vehicle_id": "B01", "schedule_id": "sch-1"}
mode, conflict, signals = detect_conflict(new_exc2, [existing_same_vehicle])
check("same_vehicle -> combined", mode, "combined")
check("same_vehicle signals đúng", signals, ["same_vehicle"])

# same_driver -> combined
new_exc3 = {"vehicle_id": "B02", "driver_name": "Nguyễn Văn An"}
existing_same_driver = {"vehicle_id": "B01", "driver_name": "Nguyễn Văn An"}
mode, _, signals = detect_conflict(new_exc3, [existing_same_driver])
check("same_driver -> combined", mode, "combined")

# same_stop -> combined
new_exc4 = {"vehicle_id": "B02", "schedule_id": "sch-1", "affected_stop_ids": ["s1", "s2"]}
existing_same_stop = {"vehicle_id": "B03", "schedule_id": "sch-1", "affected_stop_ids": ["s2", "s3"]}
mode, _, signals = detect_conflict(new_exc4, [existing_same_stop])
check("same_stop (cùng schedule, overlap stop_ids) -> combined", mode, "combined")

# resource_contention -> combined (Kịch bản bonus mục 15: A và B đều cần C03)
# A = minor_breakdown NHƯNG đã leo thang serious (sửa 50' > ngưỡng 30') nên
# vẫn tính needs_replacement_vehicle=True (xem docstring trong conflict_detector.py)
exc_a = {"vehicle_id": "B01", "sub_type": "minor_breakdown", "severity": "serious"}
exc_b = {"vehicle_id": "C02", "sub_type": "major_breakdown", "severity": "serious"}


def nearest_vehicles_fn(exc, top_n):
    # Cả A và B đều có C03 trong top candidate (mục 15 kịch bản bonus)
    if exc["vehicle_id"] == "B01":
        return ["C03", "C04"]
    if exc["vehicle_id"] == "C02":
        return ["C03", "C05"]
    return []


mode, _, signals = detect_conflict(exc_a, [exc_b], nearest_available_vehicles_fn=nearest_vehicles_fn)
check("resource_contention (kịch bản bonus, cả 2 cần C03) -> combined", mode, "combined")
check("resource_contention trong signals", "resource_contention" in signals, True)

# minor_breakdown còn warning (sự cố nhỏ thật sự) -> KHÔNG coi là cần xe thay thế
exc_a_warning = {"vehicle_id": "B01", "sub_type": "minor_breakdown", "severity": "warning"}
mode, _, signals = detect_conflict(exc_a_warning, [exc_b], nearest_available_vehicles_fn=nearest_vehicles_fn)
check("minor_breakdown còn warning -> không trigger resource_contention -> independent", mode, "independent")

# same_area_same_time CHỈ tham khảo, KHÔNG tự kích hoạt combined
new_exc5 = {"vehicle_id": "B04", "schedule_id": "sch-4", "area": "Cầu Giấy", "reported_at": datetime(2026, 9, 1, 10, 0)}
existing_area = {"vehicle_id": "B05", "schedule_id": "sch-5", "area": "Cầu Giấy", "reported_at": datetime(2026, 9, 1, 10, 10)}
mode, _, signals = detect_conflict(new_exc5, [existing_area])
check("same_area_same_time KHÔNG tự kích hoạt combined -> independent", mode, "independent")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
