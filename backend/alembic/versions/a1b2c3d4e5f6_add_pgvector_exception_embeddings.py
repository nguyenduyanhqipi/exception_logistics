"""add pgvector extension and exception_embeddings table

Revision ID: a1b2c3d4e5f6
Revises: c6cde1a087a1
Create Date: 2026-09-02 12:40:00.000000

Tách riêng khỏi migration đầu (mục 1.4/2.1 BUILD_PLAN.md): máy dev chưa có sẵn
pgvector cho PostgreSQL 17 (không có bản build sẵn chính thức cho Windows, cần
build từ source bằng Visual Studio Build Tools + quyền admin). Chạy migration
này sau khi đã `CREATE EXTENSION vector` thành công (xem hướng dẫn ở bước 1.4).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c6cde1a087a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table(
        'exception_embeddings',
        sa.Column('exception_id', sa.UUID(), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(768), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.ForeignKeyConstraint(['exception_id'], ['exceptions.exception_id'], ),
        sa.PrimaryKeyConstraint('exception_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('exception_embeddings')
    op.execute('DROP EXTENSION IF EXISTS vector')
