from fastapi import Depends, HTTPException, status

from middleware.auth import get_current_user


def require_role(*allowed_roles: str):
    def checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Vai trò '{current_user['role']}' không có quyền truy cập chức năng này",
            )
        return current_user

    return checker
