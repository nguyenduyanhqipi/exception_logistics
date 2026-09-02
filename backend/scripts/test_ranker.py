"""Test ranker.py (BUILD_PLAN.md bước 7.1) — công thức tính điểm mục 7 +
xác nhận đổi ranking_weights làm đổi thứ hạng đúng logic. Không cần DB thật
(dùng Option() object trần, không insert)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ranker import calculate_scores, rank_options
from models import Option

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


# 3 option với cost/time/sla_risk khác biệt rõ rệt, tính tay để đối chiếu.
opt_cheap = Option(description="Rẻ nhất, chậm nhất, rủi ro SLA cao nhất", cost_estimate=100_000, time_estimate_minutes=60, sla_risk_remaining=0.8)
opt_mid = Option(description="Trung bình", cost_estimate=300_000, time_estimate_minutes=30, sla_risk_remaining=0.4)
opt_fast = Option(description="Đắt nhất, nhanh nhất, an toàn SLA nhất", cost_estimate=500_000, time_estimate_minutes=10, sla_risk_remaining=0.1)
options = [opt_cheap, opt_mid, opt_fast]

# ---- Test 1: trọng số mặc định company (cost 0.4, time 0.3, sla_risk 0.3) ----
weights_default = {"cost": 0.4, "time": 0.3, "sla_risk": 0.3}
scores = calculate_scores(options, weights_default)
print("Scores (default weights):", [round(s, 4) for s in scores])

# Tính tay: cost min=100k max=500k -> normalize [0, 0.5, 1] -> (1-x) = [1, 0.5, 0]
# time min=10 max=60 -> normalize [1, 0.4, 0] -> (1-x) = [0, 0.6, 1]
# sla min=0.1 max=0.8 -> normalize [1, 0.4286, 0] -> (1-x) = [0, 0.5714, 1]
expected_cheap = 0.4 * 1 + 0.3 * 0 + 0.3 * 0
expected_mid = 0.4 * 0.5 + 0.3 * 0.6 + 0.3 * (1 - 0.42857)
expected_fast = 0.4 * 0 + 0.3 * 1 + 0.3 * 1
check("Điểm option rẻ nhất khớp tính tay", abs(scores[0] - expected_cheap) < 0.001)
check("Điểm option trung bình khớp tính tay", abs(scores[1] - expected_mid) < 0.001)
check("Điểm option nhanh/an toàn nhất khớp tính tay", abs(scores[2] - expected_fast) < 0.001)

# Với trọng số mặc định (cost cao nhất 0.4), option RẺ NHẤT nên thắng vì cost
# ảnh hưởng nhiều nhất — nhưng thực ra fast có time+sla tuyệt đối (0.3+0.3=0.6
# > 0.4 cost), nên fast phải thắng. Kiểm tra bằng rank_options trực tiếp.
ranked = rank_options(None, list(options), weights_default)
best = next(o for o in ranked if o.rank == 1)
print(f"Rank 1 (default weights): {best.description} (score={best.score})")
check("rank_options gán rank 1..3 đủ", sorted(o.rank for o in ranked) == [1, 2, 3])
check("Option rank 1 có score cao nhất trong 3", best.score == max(o.score for o in ranked))

# ---- Test 2: đổi trọng số ưu tiên tuyệt đối cho cost -> option rẻ nhất phải thắng ----
weights_cost_heavy = {"cost": 0.9, "time": 0.05, "sla_risk": 0.05}
ranked_cost_heavy = rank_options(None, [Option(description=o.description, cost_estimate=o.cost_estimate, time_estimate_minutes=o.time_estimate_minutes, sla_risk_remaining=o.sla_risk_remaining) for o in options], weights_cost_heavy)
best_cost_heavy = next(o for o in ranked_cost_heavy if o.rank == 1)
print(f"Rank 1 (cost-heavy weights): {best_cost_heavy.description}")
check("Đổi trọng số cost=0.9 -> option RẺ NHẤT thắng (đổi ranking_weights đổi đúng thứ hạng)", best_cost_heavy.description == opt_cheap.description)

# ---- Test 3: đổi trọng số ưu tiên tuyệt đối cho time -> option nhanh nhất phải thắng ----
weights_time_heavy = {"cost": 0.05, "time": 0.9, "sla_risk": 0.05}
ranked_time_heavy = rank_options(None, [Option(description=o.description, cost_estimate=o.cost_estimate, time_estimate_minutes=o.time_estimate_minutes, sla_risk_remaining=o.sla_risk_remaining) for o in options], weights_time_heavy)
best_time_heavy = next(o for o in ranked_time_heavy if o.rank == 1)
print(f"Rank 1 (time-heavy weights): {best_time_heavy.description}")
check("Đổi trọng số time=0.9 -> option NHANH NHẤT thắng", best_time_heavy.description == opt_fast.description)

# ---- Test 4: edge case 1 option duy nhất (fallback thủ công) -> không chia 0, rank=1 ----
single = [Option(description="Chỉ 1 phương án", cost_estimate=0, time_estimate_minutes=0, sla_risk_remaining=0.5)]
ranked_single = rank_options(None, single, weights_default)
check("1 option duy nhất -> không lỗi chia 0, rank=1", ranked_single[0].rank == 1 and ranked_single[0].score is not None)

# ---- Test 5: danh sách rỗng -> không lỗi ----
check("Danh sách rỗng -> trả về rỗng, không lỗi", rank_options(None, [], weights_default) == [])

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
