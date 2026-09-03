from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base, UUID_SERVER_DEFAULT


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # 'platform_admin' (mục 20.3) — quyền cấp NỀN TẢNG, không theo company,
        # dùng để tạo/duyệt rag_trace_requests (four-eyes: tối thiểu 2 người,
        # KHÔNG phải role thay thế cho dispatcher/manager của user đó). Vẫn
        # giữ company_id NOT NULL cho platform_admin (đơn giản hoá — họ vẫn là
        # 1 người dùng thật thuộc 1 company nào đó trong hệ thống, chỉ thêm
        # quyền cross-tenant qua role, không cần model "user không company").
        CheckConstraint("role IN ('dispatcher', 'manager', 'platform_admin')", name="ck_users_role"),
    )

    user_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    email = Column(Text, nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    full_name = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    deleted_at = Column(DateTime(timezone=True), nullable=True)
