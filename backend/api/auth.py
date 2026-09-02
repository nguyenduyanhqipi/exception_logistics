from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_refresh_token,
    verify_password,
)
from middleware.auth import get_current_user
from middleware.tenant import get_public_db
from models import User
from schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_public_db)):
    user = db.execute(
        select(User).where(User.email == payload.email, User.deleted_at.is_(None))
    ).scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không đúng",
        )

    return TokenResponse(
        access_token=create_access_token(user.user_id, user.company_id, user.role),
        refresh_token=create_refresh_token(user.user_id),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_public_db)):
    try:
        token_payload = decode_token(payload.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    if token_payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không phải refresh token")

    user = db.execute(
        select(User).where(User.user_id == token_payload["sub"], User.deleted_at.is_(None))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không còn tồn tại")

    return AccessTokenResponse(access_token=create_access_token(user.user_id, user.company_id, user.role))


@router.post("/logout")
def logout(payload: LogoutRequest):
    try:
        revoke_refresh_token(payload.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return {"message": "Đăng xuất thành công"}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user
