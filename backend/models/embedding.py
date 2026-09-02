from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class ExceptionEmbedding(Base):
    __tablename__ = "exception_embeddings"

    exception_id = Column(UUID(as_uuid=True), ForeignKey("exceptions.exception_id"), primary_key=True)
    embedding = Column(Vector(768), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
