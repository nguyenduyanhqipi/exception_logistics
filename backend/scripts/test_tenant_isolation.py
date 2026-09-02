"""Kiểm tra tenant injection ở tầng DB (BUILD_PLAN.md bước 2.4): tạo 2 company
+ 2 xe (mỗi company 1 xe), set current_company_id rồi query KHÔNG filter thủ
công — xác nhận chỉ thấy xe của company mình. Xóa dữ liệu test khi xong.

Đây là test ở tầng DB thuần (không qua FastAPI/HTTP) — kiểm tra cơ chế
with_loader_criteria trong database.py. Việc contextvar có thực sự lan truyền
đúng qua toàn bộ vòng đời 1 HTTP request (dependency -> endpoint) là chuyện
KHÁC, đã lộ ra 1 bug thật riêng (get_db phải là `async def`, xem
middleware/tenant.py) và được xác minh lại bằng test qua HTTP thật (2 tài
khoản 2 company gọi /api/vehicles) khi build Giai đoạn 3.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from core.tenant_context import current_company_id
from database import SessionLocal
from models import Company, Vehicle

COMPANY_A = str(uuid.uuid4())
COMPANY_B = str(uuid.uuid4())


def main():
    db = SessionLocal()
    try:
        db.add(Company(company_id=COMPANY_A, name="Test Company A"))
        db.add(Company(company_id=COMPANY_B, name="Test Company B"))
        db.flush()
        db.add(Vehicle(vehicle_id="TEST-A1", company_id=COMPANY_A, driver_name="A Driver", driver_phone="0900000001", max_payload_kg=1000))
        db.add(Vehicle(vehicle_id="TEST-B1", company_id=COMPANY_B, driver_name="B Driver", driver_phone="0900000002", max_payload_kg=1000))
        db.commit()

        current_company_id.set(COMPANY_A)
        rows = db.execute(select(Vehicle)).scalars().all()
        current_company_id.set(None)
        ids = sorted(v.vehicle_id for v in rows if v.vehicle_id.startswith("TEST-"))
        print("Xe thấy được khi set company A:", ids)
        assert ids == ["TEST-A1"], f"LEAK: expected only TEST-A1, got {ids}"
        print("PASS: company A không thấy xe của company B")

        current_company_id.set(COMPANY_B)
        rows = db.execute(select(Vehicle)).scalars().all()
        current_company_id.set(None)
        ids = sorted(v.vehicle_id for v in rows if v.vehicle_id.startswith("TEST-"))
        print("Xe thấy được khi set company B:", ids)
        assert ids == ["TEST-B1"], f"LEAK: expected only TEST-B1, got {ids}"
        print("PASS: company B không thấy xe của company A")

    finally:
        db.query(Vehicle).filter(Vehicle.vehicle_id.in_(["TEST-A1", "TEST-B1"])).delete(synchronize_session=False)
        db.query(Company).filter(Company.company_id.in_([COMPANY_A, COMPANY_B])).delete(synchronize_session=False)
        db.commit()
        db.close()
        print("Đã dọn dữ liệu test.")


if __name__ == "__main__":
    main()
