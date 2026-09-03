"""add input_context to exceptions

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-09-04 00:00:00.000000

Cần cho tính năng SỬA ngoại lệ (việc 5, 2026-09-04). Lúc tạo ngoại lệ,
dispatcher nhập một loạt tín hiệu định lượng theo sub_type
(`departure_delay_min`, `estimated_traffic_duration_min`, `has_injury`...) —
rule_engine dùng chúng để chốt `severity` rồi VỨT BỎ, chỉ `severity` được lưu
lại. Hậu quả: khi mở form sửa, không có cách nào nạp lại đúng các số liệu đó;
người dùng chỉ sửa `description` thôi cũng làm severity bị tính lại KHÔNG có
tín hiệu gốc và tụt mức — đúng kiểu lệch KPI mà tính năng sửa sinh ra để
tránh.

Cột này lưu nguyên payload tín hiệu đầu vào (answer_key + các field định
lượng) để form sửa nạp lại được. NULL với mọi ngoại lệ tạo trước migration
này — form sửa khi đó để trống các ô tương ứng, người dùng nhập lại.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, Sequence[str], None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('exceptions', sa.Column('input_context', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('exceptions', 'input_context')
