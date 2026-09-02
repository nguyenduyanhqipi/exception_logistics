from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, Text
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
    confirmed_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")


class Outcome(Base):
    __tablename__ = "outcomes"

    outcome_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    decision_id = Column(UUID(as_uuid=True), ForeignKey("decisions.decision_id"), nullable=False)
    delivered_on_time = Column(Boolean, nullable=True)
    actual_cost = Column(Numeric, nullable=True)
    notes = Column(Text, nullable=True)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
