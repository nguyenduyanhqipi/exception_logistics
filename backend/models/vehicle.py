from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    vehicle_id = Column(Text, primary_key=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    driver_name = Column(Text, nullable=False)
    driver_phone = Column(Text, nullable=False)
    vehicle_type = Column(Text, nullable=True)
    max_payload_kg = Column(Numeric, nullable=False)
    cost_per_km = Column(Numeric, nullable=True)
    status = Column(Text, nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    deleted_at = Column(DateTime(timezone=True), nullable=True)
