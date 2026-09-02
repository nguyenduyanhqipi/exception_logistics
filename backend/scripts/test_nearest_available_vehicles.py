"""Test core/conflict_detector.py::nearest_available_vehicles (bug thật phát
hiện lúc test 10.3 — resource_contention chưa bao giờ được nối dây, xem
BUILD_PLAN.md). Mock `distance_matrix` vì key Maps thật đang lỗi."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from models import Exception_, ImpactAnalysis, Schedule, User
import core.conflict_detector as cd

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


company_id = "00000000-0000-0000-0000-000000000001"
db = SessionLocal()
user = db.query(User).filter(User.company_id == company_id).first()

# Xe "bận" — tạo 1 exception active trên C01 để xác nhận bị loại khỏi candidate.
sched = Schedule(company_id=company_id, vehicle_id="C01", shift_date=__import__("datetime").date.today(), shift_label="ca_dem", trip_sequence=900, stops=[])
db.add(sched)
db.flush()
exc_busy = Exception_(company_id=company_id, schedule_id=sched.schedule_id, exception_group="vehicle_issue", sub_type="minor_breakdown", severity="warning", vehicle_id="C01", area="Test", reported_by=user.user_id, status="analyzing")
db.add(exc_busy)
db.commit()

FAKE_DISTANCES = {"C02": 15.0, "C03": 3.0, "C04": 8.0, "C05": 20.0}


def fake_distance_matrix(db, origin, destination):
    # Trả khoảng cách khác nhau tuỳ vehicle đang xét — mock qua closure biến
    # toàn cục _current_vehicle set trước mỗi lần gọi trong test dưới.
    return {"distance_km": FAKE_DISTANCES.get(_current[0], 99.0), "duration_min": 10}


_current = [None]

try:
    with patch("core.geocoder.distance_matrix", side_effect=fake_distance_matrix):
        # Không thể mock riêng theo từng vehicle vì code gọi distance_matrix(depot, exc_area)
        # không truyền vehicle_id -> đơn giản hoá: test bằng cách kiểm tra đúng
        # tập hợp candidate (loại đúng xe bận + chính mình), không kiểm tra thứ tự khoảng cách.
        result = cd.nearest_available_vehicles(db, company_id, {"vehicle_id": "B01", "area": "Cau Giay"}, top_n=3)
        print("candidates (own=B01, busy=C01):", result)
        check("Không chứa chính xe B01 (own_vehicle)", "B01" not in result)
        check("Không chứa C01 (đang bận)", "C01" not in result)
        check("Trả đúng top_n=3 xe", len(result) == 3)

        result2 = cd.nearest_available_vehicles(db, company_id, {"vehicle_id": "C02", "area": "Cau Giay"}, top_n=2)
        check("Không chứa chính xe C02 khi own=C02", "C02" not in result2)

    # Test graceful degradation: geocoder lỗi hoàn toàn -> vẫn trả đủ top_n xe
    # (không loại xe nào vì thiếu dữ liệu khoảng cách, đúng mục 5.4/14).
    with patch("core.geocoder.distance_matrix", return_value=None):
        result3 = cd.nearest_available_vehicles(db, company_id, {"vehicle_id": "B01", "area": "Cau Giay"}, top_n=2)
        check("Geocoder lỗi hoàn toàn -> vẫn trả đủ top_n=2 (fallback theo vehicle_id)", len(result3) == 2)

    # Test resource_contention thật qua detect_conflict với hàm đã inject
    with patch("core.geocoder.distance_matrix", side_effect=fake_distance_matrix):
        exc_a = {"vehicle_id": "B01", "area": "Cau Giay", "sub_type": "minor_breakdown", "severity": "serious", "schedule_id": "sa"}
        exc_b = {"vehicle_id": "C02", "area": "Nam Tu Liem", "sub_type": "major_breakdown", "severity": "serious", "schedule_id": "sb"}
        fn = lambda e, top_n: cd.nearest_available_vehicles(db, company_id, e, top_n)
        mode, conflicting, signals = cd.detect_conflict(exc_a, [exc_b], nearest_available_vehicles_fn=fn)
        print("mode:", mode, "signals:", signals)
        check("2 xe khác nhau, cùng cần thay thế, candidate trùng nhau -> combined qua resource_contention", mode == "combined" and "resource_contention" in signals)

finally:
    db.query(Exception_).filter(Exception_.exception_id == exc_busy.exception_id).delete(synchronize_session=False)
    db.query(Schedule).filter(Schedule.schedule_id == sched.schedule_id).delete(synchronize_session=False)
    db.commit()
    db.close()
    print("Đã dọn dữ liệu test.")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
