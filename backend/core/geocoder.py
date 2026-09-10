"""geocoder.py — wrapper VietMap Search/Place/Matrix (mục 14).

LỊCH SỬ ĐỔI NHÀ CUNG CẤP (2 lần, đọc để không đi lại vết xe đổ):
1. Google Maps Platform -> Goong: Google xác nhận KHÔNG dùng được cho tài khoản
   billing Việt Nam (Việt Nam nằm trong "Prohibited Territories" của Google Maps
   Platform Terms of Service).
2. Goong -> VietMap (2026-09-10, đợt code 5 Pha 6): hợp nhất về ĐÚNG 1 nhà cung
   cấp bản đồ cho toàn hệ thống. Tính năng "Vị trí & bản đồ" (Pha 4) buộc phải
   dùng VietMap vì Goong KHÔNG có dữ liệu traffic/congestion ở bất kỳ gói giá
   nào — để 2 provider song song thì cùng một địa chỉ có thể ra 2 toạ độ hơi
   khác nhau giữa màn hình bản đồ và phần AI tính khoảng cách.

BA KHÁC BIỆT THẬT của VietMap so với Goong, ĐÃ XÁC NHẬN BẰNG GỌI THẬT trước khi
viết code (cùng loại 2 bug từng dính lúc đổi Google->Goong):
1. Geocode THUẬN phải đi 2 BƯỚC: `Search v4` chỉ trả `ref_id` + địa chỉ dạng
   CHỮ, KHÔNG có lat/lng; phải gọi tiếp `Place v4` với `refid` đó mới ra toạ độ.
   Goong trả toạ độ ngay trong 1 lệnh gọi.
2. `Matrix v4` trả về MA TRẬN 2 chiều `distances[[...]]` / `durations[[...]]`
   (mét và GIÂY) ở cấp response cao nhất, không phải `rows[].elements[]` có
   `status` riêng từng phần tử như Goong/Google.
3. Cả 2 endpoint đều nhận key qua tham số `apikey` (Goong dùng `api_key`).

Thiết kế "graceful degradation" GIỮ NGUYÊN từ bản Google/Goong: mọi lỗi mạng/
key/quota đều bị bắt và trả `None`, KHÔNG BAO GIỜ raise ra ngoài, để
`option_generator`/job vẫn chạy tiếp mà chỉ thiếu thông tin khoảng cách.
"""
import hashlib
import os

import httpx
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import GeocodeCache

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

SEARCH_URL = "https://maps.vietmap.vn/api/search/v4"
PLACE_URL = "https://maps.vietmap.vn/api/place/v4"
MATRIX_URL = "https://maps.vietmap.vn/api/matrix/v4"


def _address_hash(address: str) -> str:
    return hashlib.md5(address.strip().lower().encode("utf-8")).hexdigest()


def _api_key() -> "str | None":
    """Key VietMap. Thiếu key thì trả None -> mọi hàm dưới đây degrade êm về
    None (KHÔNG raise), hệ thống chạy tiếp mà chỉ thiếu thông tin khoảng cách.

    CỐ Ý không fallback sang `GOONG_API_KEY` cũ: key Goong gọi VietMap chắc
    chắn 401, fallback chỉ đổi một lỗi cấu hình rõ ràng thành một lỗi mạng khó
    hiểu."""
    return os.environ.get("VIETMAP_API_KEY")


