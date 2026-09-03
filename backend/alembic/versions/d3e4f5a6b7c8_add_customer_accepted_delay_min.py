"""add customer_accepted_delay_min to exceptions

Revision ID: d3e4f5a6b7c8
Revises: 6987af251ab8
Create Date: 2026-09-03 00:00:00.000000

Mục F (2026-09-03): dispatcher có thể ghi nhận khách đã chủ động chấp nhận
trễ tối đa bao nhiêu phút so với SLA gốc (hỏi 2 bước, optional, chỉ hiện cho
exception_group có khả năng gây trễ — xem NewException.tsx). CHỈ dùng ở bước
ranking (ranker.py, ưu tiên phương án rẻ hơn khi delay ước tính nằm trong
buffer khách đã chấp nhận) — KHÔNG được đụng tới impact_analysis/sla_breach,
số liệu đó nuôi báo cáo KPI thật (on_time_rate).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, Sequence[str], None] = '6987af251ab8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('exceptions', sa.Column('customer_accepted_delay_min', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('exceptions', 'customer_accepted_delay_min')
