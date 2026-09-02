"""Test hard limit + logging llm_usage_logs (BUILD_PLAN.md bước 6.6). Hạ tạm
`daily_limit=2` để test nhanh, mock `generate` để không tốn quota Gemini thật.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from models import LLMUsageLog
from core.llm_adapter import LLMCallResult
import core.option_generator as og
from core.option_generator import QuotaExceededError

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


company_id = "00000000-0000-0000-0000-000000000001"
db = SessionLocal()

before_count = db.query(LLMUsageLog).filter(LLMUsageLog.company_id == company_id).count()


def fake_generate_good(prompt):
    text = '{"options": [{"description": "d", "rationale": "r", "cost_estimate": 1000, "time_estimate_minutes": 10, "sla_risk_remaining": 0.1, "explanation": "e"}]}'
    return LLMCallResult(text, 100, 50, 200, success=True)


try:
    with patch("core.option_generator.generate", side_effect=fake_generate_good):
        # Lần 1: còn hạn mức (limit=2, đang có 0 call mới trong test này — nhưng
        # DB có thể có sẵn call cũ từ hôm nay, nên dùng limit tương đối: before_count + 2)
        limit = before_count + 2

        options1, usage1 = og._call_llm_with_retry("prompt 1", db=db, company_id=company_id, daily_limit=limit)
        check("Lần gọi 1: thành công", usage1["success"] is True)

        options2, usage2 = og._call_llm_with_retry("prompt 2", db=db, company_id=company_id, daily_limit=limit)
        check("Lần gọi 2: thành công", usage2["success"] is True)

        # Lần 3: đã chạm limit (before_count+2), phải raise QuotaExceededError
        raised = False
        try:
            og._call_llm_with_retry("prompt 3", db=db, company_id=company_id, daily_limit=limit)
        except QuotaExceededError as exc:
            raised = True
            print("QuotaExceededError message:", exc)
        check("Lần gọi 3: bị chặn đúng bằng QuotaExceededError rõ ràng", raised)

        after_count = db.query(LLMUsageLog).filter(LLMUsageLog.company_id == company_id).count()
        check("llm_usage_logs ghi đúng 2 dòng mới (không ghi dòng cho lần bị chặn)", after_count - before_count == 2)

        log = db.query(LLMUsageLog).filter(LLMUsageLog.company_id == company_id).order_by(LLMUsageLog.created_at.desc()).first()
        check("log gần nhất có tokens_in/out/cost_usd/latency_ms hợp lệ", log.tokens_in == 100 and log.tokens_out == 50 and log.cost_usd is not None and log.latency_ms == 200)

finally:
    new_logs = (
        db.query(LLMUsageLog)
        .filter(LLMUsageLog.company_id == company_id)
        .order_by(LLMUsageLog.created_at.desc())
        .limit(2)
        .all()
    )
    for log in new_logs:
        db.delete(log)
    db.commit()
    db.close()
    print("Đã dọn dữ liệu test (chỉ xóa 2 log mới tạo trong test này).")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