def geocode(db: Session, address: str) -> "dict | None":
    """Trả `{"lat":.., "lng":..}` hoặc `None` nếu lỗi/không tìm thấy — KHÔNG
    raise. Cache theo hash địa chỉ (mục 14), không gọi lại API cho địa chỉ đã
    có trong `geocode_cache`.

    Cache càng quan trọng với VietMap vì mỗi lần geocode tốn 2 lệnh gọi
    (Search v4 -> Place v4), gấp đôi Goong.
    """
    address = address.strip()
    if not address:
        return None

    address_hash = _address_hash(address)
    cached = db.execute(select(GeocodeCache).where(GeocodeCache.address_hash == address_hash)).scalar_one_or_none()
    if cached is not None and cached.coordinates is not None:
        return cached.coordinates

    api_key = _api_key()
    if not api_key:
        return None

    try:
        search = httpx.get(SEARCH_URL, params={"apikey": api_key, "text": address}, timeout=10.0)
        search.raise_for_status()
        results = search.json()
        # Search v4 trả về THẲNG một mảng (không bọc trong {"results": ...}
        # như Goong) — mảng rỗng nghĩa là không tìm thấy địa chỉ nào.
        if not isinstance(results, list) or not results:
            return None
        ref_id = results[0].get("ref_id")
        if not ref_id:
            return None

        place = httpx.get(PLACE_URL, params={"apikey": api_key, "refid": ref_id}, timeout=10.0)
        place.raise_for_status()
        detail = place.json()
        lat, lng = detail.get("lat"), detail.get("lng")
        if lat is None or lng is None:
            return None
        coordinates = {"lat": float(lat), "lng": float(lng)}
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
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
    lưu vào cột `distance_matrix` dạng `{destination_hash: {...}}`).

    `Matrix v4` (giống Goong, khác Google) CHỈ nhận toạ độ `lat,lng` chứ KHÔNG
    nhận địa chỉ text tự do — phải tự `geocode()` cả 2 đầu trước, tận dụng luôn
    cache sẵn có của `geocode()`.
    """
    origin, destination = origin.strip(), destination.strip()
    if not origin or not destination:
        return None

    origin_hash = _address_hash(origin)
    dest_hash = _address_hash(destination)
    cache_row = db.execute(select(GeocodeCache).where(GeocodeCache.address_hash == origin_hash)).scalar_one_or_none()
    existing_matrix = (cache_row.distance_matrix or {}) if cache_row else {}
    if dest_hash in existing_matrix:
        return existing_matrix[dest_hash]

    api_key = _api_key()
    if not api_key:
        return None

    origin_coords = geocode(db, origin)
    dest_coords = geocode(db, destination)
    if origin_coords is None or dest_coords is None:
        return None
    # `geocode()` ở trên có thể vừa TỰ TẠO dòng `geocode_cache` cho `origin`
    # (nếu trước đó chưa có) — phải lấy lại `cache_row` MỚI, nếu không biến cũ
    # vẫn là `None` và code bên dưới sẽ cố INSERT thêm 1 dòng trùng
    # `address_hash` (vỡ ràng buộc UNIQUE) thay vì UPDATE dòng vừa tạo.
    cache_row = db.execute(select(GeocodeCache).where(GeocodeCache.address_hash == origin_hash)).scalar_one_or_none()

    try:
        response = httpx.get(
            MATRIX_URL,
            # `point` lặp 2 lần (điểm đi, điểm đến) nên phải là list tuple —
            # dict thường sẽ nuốt mất cái thứ hai.
            params=[
                ("apikey", api_key),
                ("point", f"{origin_coords['lat']},{origin_coords['lng']}"),
                ("point", f"{dest_coords['lat']},{dest_coords['lng']}"),
                ("sources", "0"),
                ("destinations", "1"),
                # Xin CẢ 2 chỉ số trong 1 lệnh gọi (tài liệu viết
                # `{duration|distance}` như thể chỉ chọn 1, gọi thật thì
                # `duration,distance` trả về đủ cả hai).
                ("annotation", "duration,distance"),
                ("vehicle", "car"),
            ],
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != "OK":
            return None
        # Ma trận 1x1 vì chỉ hỏi 1 nguồn -> 1 đích. Đơn vị: MÉT và GIÂY.
        result = {
            "distance_km": round(data["distances"][0][0] / 1000, 2),
            "duration_min": round(data["durations"][0][0] / 60, 1),
        }
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None

    existing_matrix[dest_hash] = result
    if cache_row is not None:
        cache_row.distance_matrix = existing_matrix
    else:
        db.add(GeocodeCache(address_hash=origin_hash, address_raw=origin, distance_matrix=existing_matrix))
    db.commit()
    return result
