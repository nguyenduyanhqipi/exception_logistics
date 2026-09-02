from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from models.base import Base, UUID_SERVER_DEFAULT


class ExceptionGroup(Base):
    __tablename__ = "exception_groups"
    __table_args__ = (
        CheckConstraint("mode IN ('independent', 'combined')", name="ck_exception_groups_mode"),
    )

    group_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    exception_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False)
    mode = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")


class Exception_(Base):
    __tablename__ = "exceptions"

    exception_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    schedule_id = Column(UUID(as_uuid=True), ForeignKey("schedules.schedule_id"), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey("exception_groups.group_id"), nullable=True)
    exception_group = Column(Text, nullable=False)
    sub_type = Column(Text, nullable=False)
    severity = Column(Text, nullable=True)
    vehicle_id = Column(Text, nullable=True)
    area = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="pending")
    reported_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    reported_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class ResourceLock(Base):
    __tablename__ = "resource_locks"

    lock_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    exception_id = Column(UUID(as_uuid=True), ForeignKey("exceptions.exception_id"), nullable=False)
    resource_type = Column(Text, nullable=False)
    resource_id = Column(Text, nullable=False)
    locked_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    expires_at = Column(DateTime(timezone=True), nullable=False)


class ImpactAnalysis(Base):
    __tablename__ = "impact_analysis"

    impact_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    exception_id = Column(UUID(as_uuid=True), ForeignKey("exceptions.exception_id"), nullable=False)
    affected_stops = Column(JSONB, nullable=False, server_default="[]")
    total_cost_estimate = Column(Numeric, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
