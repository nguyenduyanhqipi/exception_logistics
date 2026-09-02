from sqlalchemy import Boolean, Column, DateTime, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from models.base import Base, UUID_SERVER_DEFAULT


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    version_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    sub_type = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RuleVersion(Base):
    __tablename__ = "rule_versions"

    version_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    rule_key = Column(Text, nullable=False)
    conditions = Column(JSONB, nullable=False)
    result = Column(JSONB, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
