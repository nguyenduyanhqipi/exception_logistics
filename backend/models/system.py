from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from models.base import Base, UUID_SERVER_DEFAULT


class LLMUsageLog(Base):
    __tablename__ = "llm_usage_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    company_id = Column(UUID(as_uuid=True), nullable=False)
    exception_id = Column(UUID(as_uuid=True), nullable=True)
    model = Column(Text, nullable=False)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    cost_usd = Column(Numeric, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    prompt_version_id = Column(UUID(as_uuid=True), nullable=True)
    success = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    company_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(Text, nullable=False)
    entity_type = Column(Text, nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    detail = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"

    cache_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    address_hash = Column(Text, nullable=False, unique=True)
    address_raw = Column(Text, nullable=False)
    coordinates = Column(JSONB, nullable=True)
    distance_matrix = Column(JSONB, nullable=True)
    cached_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    job_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    company_id = Column(UUID(as_uuid=True), nullable=False)
    exception_id = Column(UUID(as_uuid=True), nullable=True)
    job_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="pending")
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
