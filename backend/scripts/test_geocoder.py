"""Test geocoder.py (BUILD_PLAN.md bước 7.2-7.4) — bản Goong Maps (mục 41).

GHI CHÚ: `GOONG_API_KEY` của công ty có thể chưa được cấu hình lúc chạy test
này — phần "geocode ra đúng toạ độ hợp lý bằng key thật" để trống, cần chạy
lại khi có key hoạt động. 3 việc test được mà KHÔNG cần key thật hoạt động:
  1. Cache logic (7.3) — mock httpx.get, xác nhận gọi API đúng 1 lần cho 2 lần
     geocode cùng địa chỉ.
  2. Graceful degradation khi KHÔNG có key (7.4) — không raise, trả None sạch
     sẽ.
  3. Graceful degradation khi CÓ key nhưng SAI/invalid (7.4, gọi API THẬT của
     Goong với key rác để mô phỏng "sai key") — Goong trả lỗi (status khác
     "OK", hoặc HTTP lỗi), code phải bắt và trả None, không crash.
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
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": 21.0368, "lng": 105.7827}}}],
    }
    call_count = {"n": 0}

    def fake_get(*args, **kwargs):
        call_count["n"] += 1
        return fake_response

    with patch.dict(os.environ, {"GOONG_API_KEY": "fake-key-for-cache-test"}):
        with patch("core.geocoder.httpx.get", side_effect=fake_get):
            result1 = geocoder.geocode(db, test_address)
            check("Lần gọi 1: trả toạ độ đúng từ (mock) API", result1 == {"lat": 21.0368, "lng": 105.7827})
            check("Lần gọi 1: gọi httpx.get đúng 1 lần", call_count["n"] == 1)

            result2 = geocoder.geocode(db, test_address)
            check("Lần gọi 2 (cùng địa chỉ): trả đúng toạ độ từ cache", result2 == {"lat": 21.0368, "lng": 105.7827})
            check("Lần gọi 2: KHÔNG gọi lại httpx.get (vẫn 1 lần) — cache hoạt động", call_count["n"] == 1)

    cached_row = db.query(GeocodeCache).filter(GeocodeCache.address_hash == address_hash).first()
    check("geocode_cache có 1 dòng lưu đúng address_raw", cached_row is not None and cached_row.address_raw == test_address)

    # ---- Test 2: graceful degradation KHÔNG CÓ key (7.4) ----
    db.query(GeocodeCache).filter(GeocodeCache.address_hash == address_hash).delete()
    db.commit()
    with patch.dict(os.environ, {"GOONG_API_KEY": ""}):
        result_no_key = geocoder.geocode(db, test_address)
        check("Không có key: trả None, KHÔNG raise exception", result_no_key is None)

    # ---- Test 3: graceful degradation với key SAI thật sự (gọi Goong API THẬT) ----
    with patch.dict(os.environ, {"GOONG_API_KEY": "invalid-key-does-not-exist-12345"}):
        try:
            result_bad_key = geocoder.geocode(db, test_address)
            check("Key sai (gọi Goong API thật): trả None, KHÔNG raise exception", result_bad_key is None)
        except Exception as e:  # noqa: BLE001
            check(f"Key sai: KHÔNG được raise exception (đã raise: {e})", False)

        try:
            dm_bad_key = geocoder.distance_matrix(db, test_address, "72 Ho Tung Mau, Nam Tu Liem")
            check("distance_matrix với key sai: trả None, KHÔNG raise exception", dm_bad_key is None)
        except Exception as e:  # noqa: BLE001
            check(f"distance_matrix key sai: KHÔNG được raise (đã raise: {e})", False)

finally:
    db.query(GeocodeCache).filter(GeocodeCache.address_hash == address_hash).delete()
    db.commit()
    db.close()
    print("Đã dọn dữ liệu test.")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
