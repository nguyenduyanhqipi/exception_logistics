from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base, UUID_SERVER_DEFAULT


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('dispatcher', 'manager')", name="ck_users_role"),
    )

    user_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    email = Column(Text, nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    full_name = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    deleted_at = Column(DateTime(timezone=True), nullable=True)
