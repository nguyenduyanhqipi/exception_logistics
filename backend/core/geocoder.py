"""geocoder.py — wrapper Google Geocoding + Distance Matrix (mục 14).

GHI CHÚ QUAN TRỌNG: viết ở thời điểm `GOOGLE_MAPS_API_KEY` của công ty đang
lỗi/chưa hoạt động — mọi hàm ở đây đã thiết kế "graceful degradation" NGAY TỪ
ĐẦU theo đúng mục 14 (không phải thêm sau): lỗi mạng/key/quota đều bị bắt và
trả `None`, KHÔNG BAO GIỜ raise ra ngoài, để `option_generator`/job vẫn tiếp
tục chạy mà chỉ thiếu thông tin khoảng cách. Khi có key thật hoạt động, cần
chạy lại `scripts/test_geocoder.py` để xác nhận toạ độ trả về hợp lý cho địa
chỉ Hà Nội thật — phần ĐÓ chưa verify được trong lúc code do key đang lỗi.
"""
import hashlib
import os

import httpx
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import GeocodeCache

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


def _address_hash(address: str) -> str:
    return hashlib.md5(address.strip().lower().encode("utf-8")).hexdigest()


def geocode(db: Session, address: str) -> "dict | None":
    """Trả `{"lat":.., "lng":..}` hoặc `None` nếu lỗi/không tìm thấy — KHÔNG
    raise. Cache theo hash địa chỉ (mục 14), không gọi lại API cho địa chỉ đã
    có trong `geocode_cache`."""
    address = address.strip()
    if not address:
        return None

    address_hash = _address_hash(address)
    cached = db.execute(select(GeocodeCache).where(GeocodeCache.address_hash == address_hash)).scalar_one_or_none()
    if cached is not None and cached.coordinates is not None:
        return cached.coordinates

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return None

    try:
        response = httpx.get(GEOCODE_URL, params={"address": address, "key": api_key}, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        location = data["results"][0]["geometry"]["location"]
        coordinates = {"lat": location["lat"], "lng": location["lng"]}
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None

    if cached is not None:
        cached.coordinates = coordinates
    else:
        db.add(GeocodeCache(address_hash=address_hash, address_raw=address, coordinates=coordinates))
    db.commit()
    return coordinates


def distance_matrix(db: Session, origin: str, destination: str) -> "dict | None":
    """Trả `{"distance_km":.., "duration_min":..}` hoặc `None` nếu lỗi — cache
    theo cặp origin+destination (dùng chung `geocode_cache` của `origin`,
    lưu vào cột `distance_matrix` dạng `{destination_hash: {...}}`)."""
    origin, destination = origin.strip(), destination.strip()
    if not origin or not destination:
        return None

    origin_hash = _address_hash(origin)
    dest_hash = _address_hash(destination)
    cache_row = db.execute(select(GeocodeCache).where(GeocodeCache.address_hash == origin_hash)).scalar_one_or_none()
    existing_matrix = (cache_row.distance_matrix or {}) if cache_row else {}
    if dest_hash in existing_matrix:
        return existing_matrix[dest_hash]

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return None

    try:
        response = httpx.get(
            DISTANCE_MATRIX_URL,
            params={"origins": origin, "destinations": destination, "key": api_key},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        element = data["rows"][0]["elements"][0]
        if data.get("status") != "OK" or element.get("status") != "OK":
            return None
        result = {
            "distance_km": round(element["distance"]["value"] / 1000, 2),
            "duration_min": round(element["duration"]["value"] / 60, 1),
        }
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None

    existing_matrix[dest_hash] = result
    if cache_row is not None:
        cache_row.distance_matrix = existing_matrix
    else:
        db.add(GeocodeCache(address_hash=origin_hash, address_raw=origin, distance_matrix=existing_matrix))
    db.commit()
    return result
