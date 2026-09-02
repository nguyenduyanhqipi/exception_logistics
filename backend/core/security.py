import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from dotenv import load_dotenv
from jose import JWTError, jwt

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Revoke list cho refresh token khi logout. In-memory vì app chạy 1 tiến trình
# ở giai đoạn này (chưa có Redis/bảng session trong schema mục 4) — refresh
# token bị revoke sẽ mất hiệu lực ngay, access token cũ (tối đa 30 phút) vẫn
# tự hết hạn tự nhiên theo "exp".
_revoked_refresh_jtis: set[str] = set()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: str, company_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "company_id": str(company_id),
        "role": role,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Token không hợp lệ hoặc đã hết hạn") from exc

    if payload.get("type") == "refresh" and payload.get("jti") in _revoked_refresh_jtis:
        raise ValueError("Refresh token đã bị thu hồi (đã logout)")

    return payload


def revoke_refresh_token(token: str) -> None:
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise ValueError("Chỉ có thể thu hồi refresh token")
    _revoked_refresh_jtis.add(payload["jti"])
