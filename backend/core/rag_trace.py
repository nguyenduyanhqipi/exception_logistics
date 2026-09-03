"""rag_trace.py — mã hoá/giải mã bảng ánh xạ `rag_case_source_map` + quy
trình yêu cầu tra vết 2 người (TECHNICAL_SPEC.md mục 20.3).

KHOÁ TÁCH 2 NGƯỜI: `K = K1 XOR K2` — K1 do founder giữ (password manager cá
nhân, KHÔNG đưa vào .env/server), K2 do 1 người thứ hai được chỉ định giữ
(vd kỹ thuật trưởng). Module này KHÔNG bao giờ đọc/lưu K từ 1 biến môi trường
DUY NHẤT hay hardcode nó ở đâu cả — mọi hàm ở đây nhận `key`/`k1`+`k2` như
THAM SỐ TƯỜNG MINH do caller cung cấp tại thời điểm gọi, dùng xong không giữ
lại. Việc 2 nửa khoá đó đến từ đâu lúc runtime (secrets manager, nhập tay qua
công cụ giải mã riêng tách khỏi ứng dụng chính...) là quyết định vận hành/
triển khai, KHÔNG thuộc phạm vi module này quyết định.

Giải mã CHỈ được phép khi `rag_trace_requests.status == 'approved'` — tức đã
qua đúng quy trình phê duyệt chéo (`requested_by != approved_by`, four-eyes,
CHECK constraint ở DB + kiểm tra lại ở tầng ứng dụng). Sau khi giải mã, request
chuyển 'completed' — KHÔNG lưu lại bản rõ ở đâu (không ghi vào DB, không log
ra file), chỉ trả về 1 lần cho caller hiển thị.
"""
import os
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AuditLog, RagCaseSourceMap, RagTraceRequest

_NONCE_BYTES = 12


class TraceRequestError(RuntimeError):
    """Yêu cầu tra vết vi phạm quy tắc (four-eyes, sai trạng thái...)."""


def combine_key(k1: bytes, k2: bytes) -> bytes:
    if len(k1) != len(k2):
        raise ValueError("K1 và K2 phải cùng độ dài")
    return bytes(a ^ b for a, b in zip(k1, k2))


