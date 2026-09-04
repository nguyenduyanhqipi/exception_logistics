from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from models.base import Base, UUID_SERVER_DEFAULT


class Company(Base):
    __tablename__ = "companies"

    company_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    name = Column(Text, nullable=False)
    timezone = Column(Text, nullable=False, server_default="Asia/Ho_Chi_Minh")
    ranking_weights = Column(
        JSONB,
        nullable=False,
        server_default='{"cost":0.4,"time":0.3,"sla_risk":0.3}',
    )
    default_depot_address = Column(Text, nullable=True)
    default_depot_area = Column(Text, nullable=True)
    default_cost_per_km = Column(Numeric, nullable=False, server_default="8000")
    # Mục 20 — opt-in (mặc định false), KHÔNG opt-out: company chưa bật thì
    # option_generator KHÔNG được truy vấn rag_case_bank cho company đó.
    rag_data_sharing_consent = Column(Boolean, nullable=False, server_default="false")
    # Việc 3 (2026-09-04): sau bao nhiêu ngày kể từ `outcomes.recorded_at` thì
    # khoá không cho sửa kết quả nữa. NULL/0 = không khoá.
    outcome_edit_lock_days = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
