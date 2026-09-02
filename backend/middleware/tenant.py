from database import SessionLocal
from core.tenant_context import current_company_id
from middleware.auth import get_current_user
from fastapi import Depends


def get_public_db():
    """DB session KHÔNG có tenant filter — chỉ dùng cho endpoint không cần auth
    (vd /api/auth/login, /health)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_db(current_user: dict = Depends(get_current_user)):
    """DB session có tenant filter tự động theo company_id của user đã xác thực
    (mục 13, bước 4) — mọi SELECT trên model có company_id sẽ tự bị lọc, xem
    database.py::_apply_tenant_filter.

    QUAN TRỌNG — phải là `async def`, KHÔNG phải `def` thường: FastAPI chạy
    dependency generator dạng `def` (sync) qua threadpool
    (anyio.to_thread.run_sync), và mỗi lần dispatch qua threadpool anyio chụp
    một BẢN SAO contextvars.Context riêng tại thời điểm gọi — set() bên trong
    1 bản sao KHÔNG lan ra context thật của request. Hậu quả thực tế đã gặp:
    contextvar set ở đây (thread A) nhưng endpoint (dispatch threadpool khác,
    thread B) đọc lại thấy `None` — tenant filter coi như tắt hoàn toàn dù
    không báo lỗi gì (chỉ không lộ ra vì lúc test mới có 1 company). Dependency
    `async def` chạy thẳng trên event loop, không qua threadpool, nên set()
    ở đây sửa đổi context thật của Task — khi FastAPI sau đó dispatch endpoint
    (sync) qua threadpool, bản sao context được chụp SAU khi giá trị này đã
    được set, nên endpoint đọc đúng giá trị.
    """
    current_company_id.set(current_user["company_id"])
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        current_company_id.set(None)
