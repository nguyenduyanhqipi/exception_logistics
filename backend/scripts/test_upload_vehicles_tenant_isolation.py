"""Test tenant isolation cho POST /api/vehicles/upload — cùng lỗi gốc với
create_vehicle (xem test_vehicle_tenant_isolation_http.py): `db.get(Vehicle,
vehicle_id)` bị tenant filter ẩn mất xe của công ty khác, khiến company B
"upload" trùng vehicle_id của company A tưởng là tạo mới rồi vỡ ràng buộc PK
(500) thay vì báo lỗi rõ ràng (400/detail). Cần server chạy sẵn ở
http://127.0.0.1:8000."""
import io
import sys
import uuid
from pathlib import Path

import httpx
import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.security import create_access_token
from database import SessionLocal
from models import Company, User, Vehicle

BASE_URL = "http://127.0.0.1:8000"
passed, failed = 0, 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


def build_vehicle_xlsx(vehicle_id: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Danh_muc_xe"
    ws.append(["vehicle_id", "driver_name", "driver_phone", "max_payload_kg", "cost_per_km", "vehicle_type", "status", "notes"])
    ws.append(["(mã xe)", "(tên tài xế)", "(SĐT)", "(kg)", "(VNĐ/km)", "(mô tả)", "(active/inactive)", "(ghi chú)"])
    ws.append([vehicle_id, "Tai xe upload B", "0900000009", 1000, None, None, "active", None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


COMPANY_A = "00000000-0000-0000-0000-000000000001"
COMPANY_B = str(uuid.uuid4())
USER_B = str(uuid.uuid4())
SHARED_VEHICLE_ID = f"TEST-UP-SHARED-{uuid.uuid4().hex[:6]}"

db = SessionLocal()
try:
    db.add(Company(company_id=COMPANY_B, name="Test Company B (upload isolation)"))
    db.add(User(user_id=USER_B, company_id=COMPANY_B, email=f"test-up-b-{uuid.uuid4().hex[:6]}@test.local", password_hash="x", role="dispatcher", full_name="Test Upload B"))
    db.add(Vehicle(vehicle_id=SHARED_VEHICLE_ID, company_id=COMPANY_A, driver_name="Tai xe A goc", driver_phone="0900000000", max_payload_kg=1000))
    db.commit()

    token_b = create_access_token(USER_B, COMPANY_B, "dispatcher")
    xlsx_bytes = build_vehicle_xlsx(SHARED_VEHICLE_ID)

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.post(
            "/api/vehicles/upload",
            files={"file": ("vehicles.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        check("Upload xe trùng ID với công ty khác -> 400 (KHÔNG PHẢI 500 crash)", resp.status_code == 400)
        try:
            detail = resp.json().get("detail", "")
        except Exception:  # noqa: BLE001
            detail = f"<không parse được JSON, status={resp.status_code}, body={resp.text[:200]}>"
        print("  detail thực tế:", detail)
        check("  thông báo nói rõ 'công ty khác'", "công ty khác" in str(detail))

    # Xác nhận vehicle gốc của company A không bị ai đó ghi đè bởi lần upload lỗi này
    unchanged = db.get(Vehicle, SHARED_VEHICLE_ID, execution_options={"skip_tenant_filter": True})
    check("Xe gốc của company A không bị đổi tên tài xế", unchanged is not None and unchanged.driver_name == "Tai xe A goc")

finally:
    db.query(Vehicle).filter(Vehicle.vehicle_id == SHARED_VEHICLE_ID).delete(synchronize_session=False)
    db.query(User).filter(User.user_id == USER_B).delete(synchronize_session=False)
    db.query(Company).filter(Company.company_id == COMPANY_B).delete(synchronize_session=False)
    db.commit()
    db.close()
    print("Đã dọn dữ liệu test.")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
