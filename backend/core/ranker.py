"""ranker.py — xếp hạng phương án (mục 7). Thuật toán DUY NHẤT tính điểm,
LLM không tham gia tính điểm (mục 7) — chỉ viết `llm_explanation`.

`normalize()` trong công thức mục 7 là min-max normalize TRONG PHẠM VI các
option đang được so sánh cùng nhau (cùng 1 exception hoặc 1 group) — ranking
là bài toán so sánh tương đối giữa vài phương án cho MỘT tình huống, không
phải so trên toàn hệ thống.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from models import Option


def _min_max_normalize(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    if hi == lo:
        # Mọi option bằng nhau ở tiêu chí này -> không có cơ sở phân biệt,
        # cho điểm giữa để tiêu chí này không lệch ảnh hưởng đến rank.
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def calculate_scores(options: list[Option], weights: dict) -> list[float]:
    """Trả về list điểm số (0-1, cao hơn = tốt hơn), CÙNG THỨ TỰ với `options`."""
    costs = [float(o.cost_estimate or 0) for o in options]
    times = [float(o.time_estimate_minutes or 0) for o in options]
    slas = [float(o.sla_risk_remaining or 0) for o in options]

    cost_scores = _min_max_normalize(costs)
    time_scores = _min_max_normalize(times)
    sla_scores = _min_max_normalize(slas)

    return [
        weights["cost"] * (1 - cost_scores[i])
        + weights["time"] * (1 - time_scores[i])
        + weights["sla_risk"] * (1 - sla_scores[i])
        for i in range(len(options))
    ]


def rank_options(db: Session, options: list[Option], weights: dict) -> list[Option]:
    """Tính điểm + gán `score`/`rank` cho từng option (rank 1 = tốt nhất).
    Không tự commit — caller (job_processor) chịu trách nhiệm."""
    if not options:
        return options

    scores = calculate_scores(options, weights)
    order = sorted(range(len(options)), key=lambda i: scores[i], reverse=True)
    for rank, idx in enumerate(order, start=1):
        options[idx].score = Decimal(str(round(scores[idx], 4)))
        options[idx].rank = rank
    return options
