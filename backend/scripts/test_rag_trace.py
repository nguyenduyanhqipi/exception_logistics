"""Test core/rag_trace.py — mã hoá/giải mã đối xứng (encrypt_value/decrypt_value/
combine_key) THUẦN không cần DB, + quy trình 4 mắt (four-eyes) CẦN DB thật
(rag_trace_requests, audit_logs, FK tới users có sẵn). Tự dọn dữ liệu test."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select

from database import SessionLocal
from core.rag_trace import (
    TraceRequestError,
    approve_trace_request,
    combine_key,
    create_trace_request,
    decrypt_trace,
    decrypt_value,
    encrypt_value,
    reject_trace_request,
)
from models import AuditLog, RagCaseBank, RagCaseSourceMap, RagTraceRequest, User

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


# ---- combine_key / encrypt_value / decrypt_value: THUẦN, không cần DB ----
k1 = os.urandom(32)
k2 = os.urandom(32)
key = combine_key(k1, k2)
check("combine_key trả đúng độ dài (256-bit)", len(key) == 32)
check("XOR đối xứng: combine(k1,k2) == combine(k2,k1)", combine_key(k1, k2) == combine_key(k2, k1))

blob = encrypt_value("company-123", key)
check("encrypt_value không trả về plaintext trần", b"company-123" not in blob)
check("decrypt_value với ĐÚNG khoá trả lại đúng giá trị gốc", decrypt_value(blob, key) == "company-123")

wrong_key = combine_key(os.urandom(32), k2)  # sai k1
try:
    decrypt_value(blob, wrong_key)
    check("decrypt_value với SAI khoá phải raise lỗi (không âm thầm trả rác)", False)
except Exception:
    check("decrypt_value với SAI khoá phải raise lỗi (không âm thầm trả rác)", True)

try:
    combine_key(os.urandom(16), os.urandom(32))
    check("combine_key với 2 khoá khác độ dài phải raise", False)
except ValueError:
    check("combine_key với 2 khoá khác độ dài phải raise", True)

# ---- Quy trình 4 mắt: CẦN DB thật ----
db = SessionLocal()
try:
    users = db.execute(select(User).limit(2)).scalars().all()
    if len(users) < 2:
        print("Bỏ qua phần test DB — cần ít nhất 2 user có sẵn trong DB (chạy scripts/seed_demo_users.py trước).")
    else:
        user_a, user_b = users[0], users[1]

        case = RagCaseBank(exception_group="__test_trace__", sub_type="__test__", area_bucket=None, shift_label=None)
        db.add(case)
        db.flush()
        db.add(
            RagCaseSourceMap(
                case_id=case.case_id,
                company_id_encrypted=encrypt_value("real-company-id", key),
                exception_id_encrypted=encrypt_value("real-exception-id", key),
            )
        )
        db.commit()

        # requested_by == approved_by -> phải bị chặn NGAY LÚC TẠO qua approve (four-eyes)
        request = create_trace_request(db, user_a.company_id, case.case_id, str(user_a.user_id), "Test lý do tra vết")
        check("create_trace_request trả status='pending'", request.status == "pending")

        try:
            approve_trace_request(db, user_a.company_id, str(request.request_id), str(user_a.user_id))
            check("KHÔNG cho phép tự phê duyệt yêu cầu của chính mình", False)
        except TraceRequestError:
            check("KHÔNG cho phép tự phê duyệt yêu cầu của chính mình", True)

        # Chưa approved -> decrypt_trace phải chặn
        try:
            decrypt_trace(db, str(request.request_id), k1, k2, user_a.company_id, str(user_a.user_id))
            check("decrypt_trace chặn khi request CHƯA approved", False)
        except TraceRequestError:
            check("decrypt_trace chặn khi request CHƯA approved", True)

        approved = approve_trace_request(db, user_b.company_id, str(request.request_id), str(user_b.user_id))
        check("Người KHÁC phê duyệt được, status='approved'", approved.status == "approved")

        result = decrypt_trace(db, str(request.request_id), k1, k2, user_b.company_id, str(user_b.user_id))
        check("decrypt_trace trả đúng company_id gốc", result["company_id"] == "real-company-id")
        check("decrypt_trace trả đúng exception_id gốc", result["exception_id"] == "real-exception-id")

        db.refresh(request)
        check("Sau khi giải mã, request chuyển 'completed'", request.status == "completed")

        # Sai nửa khoá -> giải mã thất bại (dù request đã approved) — cần request MỚI vì request cũ đã 'completed'
        request2 = create_trace_request(db, user_a.company_id, case.case_id, str(user_a.user_id), "Test lý do 2")
        approve_trace_request(db, user_b.company_id, str(request2.request_id), str(user_b.user_id))
        try:
            decrypt_trace(db, str(request2.request_id), os.urandom(32), k2, user_b.company_id, str(user_b.user_id))
            check("Sai nửa khoá K1 -> giải mã phải thất bại", False)
        except Exception:
            check("Sai nửa khoá K1 -> giải mã phải thất bại", True)

        # reject_trace_request: người khác từ chối được, tự từ chối bị chặn
        request3 = create_trace_request(db, user_a.company_id, case.case_id, str(user_a.user_id), "Test lý do 3")
        try:
            reject_trace_request(db, user_a.company_id, str(request3.request_id), str(user_a.user_id))
            check("KHÔNG cho phép tự từ chối yêu cầu của chính mình", False)
        except TraceRequestError:
            check("KHÔNG cho phép tự từ chối yêu cầu của chính mình", True)
        rejected = reject_trace_request(db, user_b.company_id, str(request3.request_id), str(user_b.user_id), reason="test")
        check("Người khác từ chối được, status='rejected'", rejected.status == "rejected")

        audit_count = len(
            db.execute(select(AuditLog).where(AuditLog.action == "rag_trace_lookup")).scalars().all()
        )
        check("Mọi request (kể cả bị từ chối) đều ghi audit_logs action='rag_trace_lookup'", audit_count >= 6)
finally:
    db.execute(delete(RagTraceRequest).where(RagTraceRequest.case_id.in_(
        select(RagCaseBank.case_id).where(RagCaseBank.exception_group == "__test_trace__")
    )))
    db.execute(delete(RagCaseSourceMap).where(RagCaseSourceMap.case_id.in_(
        select(RagCaseBank.case_id).where(RagCaseBank.exception_group == "__test_trace__")
    )))
    db.execute(delete(RagCaseBank).where(RagCaseBank.exception_group == "__test_trace__"))
    db.commit()
    db.close()

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
