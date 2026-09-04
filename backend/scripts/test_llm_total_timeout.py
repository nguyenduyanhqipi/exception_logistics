"""Test timeout MỖI LẦN THỬ cho _call_llm_with_retry (mục 8, nhóm D) — mock
generate() chạy chậm hơn ngân sách cho phép, xác nhận:

- mỗi lần thử bị cắt đúng lúc thay vì treo tới khi generate() tự trả về;
- vòng lặp vẫn chạy ĐỦ MAX_LLM_RETRIES lần, mỗi lần lãnh trọn ngân sách riêng
  (2026-09-04: đổi từ ngân sách CỘNG DỒN sang RIÊNG mỗi lần thử — bản cũ trừ
  dần theo elapsed nên lần 2/3 bị cắt ngang dù đang chạy bình thường);
- trả kết quả graceful (options=None, usage["error"] mô tả timeout) giống hệt
  nhánh lỗi AI hiện có.
"""
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


calls = []


def fake_generate_slow(prompt):
    calls.append(time.monotonic())
    time.sleep(2)
    return LLMCallResult('{"options": [{"description": "d"}]}', 10, 10, 2000, success=True)


BUDGET = 0.5

with patch("core.option_generator.generate", side_effect=fake_generate_slow):
    start = time.monotonic()
    options, usage = og._call_llm_with_retry("fake prompt", max_attempt_seconds=BUDGET)
    elapsed = time.monotonic() - start

# Mỗi lần thử bị cắt ở BUDGET giây -> tổng ~ MAX_LLM_RETRIES * BUDGET, thấp
# hơn hẳn 3 x 2s = 6s nếu vòng lặp ngồi chờ generate() chạy xong.
expected = og.MAX_LLM_RETRIES * BUDGET
check(
    f"Mỗi lần thử bị cắt đúng ngân sách (elapsed={elapsed:.2f}s, ~{expected:.1f}s, không phải 6s)",
    expected - 0.3 < elapsed < expected + 1.0,
)
check(
    f"Chạy ĐỦ {og.MAX_LLM_RETRIES} lần thử, không dừng sớm (đã gọi {len(calls)} lần)",
    len(calls) == og.MAX_LLM_RETRIES,
)
check("Trả graceful failure (options=None)", options is None)
check(
    "usage['error'] nhắc tới hết thời gian chờ",
    usage["error"] is not None and "thời gian" in usage["error"],
)
check(
    "usage['error'] nói rõ số lần đã thử + gợi ý nhập thủ công",
    usage["error"] is not None
    and f"đã thử {og.MAX_LLM_RETRIES} lần" in usage["error"]
    and "thủ công" in usage["error"],
)

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
