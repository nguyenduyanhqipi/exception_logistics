"""add delay_minutes to outcomes

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-09-04 12:00:00.000000

Tách rời "chọn phương án" và "nhập kết quả" (việc 2, 2026-09-04). Khi
dispatcher ghi nhận kết quả thực tế là MUỘN GIỜ, phải nói rõ muộn bao nhiêu
phút — trước đây `outcomes` chỉ có cờ `delivered_on_time` nên "muộn 5 phút" và
"muộn 5 tiếng" ghi lại giống hệt nhau, không đối chiếu KPI được.

Nullable vì các outcome đã ghi trước migration này không có số liệu đó (và
outcome ĐÚNG GIỜ thì theo định nghĩa luôn để trống — xem
schemas/decision.py::OutcomeCreate).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a6b7c8d9e0f1'
down_revision: Union[str, Sequence[str], None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('outcomes', sa.Column('delay_minutes', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('outcomes', 'delay_minutes')
