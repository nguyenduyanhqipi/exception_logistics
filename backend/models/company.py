from sqlalchemy import Column, DateTime, Numeric, Text, text
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
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
