"""add resolution_type to outcomes

Revision ID: a7b8c9d0e1f2
Revises: c8d9e0f1a2b3
Create Date: 2026-09-10 00:00:00.000000

Redesign form nhập kết quả thực tế (đợt code 5, Pha 2 —
Claude outputs/dot_code_5/outcome_form_redesign.md).

Form outcome trước đây dùng CHUNG 1 hình dạng cho mọi sub_type: "đúng giờ /
muộn giờ" -> số phút muộn -> chi phí. Câu hỏi đó vô nghĩa với nhóm khách từ
chối nhận hàng (`customer_absent`, `customer_dispute`): hàng còn chưa giao
được thì "đúng giờ hay muộn giờ" không có gì để trả lời. Hai sub_type đó
chuyển sang hỏi "kết quả cuối cùng là gì" — giao lại thành công / trả hàng về
kho / khách huỷ đơn / khác — và câu trả lời đó lưu vào cột này.

NULL = outcome "kiểu tiến độ" (9/11 sub_type còn lại), giữ nguyên ý nghĩa 4
field cũ, KHÔNG cần migrate dữ liệu: mọi outcome ghi trước migration này đều
thuộc kiểu đó.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('outcomes', sa.Column('resolution_type', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('outcomes', 'resolution_type')
