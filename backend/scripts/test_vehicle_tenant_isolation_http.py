"""Test tenant isolation cho POST /api/vehicles qua HTTP THẬT (không chỉ tầng
DB) — bug phát hiện qua review ngoài: `create_vehicle` check trùng xe bằng
`db.get(Vehicle, payload.vehicle_id)` không phân biệt company, khiến thông
báo lỗi "đã tồn tại" SAI khi thực ra vehicle_id đó thuộc công ty KHÁC.

Cần server đang chạy ở http://127.0.0.1:8000 (chạy `uvicorn main:app --port
8000` trước khi chạy script này).

Lưu ý quan trọng: `vehicle_id` là PK TOÀN CỤC (không composite theo
company_id, xem mục 4 TECHNICAL_SPEC.md) — 2 company KHÔNG THỂ cùng sở hữu 1
vehicle_id trong schema hiện tại (insert trùng PK sẽ vỡ ràng buộc DB). Fix ở
đây KHÔNG PHẢI "cho phép công ty B tạo trùng ID với công ty A" (chuyện đó đòi
hỏi đổi PK thành composite, ảnh hưởng FK `schedules.vehicle_id` — ngoài phạm
vi bug này) mà là: thông báo lỗi phải PHẢN ÁNH ĐÚNG SỰ THẬT (xe của công ty
khác, không phải "công ty bạn đã có xe này"), khớp đúng cách `upload_vehicles`
trong cùng file đã xử lý.
"""
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.security import create_access_token
from database import SessionLocal
from models import Company, User, Vehicle

BASE_URL = "http://127.0.0.1:8000"

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


COMPANY_A = "00000000-0000-0000-0000-000000000001"  # demo-company-001 có sẵn
COMPANY_B = str(uuid.uuid4())
USER_B = str(uuid.uuid4())
SHARED_VEHICLE_ID = f"TEST-SHARED-{uuid.uuid4().hex[:6]}"
UNIQUE_VEHICLE_ID_FOR_B = f"TEST-UNIQUE-B-{uuid.uuid4().hex[:6]}"

db = SessionLocal()
try:
    db.add(Company(company_id=COMPANY_B, name="Test Company B (tenant isolation)"))
    db.add(User(user_id=USER_B, company_id=COMPANY_B, email=f"test-b-{uuid.uuid4().hex[:6]}@test.local", password_hash="x", role="dispatcher", full_name="Test User B"))
    db.commit()

    user_a = db.query(User).filter(User.company_id == COMPANY_A).first()
    token_a = create_access_token(str(user_a.user_id), COMPANY_A, "dispatcher")
    token_b = create_access_token(USER_B, COMPANY_B, "dispatcher")

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        # ---- Bước 1: company A tạo xe SHARED_VEHICLE_ID -> thành công ----
        resp1 = client.post(
            "/api/vehicles",
            json={"vehicle_id": SHARED_VEHICLE_ID, "driver_name": "Tai xe A", "driver_phone": "0900000001", "max_payload_kg": 1000},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        check("Company A tạo xe mới lần đầu -> 201", resp1.status_code == 201)

        # ---- Bước 2: company A tạo LẠI đúng vehicle_id đó -> lỗi "đã tồn tại" (cùng công ty) ----
        resp2 = client.post(
            "/api/vehicles",
            json={"vehicle_id": SHARED_VEHICLE_ID, "driver_name": "Tai xe A2", "driver_phone": "0900000002", "max_payload_kg": 1000},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        check("Company A tạo trùng xe của CHÍNH mình -> 400", resp2.status_code == 400)
        check("  thông báo đúng 'đã tồn tại' (không nhắc công ty khác)", "đã tồn tại" in resp2.json()["detail"] and "công ty khác" not in resp2.json()["detail"])

        # ---- Bước 3 (TRỌNG TÂM BUG): company B tạo đúng vehicle_id mà company A đã có ----
        # Trước khi sửa: trả "Xe ... đã tồn tại" (SAI - công ty B chưa từng có xe này).
        # Sau khi sửa: vẫn phải chặn (PK toàn cục, xem docstring đầu file) nhưng
        # PHẢI là 400 sạch sẽ với thông báo đúng sự thật, KHÔNG BAO GIỜ được là
        # 500 (crash do vỡ ràng buộc PK ở tầng DB).
        resp3 = client.post(
            "/api/vehicles",
            json={"vehicle_id": SHARED_VEHICLE_ID, "driver_name": "Tai xe B", "driver_phone": "0900000003", "max_payload_kg": 1000},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        check("Company B tạo xe trùng ID với company A -> 400 (KHÔNG PHẢI 500 crash)", resp3.status_code == 400)
        detail3 = resp3.json().get("detail", "")
        check("  thông báo PHẢN ÁNH ĐÚNG SỰ THẬT: nói rõ 'công ty khác', không nói company B 'đã tồn tại'", "công ty khác" in detail3)
        print("  detail thực tế:", detail3)

        # ---- Bước 4: company B tạo xe với vehicle_id HOÀN TOÀN MỚI -> phải thành công bình thường ----
        resp4 = client.post(
            "/api/vehicles",
            json={"vehicle_id": UNIQUE_VEHICLE_ID_FOR_B, "driver_name": "Tai xe B rieng", "driver_phone": "0900000004", "max_payload_kg": 1200},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        check("Company B tạo xe với ID mới hoàn toàn (không đụng công ty nào) -> 201", resp4.status_code == 201)

finally:
    db.query(Vehicle).filter(Vehicle.vehicle_id.in_([SHARED_VEHICLE_ID, UNIQUE_VEHICLE_ID_FOR_B])).delete(synchronize_session=False)
    db.query(User).filter(User.user_id == USER_B).delete(synchronize_session=False)
    db.query(Company).filter(Company.company_id == COMPANY_B).delete(synchronize_session=False)
    db.commit()
    db.close()
    print("Đã dọn dữ liệu test.")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
