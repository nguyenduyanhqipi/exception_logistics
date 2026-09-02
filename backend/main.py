import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from api.auth import router as auth_router
from api.exceptions import router as exceptions_router
from api.jobs import router as jobs_router
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
app.include_router(jobs_router)


@app.get("/health")
def health():
    return {"status": "ok"}
