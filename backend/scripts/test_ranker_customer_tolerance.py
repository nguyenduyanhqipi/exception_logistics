"""Test mục F — customer_accepted_delay_min chỉ ảnh hưởng ranking (dồn nửa
trọng số sla_risk sang cost khi customer_tolerant=True), KHÔNG đổi hành vi
mặc định khi customer_tolerant=False (backward-compatible với test_ranker.py)."""
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ranker import _apply_customer_tolerance, calculate_scores, rank_options

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


def opt(cost, time_min, sla_risk):
    return SimpleNamespace(cost_estimate=Decimal(cost), time_estimate_minutes=time_min, sla_risk_remaining=Decimal(str(sla_risk)), score=None, rank=None)


weights = {"cost": 0.4, "time": 0.3, "sla_risk": 0.3}

# ---- _apply_customer_tolerance: dồn đúng nửa sla_risk sang cost, giữ nguyên time, tổng vẫn = 1 ----
adjusted = _apply_customer_tolerance(weights, customer_tolerant=True)
check("cost tăng đúng 0.15 (nửa của 0.3)", abs(adjusted["cost"] - 0.55) < 1e-9)
check("time không đổi", adjusted["time"] == 0.3)
check("sla_risk giảm còn một nửa", abs(adjusted["sla_risk"] - 0.15) < 1e-9)
check("tổng trọng số vẫn = 1", abs(sum(adjusted.values()) - 1.0) < 1e-9)

# customer_tolerant=False -> không đổi gì, TRẢ VỀ ĐÚNG object weights gốc (giữ tương thích ngược)
unchanged = _apply_customer_tolerance(weights, customer_tolerant=False)
check("customer_tolerant=False không đổi weights", unchanged == weights)

# ---- Ảnh hưởng thật lên ranking: option rẻ nhưng rủi ro SLA cao hơn 1 chút có thể thắng khi khách đã thông cảm ----
cheap_slightly_riskier = opt(50_000, 30, 0.4)
expensive_safer = opt(200_000, 30, 0.1)
options = [cheap_slightly_riskier, expensive_safer]

scores_normal = calculate_scores(options, weights, customer_tolerant=False)
scores_tolerant = calculate_scores(options, weights, customer_tolerant=True)
check(
    "customer_tolerant=True làm option rẻ được lợi tương đối so với bình thường",
    (scores_tolerant[0] - scores_tolerant[1]) > (scores_normal[0] - scores_normal[1]),
)

# ---- rank_options end-to-end với customer_tolerant, không lỗi, gán rank đủ ----
ranked = rank_options(None, [cheap_slightly_riskier, expensive_safer], weights, customer_tolerant=True)
check("rank_options gán rank 1..2 đủ", sorted(o.rank for o in ranked) == [1, 2])

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
