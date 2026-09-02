"""fix frozen now() server defaults

Revision ID: 6987af251ab8
Revises: a1b2c3d4e5f6
Create Date: 2026-09-02 17:53:14.543860

Bug thật (phát hiện lúc test UI Giai đoạn 8): `server_default="now()"` viết dạng
string trần trong các model SQLAlchemy bị Postgres hiểu là literal `'now()'`
rồi ÉP KIỂU/ĐÔNG CỨNG thành 1 giá trị timestamp cố định NGAY LÚC CHẠY
MIGRATION, thay vì hàm `now()` được Postgres gọi lại mỗi lần insert — y hệt
lỗi kinh điển "quoted 'now' freezes at DDL time" của Postgres. Hậu quả: MỌI
cột dùng `server_default="now()")` (created_at/reported_at/confirmed_at/...)
trên 18 cột thuộc gần hết các bảng đều bị đóng băng về đúng 1 thời điểm chạy
migration ban đầu — audit log, hàng đợi ưu tiên theo reported_at, cache
geocode... tất cả timestamp coi như vô nghĩa cho tới khi sửa. Models đã sửa
sang `server_default=text("now()")` (đúng, raw SQL, không bị quote) — migration
này ALTER lại default hiện có trong DB cho khớp.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6987af251ab8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AFFECTED_COLUMNS = [
    ("audit_logs", "created_at"),
    ("background_jobs", "created_at"),
    ("companies", "created_at"),
    ("decisions", "confirmed_at"),
    ("exception_embeddings", "created_at"),
    ("exception_groups", "created_at"),
    ("exceptions", "reported_at"),
    ("geocode_cache", "cached_at"),
    ("impact_analysis", "created_at"),
    ("llm_usage_logs", "created_at"),
    ("options", "created_at"),
    ("outcomes", "recorded_at"),
    ("prompt_versions", "created_at"),
    ("resource_locks", "locked_at"),
    ("rule_versions", "created_at"),
    ("schedules", "created_at"),
    ("users", "created_at"),
    ("vehicles", "created_at"),
]


def upgrade() -> None:
    for table, column in AFFECTED_COLUMNS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT now()")


def downgrade() -> None:
    # Không hạ về literal đông cứng cũ — đó chính là bug, không phải hành vi
    # mong muốn để rollback lại. Không có gì ý nghĩa để downgrade ở đây.
    pass
