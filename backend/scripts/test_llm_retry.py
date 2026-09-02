"""Test retry logic mục 8 (BUILD_PLAN.md bước 6.4) — mock llm_adapter.generate
trả về response sai định dạng JSON trước, rồi JSON hợp lệ sau, xác nhận
option_generator retry đúng và cuối cùng parse thành công."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm_adapter import LLMCallResult
import core.option_generator as og

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


# ---- Test 1: JSON có markdown code fence -> dọn sạch rồi parse được ngay (không cần gọi lại LLM) ----
call_count = {"n": 0}


def fake_generate_with_fence(prompt):
    call_count["n"] += 1
    text = '```json\n{"options": [{"description": "d", "rationale": "r", "cost_estimate": 1000, "time_estimate_minutes": 10, "sla_risk_remaining": 0.1, "explanation": "e"}]}\n```'
    return LLMCallResult(text, 10, 10, 100, success=True)


with patch("core.option_generator.generate", side_effect=fake_generate_with_fence):
    options, usage = og._call_llm_with_retry("fake prompt")
    check("Dọn code fence rồi parse thành công (1 lần gọi)", usage["success"] is True and call_count["n"] == 1)
    check("options có 1 phần tử", options is not None and len(options) == 1)

# ---- Test 2: 2 lần đầu trả JSON hỏng hoàn toàn, lần 3 mới đúng -> retry đúng 3 lần ----
call_count["n"] = 0


def fake_generate_bad_then_good(prompt):
    call_count["n"] += 1
    if call_count["n"] < 3:
        return LLMCallResult("Xin lỗi, tôi không thể trả lời dạng JSON lúc này.", 10, 5, 100, success=True)
    text = '{"options": [{"description": "d", "rationale": "r", "cost_estimate": 1000, "time_estimate_minutes": 10, "sla_risk_remaining": 0.1, "explanation": "e"}]}'
    return LLMCallResult(text, 10, 10, 100, success=True)


with patch("core.option_generator.generate", side_effect=fake_generate_bad_then_good):
    options, usage = og._call_llm_with_retry("fake prompt")
    check("Retry đúng 3 lần rồi mới thành công", call_count["n"] == 3)
    check("Cuối cùng parse thành công", usage["success"] is True)
    check("options có 1 phần tử", options is not None and len(options) == 1)

# ---- Test 3: cả 3 lần đều hỏng -> trả graceful failure (options=None), KHÔNG raise exception ----
call_count["n"] = 0


def fake_generate_always_bad(prompt):
    call_count["n"] += 1
    return LLMCallResult("không phải JSON", 10, 5, 100, success=True)


with patch("core.option_generator.generate", side_effect=fake_generate_always_bad):
    options, usage = og._call_llm_with_retry("fake prompt")
    check("Gọi đúng tối đa 3 lần rồi dừng (không lặp vô hạn)", call_count["n"] == 3)
    check("Thất bại graceful: options=None (không raise exception)", options is None)
    check("usage['success']=False", usage["success"] is False)

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
