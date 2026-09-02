import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria

from core.tenant_context import current_company_id

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Các model có company_id — mọi SELECT qua Session đăng ký event bên dưới sẽ tự
# động bị lọc theo company_id của request hiện tại (đọc từ contextvar
# current_company_id, do middleware/tenant.py set khi vào request).
_TENANT_MODELS = []


def _load_tenant_models():
    from models import Decision, Exception_, ExceptionGroup, Schedule, User, Vehicle

    return [Vehicle, User, Schedule, Exception_, ExceptionGroup, Decision]


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_filter(execute_state):
    if not execute_state.is_select:
        return
    if execute_state.execution_options.get("skip_tenant_filter", False):
        return
    company_id = current_company_id.get()
    if company_id is None:
        return

    global _TENANT_MODELS
    if not _TENANT_MODELS:
        _TENANT_MODELS = _load_tenant_models()

    for model in _TENANT_MODELS:
        # Truyền thẳng biểu thức đã bind company_id (KHÔNG dùng lambda nhận
        # `cls` rồi tự tính company_id bên trong) — SQLAlchemy cache biểu thức
        # sinh ra từ dạng callable theo (entity, statement shape), không theo
        # giá trị đóng gói trong closure, nên request sau tái dùng nhầm giá
        # trị company_id của request trước. Xem docs with_loader_criteria().
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                model,
                model.company_id == company_id,
                include_aliases=True,
            )
        )
