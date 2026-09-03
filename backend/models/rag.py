"""RAG cross-tenant case bank (TECHNICAL_SPEC.md mục 20) — kho case DÙNG
CHUNG mọi công ty, đã ẩn danh hoá. KHÔNG đưa các model dưới đây vào
database.py::_TENANT_MODELS — case dùng chung, không lọc theo company_id của
request hiện tại (đúng bản chất cross-tenant, khác mọi bảng khác trong hệ
thống). Xem docstring migration e4f5a6b7c8d9 và
"Claude outputs/rag_cross_tenant_spec_addition.md" mục 20 để biết đầy đủ
thiết kế/lý do.
"""
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base, UUID_SERVER_DEFAULT


class RagCaseBank(Base):
    """1 case đã qua pipeline ẩn danh hoá (core/rag_anonymization.py) — KHÔNG
    có company_id/exception_id trực tiếp, `case_id` không suy ra ngược được
    exception gốc. Chỉ nạp case "trọn vẹn" (đã có outcome), sau độ trễ có chủ
    đích (`admitted_at` lệch `reported_at` thật)."""

    __tablename__ = "rag_case_bank"

    case_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    exception_group = Column(Text, nullable=False)
    sub_type = Column(Text, nullable=False)
    severity = Column(Text, nullable=True)
    # Bucket hoá — TUYỆT ĐỐI không lưu address/eta/sla_deadline/volume_kg
    # chính xác (xem mục 20.1, k-anonymity mục 20.2).
    area_bucket = Column(Text, nullable=True)
    shift_label = Column(Text, nullable=True)
    time_to_deadline_bucket = Column(Text, nullable=True)
    downstream_stops_affected = Column(Integer, nullable=True)
    has_priority_order = Column(Boolean, nullable=True)
    cargo_type = Column(Text, nullable=True)
    volume_kg_bucket = Column(Text, nullable=True)
    notes_redacted = Column(Text, nullable=True)
    option_cost_estimate = Column(Numeric, nullable=True)
    option_time_estimate_minutes = Column(Integer, nullable=True)
    option_sla_risk_remaining = Column(Numeric, nullable=True)
    outcome_delivered_on_time = Column(Boolean, nullable=True)
    # Tỷ lệ %, KHÔNG phải actual_cost tuyệt đối (mục 20.1 — số tiền tuyệt đối
    # dễ gợi ý quy mô/đơn hàng cụ thể hơn tỷ lệ).
    outcome_cost_variance_pct = Column(Numeric, nullable=True)
    embedding = Column(Vector(768), nullable=True)
    admitted_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RagCaseSourceMap(Base):
    """Bảng ánh xạ truy vết — TÁCH RIÊNG HOÀN TOÀN khỏi mọi query retrieval
    bình thường (không JOIN ở option_generator.py/ranker.py). company_id/
    exception_id lưu Ở DẠNG MÃ HOÁ (AES-256-GCM, khoá K = K1 XOR K2 — xem
    core/rag_trace.py), vô nghĩa nếu không kết hợp đủ 2 nửa khoá."""

    __tablename__ = "rag_case_source_map"

    case_id = Column(UUID(as_uuid=True), ForeignKey("rag_case_bank.case_id"), primary_key=True)
    company_id_encrypted = Column(LargeBinary, nullable=False)
    exception_id_encrypted = Column(LargeBinary, nullable=False)
    mapped_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RagTraceRequest(Base):
    """Yêu cầu tra vết — bắt buộc 2 người khác nhau (four-eyes, CHECK
    `approved_by != requested_by`) mới giải mã tra vết được 1 case. Ghi vào
    `audit_logs` (action='rag_trace_lookup') ở mọi trạng thái, kể cả bị từ
    chối — xem core/rag_trace.py."""

    __tablename__ = "rag_trace_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'completed')", name="ck_rag_trace_requests_status"),
        CheckConstraint("approved_by IS NULL OR approved_by != requested_by", name="ck_rag_trace_requests_four_eyes"),
    )

    request_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    case_id = Column(UUID(as_uuid=True), ForeignKey("rag_case_bank.case_id"), nullable=False)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    reason = Column(Text, nullable=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    status = Column(Text, nullable=False, server_default="pending")
    requested_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    approved_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
