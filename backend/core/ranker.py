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


def _apply_customer_tolerance(weights: dict, customer_tolerant: bool) -> dict:
    """Mục F (2026-09-03): khi khách đã CHỦ ĐỘNG chấp nhận đúng mức trễ tình
    huống này gây ra (`customer_accepted_delay_min` >= trễ ước tính thật —
    xem job_processor.py::_customer_tolerant_of_delay), rủi ro SLA bớt đáng lo
    vì khách đã đồng ý từ trước — dồn nửa trọng số `sla_risk` sang `cost`, ưu
    tiên phương án rẻ hơn thay vì tốn thêm để né 1 rủi ro khách không còn
    quan tâm. Chỉ đổi weights DÙNG TẠM cho lần rank này, không ghi đè
    `company.ranking_weights` gốc. Ranh giới bắt buộc: hàm này KHÔNG được và
    KHÔNG hề đụng tới `impact_analysis`/cờ `sla_breach` thật — số liệu đó nuôi
    KPI thật (on_time_rate ở ManagerDashboard), badge "Vi phạm SLA?" ở
    ExceptionDetail luôn phải đúng thực tế hợp đồng bất kể khách thông cảm
    hay không; chỉ THỨ TỰ ưu tiên phương án bị đổi."""
    if not customer_tolerant:
        return weights
    shifted = weights["sla_risk"] / 2
    return {"cost": weights["cost"] + shifted, "time": weights["time"], "sla_risk": weights["sla_risk"] - shifted}


def calculate_scores(options: list[Option], weights: dict, customer_tolerant: bool = False) -> list[float]:
    """Trả về list điểm số (0-1, cao hơn = tốt hơn), CÙNG THỨ TỰ với `options`."""
    weights = _apply_customer_tolerance(weights, customer_tolerant)
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


def rank_options(db: Session, options: list[Option], weights: dict, customer_tolerant: bool = False) -> list[Option]:
    """Tính điểm + gán `score`/`rank` cho từng option (rank 1 = tốt nhất).
    Không tự commit — caller (job_processor) chịu trách nhiệm."""
    if not options:
        return options

    scores = calculate_scores(options, weights, customer_tolerant=customer_tolerant)
    order = sorted(range(len(options)), key=lambda i: scores[i], reverse=True)
    for rank, idx in enumerate(order, start=1):
        options[idx].score = Decimal(str(round(scores[idx], 4)))
        options[idx].rank = rank
    return options
