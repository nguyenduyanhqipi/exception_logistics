from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base, UUID_SERVER_DEFAULT


class Option(Base):
    __tablename__ = "options"

    option_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    exception_id = Column(UUID(as_uuid=True), ForeignKey("exceptions.exception_id"), nullable=True)
    group_id = Column(UUID(as_uuid=True), ForeignKey("exception_groups.group_id"), nullable=True)
    description = Column(Text, nullable=False)
    score = Column(Numeric, nullable=True)
    cost_estimate = Column(Numeric, nullable=True)
    time_estimate_minutes = Column(Integer, nullable=True)
    sla_risk_remaining = Column(Numeric, nullable=True)
    llm_explanation = Column(Text, nullable=True)
    prompt_version_id = Column(UUID(as_uuid=True), ForeignKey("prompt_versions.version_id"), nullable=True)
    rank = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
