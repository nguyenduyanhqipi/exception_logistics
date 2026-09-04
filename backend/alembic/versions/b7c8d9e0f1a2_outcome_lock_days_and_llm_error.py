"""add companies.outcome_edit_lock_days and llm_usage_logs.error

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-09-04 18:00:00.000000

1) `companies.outcome_edit_lock_days` (việc 3, 2026-09-04): sau bao nhiêu ngày
   kể từ lúc ghi nhận kết quả thì khoá không cho sửa nữa. NULL hoặc 0 = không
   khoá (sửa tự do mãi mãi) — mặc định NULL để hành vi hiện tại không đổi.

2) `llm_usage_logs.error` (việc 4): bảng này trước chỉ có cờ boolean `success`,
   KHÔNG lưu thông báo lỗi. Hậu quả thật khi điều tra tỷ lệ lỗi AI ngày
   2026-09-04: nhìn được 18 lần gọi thất bại nhưng KHÔNG biết cái nào là hết
   hạn mức (429), cái nào là quá tải (503), cái nào là hết thời gian chờ —
   trong khi latency cho thấy rõ ít nhất 2 nhóm nguyên nhân khác hẳn nhau
   (nhóm ~90s = timeout, nhóm ~100-300ms = lỗi trả về tức thì). Không có cột
   này thì mọi kết luận đều là suy đoán.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'a6b7c8d9e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('outcome_edit_lock_days', sa.Integer(), nullable=True))
    op.add_column('llm_usage_logs', sa.Column('error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('llm_usage_logs', 'error')
    op.drop_column('companies', 'outcome_edit_lock_days')
