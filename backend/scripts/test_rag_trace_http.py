"""Test /api/rag-trace/* qua HTTP thật (không chỉ tầng hàm) — cần server đang
chạy ở http://127.0.0.1:8123 (hoặc set RAG_TEST_BASE_URL). Xác nhận: 403 khi
role không phải platform_admin, tạo/duyệt/từ chối hoạt động đúng qua API,
KHÔNG có endpoint giải mã nào lộ ra (404)."""
import os
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.security import create_access_token
from database import SessionLocal
from models import Company, RagCaseBank, RagTraceRequest, User
from sqlalchemy import delete, select

BASE_URL = os.environ.get("RAG_TEST_BASE_URL", "http://127.0.0.1:8123")

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


db = SessionLocal()
try:
    company = db.execute(select(Company)).scalars().first()
    users = db.execute(select(User).limit(2)).scalars().all()
    if company is None or len(users) < 2:
        print("Bỏ qua — cần ít nhất 1 company và 2 user có sẵn trong DB.")
        sys.exit(0)
    user_a, user_b = users[0], users[1]

    case = RagCaseBank(exception_group="__test_http__", sub_type="__test__")
    db.add(case)
    db.commit()
    case_id = str(case.case_id)

    dispatcher_token = create_access_token(str(user_a.user_id), str(company.company_id), "dispatcher")
    admin_a_token = create_access_token(str(user_a.user_id), str(company.company_id), "platform_admin")
    admin_b_token = create_access_token(str(user_b.user_id), str(company.company_id), "platform_admin")

    client = httpx.Client(base_url=BASE_URL, timeout=10)

    # ---- role thường (dispatcher) bị chặn 403 ----
    r = client.post("/api/rag-trace/requests", json={"case_id": case_id, "reason": "test"}, headers={"Authorization": f"Bearer {dispatcher_token}"})
    check("dispatcher (không phải platform_admin) bị 403 khi tạo request", r.status_code == 403)

    # ---- platform_admin tạo được ----
    r = client.post("/api/rag-trace/requests", json={"case_id": case_id, "reason": "test lý do"}, headers={"Authorization": f"Bearer {admin_a_token}"})
    check("platform_admin tạo request thành công (201)", r.status_code == 201)
    request_id = r.json()["request_id"]
    check("request mới có status='pending'", r.json()["status"] == "pending")

    # ---- tự phê duyệt bị chặn ----
    r = client.post(f"/api/rag-trace/requests/{request_id}/approve", headers={"Authorization": f"Bearer {admin_a_token}"})
    check("tự phê duyệt yêu cầu của chính mình bị chặn (400)", r.status_code == 400)

    # ---- người khác phê duyệt được ----
    r = client.post(f"/api/rag-trace/requests/{request_id}/approve", headers={"Authorization": f"Bearer {admin_b_token}"})
    check("người khác (platform_admin B) phê duyệt thành công", r.status_code == 200 and r.json()["status"] == "approved")

    # ---- list requests trả về đúng request vừa tạo ----
    r = client.get("/api/rag-trace/requests", headers={"Authorization": f"Bearer {admin_a_token}"})
    check("GET list requests trả 200", r.status_code == 200)
    check("request vừa tạo có trong danh sách", any(x["request_id"] == request_id for x in r.json()))

    # ---- KHÔNG có endpoint giải mã public nào (mục 20.3: tách khỏi ứng dụng chính) ----
    r = client.post(f"/api/rag-trace/requests/{request_id}/decrypt", headers={"Authorization": f"Bearer {admin_b_token}"})
    check("KHÔNG tồn tại endpoint /decrypt công khai (404)", r.status_code == 404)

    client.close()
finally:
    db.execute(delete(RagTraceRequest).where(RagTraceRequest.case_id.in_(
        select(RagCaseBank.case_id).where(RagCaseBank.exception_group == "__test_http__")
    )))
    db.execute(delete(RagCaseBank).where(RagCaseBank.exception_group == "__test_http__"))
    db.commit()
    db.close()

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
