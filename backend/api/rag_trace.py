"""api/rag_trace.py — quy trình yêu cầu tra vết 2 người (mục 20.3). CHỈ có
tạo/duyệt/từ chối/liệt kê yêu cầu — CỐ Ý KHÔNG có endpoint giải mã nào ở đây:
spec yêu cầu công cụ giải mã phải "tách khỏi ứng dụng chính, không phải 1 API
công khai" (mục 20.3) — xem scripts/rag_decrypt_tool.py (chạy tay, 2 người
cùng nhập nửa khoá của mình).

Quyền hạn: role mới `platform_admin` (mục 20.3, cấp NỀN TẢNG không theo
company) — dùng lại `require_role()` sẵn có (middleware/rbac.py), không cần
cơ chế quyền mới. rag_trace_requests/rag_case_bank KHÔNG nằm trong
`database.py::_TENANT_MODELS` nên không bị lọc theo company_id của
platform_admin đang gọi — đúng bản chất cross-tenant.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.rag_trace import TraceRequestError, approve_trace_request, create_trace_request, reject_trace_request
from middleware.rbac import require_role
from middleware.tenant import get_db
from models import RagTraceRequest

router = APIRouter(prefix="/api/rag-trace", tags=["rag-trace"])


class TraceRequestCreate(BaseModel):
    case_id: str
    reason: str = Field(min_length=1)


class TraceRequestActionPayload(BaseModel):
    reason: "str | None" = None


def _to_dict(r: RagTraceRequest) -> dict:
    return {
        "request_id": str(r.request_id),
        "case_id": str(r.case_id),
        "requested_by": str(r.requested_by),
        "reason": r.reason,
        "approved_by": str(r.approved_by) if r.approved_by else None,
        "status": r.status,
        "requested_at": r.requested_at.isoformat() if r.requested_at else None,
        "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


@router.post("/requests", status_code=status.HTTP_201_CREATED)
def create_request(
    payload: TraceRequestCreate,
    current_user: dict = Depends(require_role("platform_admin")),
    db: Session = Depends(get_db),
):
    try:
        request = create_trace_request(db, current_user["company_id"], payload.case_id, current_user["user_id"], payload.reason)
    except TraceRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _to_dict(request)


@router.get("/requests")
def list_requests(
    current_user: dict = Depends(require_role("platform_admin")),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(RagTraceRequest).order_by(RagTraceRequest.requested_at.desc())).scalars().all()
    return [_to_dict(r) for r in rows]


@router.post("/requests/{request_id}/approve")
def approve_request(
    request_id: str,
    current_user: dict = Depends(require_role("platform_admin")),
    db: Session = Depends(get_db),
):
    try:
        request = approve_trace_request(db, current_user["company_id"], request_id, current_user["user_id"])
    except TraceRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _to_dict(request)


@router.post("/requests/{request_id}/reject")
def reject_request(
    request_id: str,
    payload: TraceRequestActionPayload,
    current_user: dict = Depends(require_role("platform_admin")),
    db: Session = Depends(get_db),
):
    try:
        request = reject_trace_request(db, current_user["company_id"], request_id, current_user["user_id"], reason=payload.reason)
    except TraceRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _to_dict(request)
