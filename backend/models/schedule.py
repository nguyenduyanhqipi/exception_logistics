from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from models.base import Base, UUID_SERVER_DEFAULT


class Schedule(Base):
    __tablename__ = "schedules"
    __table_args__ = (
        Index(
            "uq_schedules_vehicle_trip",
            "company_id",
            "vehicle_id",
            "shift_date",
            "shift_label",
            "trip_sequence",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    schedule_id = Column(UUID(as_uuid=True), primary_key=True, server_default=UUID_SERVER_DEFAULT)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    vehicle_id = Column(Text, ForeignKey("vehicles.vehicle_id"), nullable=False)
    shift_date = Column(Date, nullable=False)
    shift_label = Column(Text, nullable=False)
    trip_sequence = Column(Integer, nullable=False, server_default="1")
    depot_arrival_time = Column(Time, nullable=True)
    depot_loading_duration_min = Column(Integer, nullable=True)
    planned_departure_time = Column(Time, nullable=True)
    depot_address = Column(Text, nullable=True)
    stops = Column(JSONB, nullable=False, server_default="[]")
    status = Column(Text, nullable=False, server_default="active")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    deleted_at = Column(DateTime(timezone=True), nullable=True)
