from contextvars import ContextVar
from typing import Optional

current_company_id: ContextVar[Optional[str]] = ContextVar("current_company_id", default=None)
