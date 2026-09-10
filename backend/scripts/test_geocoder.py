"""Test geocoder.py (BUILD_PLAN.md bước 7.2-7.4) — bản VietMap (đợt code 5, Pha 6).

4 việc test được:
  1. Cache logic (7.3) — mock httpx.get, xác nhận gọi API đúng 1 lần cho 2 lần
     geocode cùng địa chỉ.
  2. Graceful degradation khi KHÔNG có key (7.4) — không raise, trả None sạch
     sẽ.
  3. Graceful degradation khi CÓ key nhưng SAI/invalid (7.4, gọi API THẬT của
     VietMap với key rác để mô phỏng "sai key") — VietMap trả HTTP lỗi, code
     phải bắt và trả None, không crash.
  4. (chỉ chạy nếu `VIETMAP_API_KEY` thật có trong .env) geocode + distance_matrix
     THẬT trên địa chỉ Hà Nội thật — verify tọa độ hợp lý, khoảng cách/thời
     gian hợp lý, và cache distance_matrix không gọi lại API lần 2. Test này
     từng bị bỏ trống vì lúc viết ban đầu chưa có key thật — khi có key, đã
     lộ ra 2 bug thật trong `distance_matrix()` (đã sửa, xem docstring hàm
     đó trong `core/geocoder.py`): (a) truyền thẳng địa chỉ text vào
     DistanceMatrix trong khi API đó CHỈ nhận tọa độ `lat,lng` (khác Google);
     (b) check nhầm field `status` ở cấp response cao nhất.

ĐỔI SANG VIETMAP 2026-09-10: geocode thuận nay tốn 2 lệnh gọi HTTP
(`Search v4` trả ref_id -> `Place v4` trả lat/lng) chứ không phải 1 như Goong,
nên test cache bên dưới đếm 2 lượt gọi cho lần geocode đầu tiên.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from models import GeocodeCache
import core.geocoder as geocoder

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


db = SessionLocal()
test_address = "144 Xuan Thuy, Cau Giay, Ha Noi - TEST ONLY"
address_hash = geocoder._address_hash(test_address)

# Dọn trước phòng khi có rác từ lần chạy trước
db.query(GeocodeCache).filter(GeocodeCache.address_hash == address_hash).delete()
db.commit()

try:
    # ---- Test 1: cache logic (7.3), mock httpx.get + key giả để đi qua nhánh gọi API ----
    # VietMap geocode = 2 lệnh gọi: Search v4 (ra ref_id, KHÔNG có toạ độ) rồi
    # Place v4 (ra lat/lng). Mock phải trả đúng 2 shape đó theo thứ tự.
    def make_response(payload):
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json.return_value = payload
        return r

    search_response = make_response([{"ref_id": "geocode:FAKE-REF", "display": "144 Xuân Thuỷ"}])
    place_response = make_response({"lat": 21.0368, "lng": 105.7827, "display": "144 Xuân Thuỷ"})
    call_count = {"n": 0}

    def fake_get(url, *args, **kwargs):
        call_count["n"] += 1
        return place_response if "place" in str(url) else search_response

    with patch.dict(os.environ, {"VIETMAP_API_KEY": "fake-key-for-cache-test"}):
        with patch("core.geocoder.httpx.get", side_effect=fake_get):
            result1 = geocoder.geocode(db, test_address)
            check("Lần gọi 1: trả toạ độ đúng từ (mock) API", result1 == {"lat": 21.0368, "lng": 105.7827})
            check("Lần gọi 1: gọi httpx.get đúng 2 lần (Search v4 + Place v4)", call_count["n"] == 2)

            result2 = geocoder.geocode(db, test_address)
            check("Lần gọi 2 (cùng địa chỉ): trả đúng toạ độ từ cache", result2 == {"lat": 21.0368, "lng": 105.7827})
            check("Lần gọi 2: KHÔNG gọi lại httpx.get (vẫn 2 lần) — cache hoạt động", call_count["n"] == 2)

    cached_row = db.query(GeocodeCache).filter(GeocodeCache.address_hash == address_hash).first()
    check("geocode_cache có 1 dòng lưu đúng address_raw", cached_row is not None and cached_row.address_raw == test_address)

    # ---- Test 2: graceful degradation KHÔNG CÓ key (7.4) ----
    db.query(GeocodeCache).filter(GeocodeCache.address_hash == address_hash).delete()
    db.commit()
    with patch.dict(os.environ, {"VIETMAP_API_KEY": ""}):
        result_no_key = geocoder.geocode(db, test_address)
        check("Không có key: trả None, KHÔNG raise exception", result_no_key is None)

    # ---- Test 3: graceful degradation với key SAI thật sự (gọi VietMap API THẬT) ----
    with patch.dict(os.environ, {"VIETMAP_API_KEY": "invalid-key-does-not-exist-12345"}):
        try:
            result_bad_key = geocoder.geocode(db, test_address)
            check("Key sai (gọi VietMap API thật): trả None, KHÔNG raise exception", result_bad_key is None)
        except Exception as e:  # noqa: BLE001
            check(f"Key sai: KHÔNG được raise exception (đã raise: {e})", False)

        try:
            dm_bad_key = geocoder.distance_matrix(db, test_address, "72 Ho Tung Mau, Nam Tu Liem")
            check("distance_matrix với key sai: trả None, KHÔNG raise exception", dm_bad_key is None)
        except Exception as e:  # noqa: BLE001
            check(f"distance_matrix key sai: KHÔNG được raise (đã raise: {e})", False)

    # ---- Test 4: geocode + distance_matrix THẬT với key thật (nếu có) ----
    real_key = os.environ.get("VIETMAP_API_KEY")
    addr_a = "18 Pham Hung, Nam Tu Liem, Ha Noi - TEST ONLY"
    addr_b = "144 Xuan Thuy, Cau Giay, Ha Noi - TEST ONLY"
    hash_a, hash_b = geocoder._address_hash(addr_a), geocoder._address_hash(addr_b)
    db.query(GeocodeCache).filter(GeocodeCache.address_hash.in_([hash_a, hash_b])).delete(synchronize_session=False)
    db.commit()

    if not real_key:
        print("[SKIP] Test 4 (geocode/distance_matrix với key thật) — VIETMAP_API_KEY chưa cấu hình.")
    else:
        coords_a = geocoder.geocode(db, addr_a)
        check("Test 4: geocode địa chỉ A ra tọa độ hợp lý cho Hà Nội (lat 20.5-21.5, lng 105.3-106.1)", coords_a is not None and 20.5 <= coords_a["lat"] <= 21.5 and 105.3 <= coords_a["lng"] <= 106.1)

        coords_b = geocoder.geocode(db, addr_b)
        check("Test 4: geocode địa chỉ B ra tọa độ hợp lý cho Hà Nội", coords_b is not None and 20.5 <= coords_b["lat"] <= 21.5 and 105.3 <= coords_b["lng"] <= 106.1)

        real_call_count = {"n": 0}
        orig_get = geocoder.httpx.get

        def counting_get(*args, **kwargs):
            real_call_count["n"] += 1
            return orig_get(*args, **kwargs)

        with patch("core.geocoder.httpx.get", side_effect=counting_get):
            dm1 = geocoder.distance_matrix(db, addr_a, addr_b)
            check("Test 4: distance_matrix trả kết quả hợp lý (0 < km < 30, 0 < phút < 120 cho 2 điểm cùng Hà Nội)", dm1 is not None and 0 < dm1["distance_km"] < 30 and 0 < dm1["duration_min"] < 120)
            print("  distance_matrix thật:", dm1)
            calls_after_first = real_call_count["n"]

            dm2 = geocoder.distance_matrix(db, addr_a, addr_b)
            check("Test 4: distance_matrix lần 2 (cùng cặp địa chỉ) lấy từ cache, KHÔNG gọi lại API", dm2 == dm1 and real_call_count["n"] == calls_after_first)

    db.query(GeocodeCache).filter(GeocodeCache.address_hash.in_([hash_a, hash_b])).delete(synchronize_session=False)
    db.commit()

finally:
    db.query(GeocodeCache).filter(GeocodeCache.address_hash == address_hash).delete()
    db.commit()
    db.close()
    print("Đã dọn dữ liệu test.")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
