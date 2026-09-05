"""drop schedules.shift_label; trip key becomes (vehicle, date, trip_sequence)

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-09-05 00:00:00.000000

Bỏ hẳn khái niệm "ca" cố định (ca_sang/ca_chieu/ca_dem) khỏi kế hoạch: 1 chuyến
giờ được định danh bằng (company_id, vehicle_id, shift_date, trip_sequence).

XỬ LÝ VA CHẠM TRƯỚC KHI TẠO INDEX MỚI: bỏ `shift_label` khỏi khoá làm 2 chuyến
vốn khác nhau chỉ ở ca (VD B01 ngày 01/09 ca_sang chuyến 1 và ca_chieu chuyến
1) trở thành trùng khoá — index unique mới sẽ không tạo được. `seed_historical_
exceptions.py` sinh `shift_label` NGẪU NHIÊN với trip_sequence mặc định = 1 nên
va chạm kiểu này là chắc chắn có trên dữ liệu lịch sử. Nên trước khi tạo index,
dồn lại `trip_sequence` thành 1..N cho ĐÚNG những nhóm (công ty, xe, ngày) đang
va chạm — nhóm không va chạm giữ nguyên số chuyến cũ để không đổi số hiệu người
dùng đang quen.

`rag_case_bank.shift_label` KHÔNG bị đụng tới: đó là cột riêng của kho case
dùng chung, giữ nguyên giá trị lịch sử; case nạp mới từ nay sẽ có NULL ở đó
(xem core/rag_anonymization.py).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Chỉ đụng vào nhóm (company, vehicle, date) thực sự có >1 chuyến cùng
# trip_sequence sau khi bỏ shift_label.
_RENUMBER_CONFLICTS = """
WITH conflicted AS (
    SELECT DISTINCT company_id, vehicle_id, shift_date
    FROM (
        SELECT company_id, vehicle_id, shift_date, trip_sequence
        FROM schedules
        WHERE deleted_at IS NULL
        GROUP BY company_id, vehicle_id, shift_date, trip_sequence
        HAVING count(*) > 1
    ) dup
),
ranked AS (
    SELECT s.schedule_id,
           row_number() OVER (
               PARTITION BY s.company_id, s.vehicle_id, s.shift_date
               ORDER BY s.trip_sequence, s.created_at, s.schedule_id
           ) AS rn
    FROM schedules s
    JOIN conflicted c
      ON c.company_id = s.company_id
     AND c.vehicle_id = s.vehicle_id
     AND c.shift_date = s.shift_date
    WHERE s.deleted_at IS NULL
)
UPDATE schedules s
SET trip_sequence = r.rn
FROM ranked r
WHERE s.schedule_id = r.schedule_id
  AND s.trip_sequence <> r.rn
"""


def upgrade() -> None:
    op.execute(_RENUMBER_CONFLICTS)
    op.drop_index('uq_schedules_vehicle_trip', table_name='schedules')
    op.drop_column('schedules', 'shift_label')
    op.create_index(
        'uq_schedules_vehicle_trip',
        'schedules',
        ['company_id', 'vehicle_id', 'shift_date', 'trip_sequence'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    # Không khôi phục được giá trị `shift_label` cũ (đã bị drop) — mọi dòng
    # nhận 'ca_sang'. Chấp nhận: đây là đường lùi khẩn cấp, không phải đường
    # bảo toàn dữ liệu.
    op.drop_index('uq_schedules_vehicle_trip', table_name='schedules')
    op.add_column(
        'schedules',
        sa.Column('shift_label', sa.Text(), nullable=False, server_default='ca_sang'),
    )
    op.create_index(
        'uq_schedules_vehicle_trip',
        'schedules',
        ['company_id', 'vehicle_id', 'shift_date', 'shift_label', 'trip_sequence'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )
