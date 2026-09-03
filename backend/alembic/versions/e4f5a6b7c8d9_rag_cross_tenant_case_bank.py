"""RAG cross-tenant case bank (TECHNICAL_SPEC.md mục 20)

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-03 00:00:00.000000

Thay thế `exception_embeddings` (1 dòng = 1 exception_id trực tiếp, chưa từng
được option_generator.py dùng để retrieval) bằng kho case DÙNG CHUNG mọi công
ty, đã ẩn danh hoá — xem "Claude outputs/rag_cross_tenant_spec_addition.md"
mục 20 (quyết định 2026-09-03, trao đổi với founder ngoài phiên code) để biết
đầy đủ lý do/thiết kế. Tóm tắt:

- `rag_case_bank`: case đã ẩn danh hoá (bucket hoá area/thời gian/khối lượng,
  redact PII trong notes_redacted), id KHÔNG suy ra được từ exception_id gốc.
- `rag_case_source_map`: bảng ánh xạ TÁCH RIÊNG, company_id/exception_id lưu
  Ở DẠNG MÃ HOÁ (application-level, AES-256-GCM, khoá K = K1 XOR K2 — xem
  core/rag_trace.py) — không JOIN ở bất kỳ đường code retrieval bình thường
  nào, chỉ dùng trong luồng tra vết 2 người.
- `rag_trace_requests`: yêu cầu tra vết bắt buộc 2 người khác nhau
  (`requested_by` != `approved_by`, four-eyes principle).
- `companies.rag_data_sharing_consent`: mặc định false (opt-in) — company
  chưa bật thì option_generator KHÔNG được truy vấn rag_case_bank cho company
  đó (chưa wire retrieval thật, xem ghi chú trong core/option_generator.py).
- `users.role` CHECK mở rộng thêm `'platform_admin'` (quyền cấp NỀN TẢNG,
  không theo company — dùng cho tạo/duyệt rag_trace_requests).

`rag_case_bank`/`rag_case_source_map`/`rag_trace_requests` KHÔNG có cột
company_id trực tiếp (case dùng chung, ánh xạ ngược đã mã hoá riêng) — CỐ Ý
không đưa vào `database.py::_TENANT_MODELS`, tenant filter tự động không áp
dụng ở đây, đúng bản chất "dùng chung mọi công ty".
"""
from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # exception_embeddings chưa từng được option_generator.py dùng để
    # retrieval (xác nhận qua grep toàn backend) — an toàn để thay hẳn, không
    # có dữ liệu/luồng code nào phụ thuộc.
    op.drop_table('exception_embeddings')

    op.create_table(
        'rag_case_bank',
        sa.Column('case_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('exception_group', sa.Text(), nullable=False),
        sa.Column('sub_type', sa.Text(), nullable=False),
        sa.Column('severity', sa.Text(), nullable=True),
        sa.Column('area_bucket', sa.Text(), nullable=True),
        sa.Column('shift_label', sa.Text(), nullable=True),
        sa.Column('time_to_deadline_bucket', sa.Text(), nullable=True),
        sa.Column('downstream_stops_affected', sa.Integer(), nullable=True),
        sa.Column('has_priority_order', sa.Boolean(), nullable=True),
        sa.Column('cargo_type', sa.Text(), nullable=True),
        sa.Column('volume_kg_bucket', sa.Text(), nullable=True),
        sa.Column('notes_redacted', sa.Text(), nullable=True),
        sa.Column('option_cost_estimate', sa.Numeric(), nullable=True),
        sa.Column('option_time_estimate_minutes', sa.Integer(), nullable=True),
        sa.Column('option_sla_risk_remaining', sa.Numeric(), nullable=True),
        sa.Column('outcome_delivered_on_time', sa.Boolean(), nullable=True),
        sa.Column('outcome_cost_variance_pct', sa.Numeric(), nullable=True),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(768), nullable=True),
        sa.Column('admitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('case_id'),
    )

    op.create_table(
        'rag_case_source_map',
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('company_id_encrypted', sa.LargeBinary(), nullable=False),
        sa.Column('exception_id_encrypted', sa.LargeBinary(), nullable=False),
        sa.Column('mapped_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['rag_case_bank.case_id']),
        sa.PrimaryKeyConstraint('case_id'),
    )

    op.create_table(
        'rag_trace_requests',
        sa.Column('request_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('requested_by', sa.UUID(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('approved_by', sa.UUID(), nullable=True),
        sa.Column('status', sa.Text(), server_default='pending', nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['rag_case_bank.case_id']),
        sa.ForeignKeyConstraint(['requested_by'], ['users.user_id']),
        sa.ForeignKeyConstraint(['approved_by'], ['users.user_id']),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'completed')", name='ck_rag_trace_requests_status'),
        sa.CheckConstraint('approved_by IS NULL OR approved_by != requested_by', name='ck_rag_trace_requests_four_eyes'),
        sa.PrimaryKeyConstraint('request_id'),
    )

    op.add_column('companies', sa.Column('rag_data_sharing_consent', sa.Boolean(), server_default='false', nullable=False))

    # Không thuộc schema gốc mục 20.1 — cần để pipeline nạp (mục 20.2) biết
    # outcome nào đã nạp vào rag_case_bank rồi mà KHÔNG phải tra ngược
    # rag_case_source_map (map đã mã hoá, không query theo exception_id thật
    # được). Plaintext, chỉ nói "đã nạp hay chưa", không tiết lộ case_id nào.
    op.add_column('outcomes', sa.Column('admitted_to_rag_at', sa.DateTime(timezone=True), nullable=True))

    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.create_check_constraint('ck_users_role', 'users', "role IN ('dispatcher', 'manager', 'platform_admin')")


def downgrade() -> None:
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.create_check_constraint('ck_users_role', 'users', "role IN ('dispatcher', 'manager')")

    op.drop_column('outcomes', 'admitted_to_rag_at')
    op.drop_column('companies', 'rag_data_sharing_consent')

    op.drop_table('rag_trace_requests')
    op.drop_table('rag_case_source_map')
    op.drop_table('rag_case_bank')

    op.create_table(
        'exception_embeddings',
        sa.Column('exception_id', sa.UUID(), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(768), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['exception_id'], ['exceptions.exception_id']),
        sa.PrimaryKeyConstraint('exception_id'),
    )
