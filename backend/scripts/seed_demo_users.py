"""Seed 1 company + 1 manager + 1 dispatcher demo (BUILD_PLAN.md bước 2.7).

Chạy: python scripts/seed_demo_users.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from core.security import hash_password
from database import SessionLocal
from models import Company, User

DEMO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"


def main():
    db = SessionLocal()
    try:
        company = db.execute(
            select(Company).where(Company.company_id == DEMO_COMPANY_ID)
        ).scalar_one_or_none()
        if company is None:
            company = Company(
                company_id=DEMO_COMPANY_ID,
                name="Công ty Vận tải Thành Công",
                timezone="Asia/Ho_Chi_Minh",
                default_depot_address="18 Phạm Hùng, Nam Từ Liêm",
                default_depot_area="Nam Từ Liêm",
                default_cost_per_km=8000,
            )
            db.add(company)
            db.flush()
            print(f"Created company {company.company_id}")
        else:
            print(f"Company {company.company_id} already exists")

        demo_users = [
            ("manager@demo.vn", "manager123", "manager", "Nguyễn Quản Lý"),
            ("dispatcher@demo.vn", "dispatcher123", "dispatcher", "Trần Điều Phối"),
        ]
        for email, password, role, full_name in demo_users:
            existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if existing:
                print(f"User {email} already exists")
                continue
            user = User(
                company_id=company.company_id,
                email=email,
                password_hash=hash_password(password),
                role=role,
                full_name=full_name,
            )
            db.add(user)
            print(f"Created user {email} ({role})")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
