"""geocoder.py — wrapper Goong Maps Geocoding + Distance Matrix (mục 14).

GHI CHÚ QUAN TRỌNG (đổi provider so với thiết kế ban đầu ở mục 41): Google Maps
Platform xác nhận KHÔNG dùng được cho tài khoản billing Việt Nam — Việt Nam nằm
trong danh sách "Prohibited Territories" chính thức của Google Maps Platform
Terms of Service (cùng nhóm với Trung Quốc, Iran, Triều Tiên, Syria...), xác
nhận độc lập qua trang chính thức của Google và qua Google Maps Support. Vì
vậy chuyển sang Goong Maps (goong.io) — API tương thích gần như 1-1 với Google
Geocoding/Distance Matrix ("drop-in replacement"), hỗ trợ đầy đủ Việt Nam.

Thiết kế "graceful degradation" GIỮ NGUYÊN như bản Google (mục 14, viết ngay từ
đầu chứ không phải thêm sau): lỗi mạng/key/quota đều bị bắt và trả `None`,
KHÔNG BAO GIỜ raise ra ngoài, để `option_generator`/job vẫn tiếp tục chạy mà
chỉ thiếu thông tin khoảng cách. Cần chạy lại `scripts/test_geocoder.py` với
`GOONG_API_KEY` thật để xác nhận toạ độ trả về hợp lý cho địa chỉ Hà Nội thật.
"""
import hashlib
import os

import httpx
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import GeocodeCache

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

GEOCODE_URL = "https://rsapi.goong.io/geocode"
DISTANCE_MATRIX_URL = "https://rsapi.goong.io/DistanceMatrix"


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

    api_key = os.environ.get("GOONG_API_KEY")
    if not api_key:
        return None

    try:
        response = httpx.get(GEOCODE_URL, params={"address": address, "api_key": api_key}, timeout=10.0)
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

    api_key = os.environ.get("GOONG_API_KEY")
    if not api_key:
        return None

    try:
        response = httpx.get(
            DISTANCE_MATRIX_URL,
            params={"origins": origin, "destinations": destination, "vehicle": "car", "api_key": api_key},
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
