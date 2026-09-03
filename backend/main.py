import os
import time
from collections import defaultdict, deque

import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# `sentry_sdk` có sẵn trong requirements.txt, `SENTRY_DSN` có sẵn trong
# .env.example/render.yaml/DEPLOY.md từ đầu dự án nhưng chưa từng được init ở
# đâu — khai báo vô tác dụng. Chỉ init khi có DSN thật (mục "Sentry để trống
# nếu chưa dùng" trong DEPLOY.md) — để trống thì KHÔNG init, app chạy y hệt
# như trước, không lỗi/warning gì.
SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN)

from api.auth import router as auth_router
from api.dashboard import router as dashboard_router
from api.decisions import router as decisions_router
from api.exceptions import router as exceptions_router
from api.reports import router as reports_router
from api.jobs import router as jobs_router
from api.rag_trace import router as rag_trace_router
from api.schedules import router as schedules_router
from api.settings import router as settings_router
from api.vehicles import router as vehicles_router

app = FastAPI(title="Exception Logistics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting đơn giản theo IP (mục 13, bước 2) — 100 req/phút. In-memory vì
# chưa dùng Redis ở giai đoạn này; đủ cho 1 tiến trình dev/demo.
RATE_LIMIT = 100
RATE_WINDOW_SECONDS = 60
_request_log: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    log = _request_log[client_key]
    while log and now - log[0] > RATE_WINDOW_SECONDS:
        log.popleft()
    if len(log) >= RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Quá nhiều yêu cầu, vui lòng thử lại sau",
        )
    log.append(now)
    return await call_next(request)


app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(vehicles_router)
app.include_router(schedules_router)
app.include_router(exceptions_router)
app.include_router(dashboard_router)
app.include_router(jobs_router)
app.include_router(decisions_router)
app.include_router(reports_router)
app.include_router(rag_trace_router)


@app.get("/health")
def health():
    return {"status": "ok"}
