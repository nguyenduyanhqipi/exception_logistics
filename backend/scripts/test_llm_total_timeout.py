"""Test timeout tổng cho _call_llm_with_retry (mục 8, nhóm D) — mock generate()
chạy chậm hơn ngân sách cho phép, xác nhận vòng lặp dừng đúng lúc thay vì
treo tới khi generate() tự trả về, và trả kết quả graceful (options=None,
usage["error"] mô tả timeout) giống hệt nhánh lỗi AI hiện có."""
import sys
import time
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


def fake_generate_slow(prompt):
    time.sleep(2)
    return LLMCallResult('{"options": [{"description": "d"}]}', 10, 10, 2000, success=True)


with patch("core.option_generator.generate", side_effect=fake_generate_slow):
    start = time.monotonic()
    options, usage = og._call_llm_with_retry("fake prompt", max_total_seconds=0.5)
    elapsed = time.monotonic() - start
    check(f"Dừng sớm trong ngân sách (elapsed={elapsed:.2f}s, budget=0.5s)", elapsed < 1.5)
    check("Trả graceful failure (options=None)", options is None)
    check("usage['error'] nhắc tới hết thời gian chờ", usage["error"] is not None and "thời gian" in usage["error"])

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
