"""grant_platform_admin.py — cấp role 'platform_admin' (mục 20.3) cho 1 user
theo email. Chạy TAY, không có UI/API (đúng tinh thần "cấp cho tối thiểu 2
người CỤ THỂ", không phải quy trình tự phục vụ đại trà).

Chạy: python scripts/grant_platform_admin.py user@example.com
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from database import SessionLocal
from models import User


def main():
    if len(sys.argv) != 2:
        print("Dùng: python scripts/grant_platform_admin.py <email>")
        sys.exit(1)
    email = sys.argv[1]

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            print(f"Không tìm thấy user với email {email}")
            sys.exit(1)
        old_role = user.role
        user.role = "platform_admin"
        db.commit()
        print(f"Đã cấp platform_admin cho {email} (role cũ: {old_role}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