def encrypt_value(value: str, key: bytes) -> bytes:
    """AES-256-GCM — trả về nonce(12 byte) + ciphertext+tag, gộp 1 blob duy
    nhất (tiện lưu thẳng vào cột BYTEA, không cần cột nonce riêng)."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt_value(blob: bytes, key: bytes) -> str:
    aesgcm = AESGCM(key)
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def _write_audit_log(db: Session, company_id, user_id, detail: dict):
    db.add(
        AuditLog(
            company_id=company_id,
            user_id=user_id,
            action="rag_trace_lookup",
            entity_type="rag_trace_request",
            entity_id=detail.get("request_id"),
            detail=detail,
        )
    )


def create_trace_request(db: Session, requester_company_id, case_id, requested_by: str, reason: str) -> RagTraceRequest:
    if not reason or not reason.strip():
        raise TraceRequestError("Phải nêu lý do tra vết (reason bắt buộc)")
    request = RagTraceRequest(case_id=case_id, requested_by=requested_by, reason=reason, status="pending")
    db.add(request)
    db.flush()
    _write_audit_log(
        db, requester_company_id, requested_by,
        {"request_id": str(request.request_id), "case_id": str(case_id), "requested_by": str(requested_by), "reason": reason, "status": "pending"},
    )
    db.commit()
    db.refresh(request)
    return request


def approve_trace_request(db: Session, approver_company_id, request_id: str, approved_by: str) -> RagTraceRequest:
    """Phê duyệt (bước 1/2 của four-eyes — chưa giải mã gì ở đây, chỉ chuyển
    trạng thái). Từ chối tự phê duyệt yêu cầu CHÍNH MÌNH tạo ra — kiểm tra lại
    ở tầng ứng dụng dù DB đã có CHECK constraint, để trả lỗi rõ ràng thay vì
    IntegrityError thô."""
    request = db.get(RagTraceRequest, request_id)
    if request is None:
        raise TraceRequestError(f"Không tìm thấy yêu cầu tra vết {request_id}")
    if request.status != "pending":
        raise TraceRequestError(f"Yêu cầu đang ở trạng thái '{request.status}', không thể phê duyệt")
    if str(request.requested_by) == str(approved_by):
        raise TraceRequestError("Người phê duyệt phải KHÁC người đã khởi tạo yêu cầu (four-eyes)")

    request.status = "approved"
    request.approved_by = approved_by
    request.approved_at = datetime.now(timezone.utc)
    _write_audit_log(
        db, approver_company_id, approved_by,
        {"request_id": str(request.request_id), "case_id": str(request.case_id), "approved_by": str(approved_by), "status": "approved"},
    )
    db.commit()
    db.refresh(request)
    return request


def reject_trace_request(db: Session, approver_company_id, request_id: str, approved_by: str, reason: "str | None" = None) -> RagTraceRequest:
    request = db.get(RagTraceRequest, request_id)
    if request is None:
        raise TraceRequestError(f"Không tìm thấy yêu cầu tra vết {request_id}")
    if request.status != "pending":
        raise TraceRequestError(f"Yêu cầu đang ở trạng thái '{request.status}', không thể từ chối")
    if str(request.requested_by) == str(approved_by):
        raise TraceRequestError("Người từ chối phải KHÁC người đã khởi tạo yêu cầu (four-eyes)")

    request.status = "rejected"
    request.approved_by = approved_by
    _write_audit_log(
        db, approver_company_id, approved_by,
        {"request_id": str(request.request_id), "case_id": str(request.case_id), "approved_by": str(approved_by), "status": "rejected", "reject_reason": reason},
    )
    db.commit()
    db.refresh(request)
    return request


def decrypt_trace(db: Session, request_id: str, k1: bytes, k2: bytes, performed_by_company_id, performed_by_user_id) -> dict:
    """Bước 2/2 của four-eyes — ĐÚNG 2 người cùng nhập nửa khoá của mình vào
    công cụ giải mã (tách khỏi ứng dụng chính) mới gọi được hàm này. Trả về
    plaintext {company_id, exception_id} ĐÚNG 1 LẦN — KHÔNG cache/lưu lại ở
    bất kỳ đâu, caller chịu trách nhiệm không log/lưu giá trị trả về.

    `performed_by_company_id`/`performed_by_user_id`: audit_logs.company_id/
    user_id NOT NULL (mọi bảng khác trong hệ thống đều bắt buộc gắn 1 công ty
    dù đây là hành động cross-tenant) — dùng công ty/tài khoản của người BẤM
    NÚT giải mã (1 trong 2 người platform_admin), không phải công ty của case
    đang tra vết (case đó chính là thứ CHƯA được biết cho tới khi giải mã)."""
    request = db.get(RagTraceRequest, request_id)
    if request is None:
        raise TraceRequestError(f"Không tìm thấy yêu cầu tra vết {request_id}")
    if request.status != "approved":
        raise TraceRequestError(f"Yêu cầu chưa được phê duyệt (trạng thái hiện tại: '{request.status}')")

    source = db.execute(select(RagCaseSourceMap).where(RagCaseSourceMap.case_id == request.case_id)).scalar_one_or_none()
    if source is None:
        raise TraceRequestError(f"Không có bản ghi ánh xạ nguồn cho case {request.case_id}")

    key = combine_key(k1, k2)
    company_id = decrypt_value(source.company_id_encrypted, key)
    exception_id = decrypt_value(source.exception_id_encrypted, key)

    request.status = "completed"
    request.completed_at = datetime.now(timezone.utc)
    _write_audit_log(
        db, performed_by_company_id, performed_by_user_id,
        {"request_id": str(request.request_id), "case_id": str(request.case_id), "status": "completed"},
    )
    db.commit()

    return {"company_id": company_id, "exception_id": exception_id}
