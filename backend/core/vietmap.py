"""vietmap.py — wrapper VietMap Maps API cho tính năng "Vị trí & bản đồ"
(đợt code 5, Pha 4 — Claude outputs/dot_code_5/map_routing_feature.md).

TÁCH KHỎI `core/geocoder.py` có chủ đích: geocoder đang chạy Goong và đang nuôi
`distance_info` cho pipeline AI (đã chạy thật trên production). Hợp nhất 2 nhà
cung cấp là việc RIÊNG, xếp sau (Pha 6) — trộn vào đây là đụng phần đang chạy
tốt để đổi lấy một tính năng chưa có gì.

Hai cạm bẫy ĐÃ XÁC NHẬN BẰNG GỌI THẬT (không đoán), cùng loại với 2 bug từng
gặp khi đổi Google -> Goong:
1. Thứ tự toạ độ KHÔNG đồng nhất: Route v4 nhận `point=lat,lng`, nhưng
   `paths[].points.coordinates` trả về `[lng, lat]` (chuẩn GeoJSON) và
   `paths[].bbox` là `[minLng, minLat, maxLng, maxLat]`. Đổi chỗ nhầm là ra
   giữa biển Đông mà không có lỗi nào báo.
2. `annotations` KHÔNG phải mảng phẳng: nó là object có 3 key con
   (`congestion`, `congestion_distance`, `history_speed`) dù chỉ xin
   `annotations=congestion,toll`. `congestion` là list các đoạn
   `{"value": "low|moderate|heavy|severe", "first": i, "last": j}` với i/j là
   CHỈ SỐ vào mảng `coordinates`, không phải mét hay giây.

Graceful degradation giống hệt geocoder.py: mọi lỗi mạng/key/quota đều trả về
`None`/raise `VietMapError` có thông điệp đọc được, KHÔNG để traceback thô nhảy
ra API.
"""
import os

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

ROUTE_URL = "https://maps.vietmap.vn/api/route/v4"
STATIC_MAP_URL = "https://maps.vietmap.vn/api/maps/statics/tm"

# Trần thời gian cho 1 lệnh gọi. Dispatcher đang đứng chờ trước màn hình bản đồ
# nên không thể để treo lâu như job AI chạy nền (90s ở option_generator).
TIMEOUT_SECONDS = 15.0

# 4 mức tắc đường VietMap trả về, theo đúng thứ tự nặng dần. Liệt kê ra để
# frontend tô màu và để biết ngay khi VietMap thêm mức mới (giá trị lạ sẽ rơi
# vào nhánh mặc định thay vì làm vỡ giao diện).
CONGESTION_LEVELS = ("low", "moderate", "heavy", "severe")


class VietMapError(RuntimeError):
    """Lỗi gọi VietMap đã được diễn giải sang tiếng Việt cho dispatcher đọc."""


def _api_key() -> str:
    key = os.getenv("VIETMAP_API_KEY")
    if not key:
        raise VietMapError("Chưa cấu hình VIETMAP_API_KEY — thêm vào .env rồi khởi động lại backend")
    return key


def route(
    origin: "tuple[float, float]",
    destination: "tuple[float, float]",
    vehicle: str = "car",
    alternatives: bool = True,
) -> list:
    """Tìm đường từ `origin` tới `destination`, cả 2 dạng `(lat, lng)`.

    Trả về list phương án đã CHUẨN HOÁ sẵn cho frontend vẽ bản đồ — không trả
    thô response VietMap, để chỗ duy nhất phải biết về hình dạng response của họ
    là file này (xem 2 cạm bẫy ở docstring đầu file).
    """
    params = {
        "apikey": _api_key(),
        "vehicle": vehicle,
        # `annotations=congestion,toll` -> có mức tắc từng đoạn + chi phí trạm
        # thu phí thật; `points_encoded=false` -> `points` về thẳng dạng GeoJSON
        # LineString, khỏi phải tự giải mã polyline ở frontend.
        "annotations": "congestion,toll",
        "points_encoded": "false",
    }
    if alternatives:
        params["alternative"] = "true"
    # `point` lặp lại 2 lần (điểm đi, điểm đến) nên phải dựng list tuple, dict
    # thường sẽ nuốt mất cái thứ hai.
    query = list(params.items()) + [
        ("point", f"{origin[0]},{origin[1]}"),
        ("point", f"{destination[0]},{destination[1]}"),
    ]

    try:
        resp = httpx.get(ROUTE_URL, params=query, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise VietMapError(f"Không gọi được dịch vụ bản đồ VietMap: {exc}") from exc

    if resp.status_code != 200:
        # 503 body rỗng từ nginx = sự cố hạ tầng phía VietMap, KHÁC hẳn lỗi
        # app-level (luôn có JSON kèm message) — nói rõ để dispatcher không đi
        # sửa nhầm dữ liệu của mình.
        detail = (resp.text or "").strip()
        raise VietMapError(
            f"Dịch vụ định tuyến VietMap trả lỗi {resp.status_code}"
            + (f": {detail[:200]}" if detail else " (không có nội dung — nhiều khả năng lỗi hạ tầng phía VietMap)")
        )

    data = resp.json()
    if data.get("code") != "OK":
        raise VietMapError(f"VietMap không tìm được đường đi (code={data.get('code')})")

    return [_normalise_path(p) for p in data.get("paths", [])]


def _normalise_path(path: dict) -> dict:
    """1 phương án đường đi -> dict frontend dùng thẳng được.

    `coordinates` giữ NGUYÊN thứ tự `[lng, lat]` của VietMap vì VietMap GL JS
    (và GeoJSON nói chung) cũng dùng đúng thứ tự đó — đổi ở đây rồi lại đổi
    ngược ở frontend là 2 lần cơ hội sai.
    """
    points = path.get("points") or {}
    coordinates = points.get("coordinates") or []
    annotations = path.get("annotations") or {}
    return {
        "distance_m": path.get("distance"),
        # VietMap trả mili-giây; đổi sang phút ngay tại đây để không nơi nào
        # khác phải nhớ đơn vị này.
        "duration_min": round((path.get("time") or 0) / 60000, 1),
        "toll_cost": path.get("toll_cost"),
        "tolls": path.get("tolls") or [],
        "coordinates": coordinates,
        "bbox": path.get("bbox"),
        "congestion": annotations.get("congestion") or [],
    }


def static_map_png(lat: float, lng: float, zoom: int = 15, size: str = "600x400") -> bytes:
    """Ảnh PNG bản đồ tĩnh quanh 1 toạ độ.

    Dùng làm ảnh xem trước ở màn hình chính: hạn mức Static Map là 200 lệnh/phút
    trong khi Tilemap chỉ 10/phút, nên mở bản đồ tương tác cho MỌI ngoại lệ là
    cách nhanh nhất để chạm trần rồi tile trắng xoá giữa lúc demo.

    `apikey` phải nằm trong FORM BODY, không phải query string (khác hẳn Route
    v4) — đây là endpoint server-side, key không được lộ ra URL.
    """
    try:
        resp = httpx.post(
            STATIC_MAP_URL,
            files={
                "lat": (None, str(lat)),
                "lng": (None, str(lng)),
                "apikey": (None, _api_key()),
                "zoom": (None, str(zoom)),
                "size": (None, size),
            },
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise VietMapError(f"Không gọi được ảnh bản đồ VietMap: {exc}") from exc

    if resp.status_code != 200:
        raise VietMapError(f"Dịch vụ ảnh bản đồ VietMap trả lỗi {resp.status_code}")
    return resp.content
