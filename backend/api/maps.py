"""api/maps.py — endpoint bản đồ/định tuyến cho tính năng "Vị trí & bản đồ"
(đợt code 5, Pha 4).

TẠI SAO PHẢI PROXY QUA BACKEND thay vì để frontend gọi thẳng VietMap: có 2 key
khác nhau và chỉ 1 cái được phép ra trình duyệt.
- `VIETMAP_TILEMAP_KEY` -> BẮT BUỘC ở phía trình duyệt (nằm ngay trong style
  URL mà VietMap GL JS tải), chỉ bảo vệ được bằng giới hạn domain/IP trong
  Console VietMap.
- `VIETMAP_API_KEY` (Route v4, Static Map) -> giữ NGUYÊN phía server. Route v4
  tính theo lệnh gọi, lộ key ra bundle JS là ai cũng đốt hạn mức hộ được.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.geocoder import geocode
from core.vietmap import VietMapError, route, static_map_png
from middleware.auth import get_current_user
from middleware.tenant import get_db
from models import Exception_, ImpactAnalysis, Schedule

router = APIRouter(prefix="/api/maps", tags=["maps"])


class LatLng(BaseModel):
    # Biên hợp lệ của lãnh thổ Việt Nam (nới rộng chút cho hải đảo). Chặn ngay
    # ở đây vì lỗi hay gặp nhất khi ghép bản đồ là ĐẢO THỨ TỰ lat/lng — vào tới
    # VietMap thì nó chỉ trả "không tìm được đường", không nói vì sao.
    lat: float = Field(ge=8.0, le=24.0)
    lng: float = Field(ge=102.0, le=110.0)


class RouteRequest(BaseModel):
    origin: LatLng
    destination: LatLng
    # Ảnh hưởng thật tới tuyến: xe tải bị cấm giờ/cấm đường ở nhiều tuyến nội
    # đô, đi theo tuyến của xe con là ra phương án không chạy được.
    vehicle: str = "car"


@router.post("/route")
def get_route(
    payload: RouteRequest,
    current_user: dict = Depends(get_current_user),
):
    """Tìm đường + mức tắc từng đoạn + phí trạm, từ vị trí xe tới 1 điểm đến.

    Trả về NHIỀU phương án (`alternative=true`) để dispatcher tự chọn theo tiêu
    chí của mình — hệ thống KHÔNG tự chốt hộ: `avoid` của Route v4 chỉ né được
    LOẠI đường (phà, cao tốc...) chứ không né được đúng đoạn đang bị chặn, nên
    chỉ người nhìn bản đồ mới xác nhận được tuyến nào thực sự đi vòng qua chỗ
    tắc.
    """
    try:
        paths = route(
            (payload.origin.lat, payload.origin.lng),
            (payload.destination.lat, payload.destination.lng),
            vehicle=payload.vehicle,
        )
    except VietMapError as exc:
        # 502: lỗi của dịch vụ bên ngoài, không phải request sai của người dùng
        # — phân biệt rõ để dispatcher không đi sửa lại dữ liệu đã nhập đúng.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if not paths:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VietMap không tìm được tuyến nào giữa 2 điểm này.",
        )
    return {"paths": paths}


@router.get("/static")
def get_static_map(
    lat: float = Query(ge=8.0, le=24.0),
    lng: float = Query(ge=102.0, le=110.0),
    zoom: int = Query(default=15, ge=0, le=20),
    current_user: dict = Depends(get_current_user),
):
    """Ảnh PNG bản đồ tĩnh — ảnh xem trước rẻ tiền cho màn hình danh sách.

    Có endpoint này thì bản đồ TƯƠNG TÁC chỉ mở khi dispatcher thật sự bấm
    "xem bản đồ": hạn mức Tilemap chỉ 10 lệnh/phút (thấp hơn hẳn 200/phút của
    Static Map), mở tương tác cho mọi ngoại lệ là chạm trần rồi tile trắng.
    """
    try:
        png = static_map_png(lat, lng, zoom=zoom)
    except VietMapError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    # Ảnh của 1 toạ độ cố định không đổi theo thời gian -> cho trình duyệt cache
    # 1 ngày, đỡ đốt hạn mức khi dispatcher mở đi mở lại cùng 1 ngoại lệ.
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/exceptions/{exception_id}/routes")
def routes_for_exception(
    exception_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Các tuyến đi từ VỊ TRÍ XE HIỆN TẠI tới điểm giao kế tiếp của 1 ngoại lệ.

    Gom cả 3 việc (đọc vị trí xe, tìm toạ độ điểm đến, gọi Route v4) vào 1 lệnh
    gọi để frontend không phải tự ghép — và quan trọng hơn, để chỗ duy nhất biết
    "điểm đến kế tiếp là điểm nào" nằm ở backend, cùng chỗ với
    `impact_analysis.affected_stops` sinh ra nó.

    Vị trí xe lấy từ `input_context.current_lat/current_lng` (dispatcher ghim
    lúc khai báo ngoại lệ, xem exceptionForm.ts::FOLLOW_UPS). Không có toạ độ
    thì KHÔNG đoán từ `area`: một chuỗi "Cầu Giấy" có thể là bất cứ đâu trong
    cả quận, vẽ ra tuyến sai còn tệ hơn không vẽ gì.
    """
    exc = db.get(Exception_, exception_id)
    if exc is None or str(exc.company_id) != current_user["company_id"] or exc.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy ngoại lệ {exception_id}")

    ctx = exc.input_context or {}
    lat, lng = ctx.get("current_lat"), ctx.get("current_lng")
    if lat is None or lng is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngoại lệ này chưa ghim vị trí xe trên bản đồ — sửa lại ngoại lệ và chọn vị trí để xem tuyến đi.",
        )

    impact = db.execute(
        select(ImpactAnalysis).where(ImpactAnalysis.exception_id == exc.exception_id)
    ).scalar_one_or_none()
    affected = (impact.affected_stops if impact else None) or []
    if not affected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngoại lệ này không ảnh hưởng điểm giao nào nên không có điểm đến để tìm đường.",
        )

    schedule = db.get(Schedule, exc.schedule_id)
    stops_by_id = {s.get("stop_id"): s for s in ((schedule.stops if schedule else None) or [])}
    target = stops_by_id.get(affected[0].get("stop_id")) or affected[0]

    # Ưu tiên toạ độ có sẵn trong `stops[]`; thiếu thì geocode địa chỉ (có cache
    # theo hash địa chỉ nên mở lại cùng ngoại lệ không tốn thêm lệnh gọi nào).
    dest_lat, dest_lng = target.get("lat"), target.get("lng")
    if dest_lat is None or dest_lng is None:
        found = geocode(db, target.get("address") or "")
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không xác định được toạ độ của điểm giao '{target.get('address') or '?'}' để tìm đường.",
            )
        dest_lat, dest_lng = found["lat"], found["lng"]

    try:
        paths = route((lat, lng), (dest_lat, dest_lng), vehicle="truck")
    except VietMapError as exc_err:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc_err))

    return {
        "origin": {"lat": lat, "lng": lng, "address": ctx.get("current_address")},
        "destination": {
            "lat": dest_lat,
            "lng": dest_lng,
            "address": target.get("address"),
            "order_id": target.get("order_id"),
            "stop_id": target.get("stop_id"),
        },
        "paths": paths,
    }
