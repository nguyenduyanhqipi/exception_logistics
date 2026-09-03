from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base, UUID_SERVER_DEFAULT


class Decision(Base):
    __tablename__ = "decisions"

    decision_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    exception_id = Column(UUID(as_uuid=True), ForeignKey("exceptions.exception_id"), nullable=True)
    group_id = Column(UUID(as_uuid=True), ForeignKey("exception_groups.group_id"), nullable=True)
    selected_option_id = Column(UUID(as_uuid=True), ForeignKey("options.option_id"), nullable=False)
    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    override_note = Column(Text, nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Outcome(Base):
    __tablename__ = "outcomes"

    outcome_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    decision_id = Column(UUID(as_uuid=True), ForeignKey("decisions.decision_id"), nullable=False)
    delivered_on_time = Column(Boolean, nullable=True)
    actual_cost = Column(Numeric, nullable=True)
    notes = Column(Text, nullable=True)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    # Mục 20.2 — NULL = chưa nạp vào rag_case_bank. Không phải trong schema
    # gốc của mục 20, thêm để pipeline biết case nào đã nạp rồi mà KHÔNG cần
    # tra ngược rag_case_source_map (map đã mã hoá, không query được theo
    # exception_id thật) — plaintext cột này chỉ nói "đã nạp hay chưa", không
    # tiết lộ case_id/nội dung case tương ứng.
    admitted_to_rag_at = Column(DateTime(timezone=True), nullable=True)
