"""Seed dữ liệu lịch sử giả cho trang Báo cáo (đợt code thứ 6, Việc 4 —
Claude outputs/dot_code_6/DOT_CODE_6_KICKOFF.md).

VIẾT LẠI HOÀN TOÀN bản gốc (25 ngoại lệ / 25 ngày) vì bản đó quá mỏng cho các
tab Quý/Năm + chế độ so sánh 2 kỳ của trang Báo cáo mới (đợt code 5, Pha 5), và
thiếu 2 field mới (`options.prompt_version_id`/`llm_explanation`,
`outcomes.resolution_type`) khiến số liệu AI/outcome sai lệch (xem lý do chi
tiết trong DOT_CODE_6_KICKOFF.md, Việc 4).

Đây vẫn là dữ liệu LỊCH SỬ đã xử lý xong (không phải kịch bản demo sống động —
xem `seed_demo_data.py`), dùng timestamp TUYỆT ĐỐI trong quá khứ nên KHÔNG cần
chạy lại sát giờ demo như `seed_demo_data.py`. KHÔNG đi qua rule_engine/LLM
thật — set thẳng option/outcome giả lập hợp lý, vì mục đích là làm đẹp báo
cáo, không phải test lại pipeline (đã test kỹ ở Giai đoạn 4-7 / đợt code 5).

LƯU Ý khi chạy ĐÚNG NGÀY TRÌNH BÀY: cửa sổ cuối cùng chạy tới hết HÔM NAY (để
tab "Ngày" của trang Báo cáo không trống), nên script ghi vài dòng
`llm_usage_logs` mang timestamp hôm nay — chúng ĐƯỢC TÍNH vào hạn mức 100 lượt
gọi LLM/ngày (core/llm_usage.py::count_calls_today). Thực tế chỉ ~8-15 lượt trên
tổng 100 nên không cản trở buổi demo, nhưng đừng chạy đi chạy lại script này
nhiều lần trong ngày trình bày.

Chạy: python scripts/seed_historical_exceptions.py
"""
import random
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from core.llm_adapter import MODEL_NAME
# Tái dùng ĐÚNG hàm tra prompt active mà pipeline thật dùng (option_generator.py)
# thay vì tự viết lại truy vấn PromptVersion — tránh 2 nơi có thể lệch nhau.
# Import KHÔNG kích hoạt gọi mạng/API key nào (generate() mới cần key, load lười).
from core.option_generator import MAX_LLM_RETRIES, _get_active_prompt
from core.llm_usage import estimate_cost_usd
from database import SessionLocal
from models import Decision, Exception_, LLMUsageLog, Option, Outcome, Schedule, User

MARKER = "[SEED_HISTORICAL]"
COMPANY_ID = "00000000-0000-0000-0000-000000000001"
VEHICLE_IDS = ["B01", "B02", "B03", "B04", "B05", "C01", "C02", "C03", "C04", "C05"]
AREAS = ["Cầu Giấy", "Đống Đa", "Hai Bà Trưng", "Hoàn Kiếm", "Hoàng Mai", "Long Biên", "Nam Từ Liêm", "Tây Hồ", "Thanh Xuân", "Ba Đình"]

MONTHS_BACK = 24  # ~2 năm, chốt mốc cuối 2026-09-10 (xem kickoff)
EXCEPTIONS_PER_MONTH = (28, 40)  # random.randint mỗi tháng — đủ dày cho tab Tuần, KHÔNG tháng nào trống
OUTCOME_RATE = 0.85  # ~85% có outcome, ~15% "chưa ai nhập kết quả" — giữ nguyên tỷ lệ bản gốc
AI_FAIL_RATE = 0.07  # ~7% AI "sinh phương án thất bại" (timeout/lỗi thật) — nằm trong khoảng 5-10% kickoff yêu cầu

# Sai số chi phí THỰC TẾ so với ước tính của AI, dạng TỶ LỆ chứ không phải một
# khoảng tiền tuyệt đối. Bản nháp đầu dùng `cost_estimate + randint(-30k, +50k)`
# — với ngoại lệ rẻ (change_time ước tính 5.000đ) thì lệch 50.000đ là sai số
# 1000%, kéo `cost_accuracy_rate` của api/reports.py::_outcome_metrics
# (= 1 - trung bình |lệch %|, kẹp sàn ở 0) tụt thẳng về 0% — đúng cái KPI mà
# kickoff yêu cầu "không được ra 0% hay 100%". Lệch theo tỷ lệ giữ sai số hợp lý
# ở mọi bậc chi phí, ra độ chính xác ~88%.
COST_DEVIATION = (-0.12, 0.18)  # thiên về vượt dự toán một chút cho giống đời thật

# schedule.trip_sequence: dùng 1 bộ đếm TOÀN CỤC tăng dần, KHÔNG theo từng xe/ngày
# — mỗi ngoại lệ lịch sử có 1 schedule riêng, bộ đếm toàn cục làm
# (company_id, vehicle_id, shift_date, trip_sequence) luôn khác nhau dù trùng
# xe/ngày (unique index ở models/schedule.py), không cần biết trước xe nào rơi
# vào ngày nào. Bắt đầu từ 9000 để không đụng dải trip_sequence của
# seed_demo_data.py (1, 2, 3...) hay bản seed lịch sử CŨ (100-124, đã bị xoá).
TRIP_SEQUENCE_START = 9000

# (group, tỷ trọng tương đối, {warning,serious,critical} tỷ trọng độ nghiêm
# trọng, khoảng chi phí VNĐ, khoảng thời gian phút, khoảng rủi ro SLA còn lại).
# Tỷ trọng phản ánh trực giác đời thật: delay/road_block (tắc đường, xuất phát
# trễ) xảy ra thường xuyên hơn hẳn vehicle_issue (sự cố xe/tai nạn, hiếm hơn) —
# tổng tỷ trọng = 100, KHÔNG cần chia đều tuyệt đối như bản gốc.
SUB_TYPE_PROFILE = {
    "late_departure": ("delay", 25, (0.60, 0.35, 0.05), (50_000, 300_000), (15, 60), (0.10, 0.55)),
    "unknown_delay": ("delay", 6, (0.20, 0.45, 0.35), (100_000, 400_000), (30, 90), (0.20, 0.70)),
    "traffic_jam": ("road_block", 22, (0.55, 0.35, 0.10), (50_000, 250_000), (15, 60), (0.10, 0.50)),
    "road_closed": ("road_block", 5, (0.15, 0.45, 0.40), (150_000, 500_000), (20, 90), (0.20, 0.75)),
    "customer_absent": ("customer_reject", 10, (0.50, 0.35, 0.15), (100_000, 400_000), (15, 45), (0.10, 0.55)),
    "customer_dispute": ("customer_reject", 4, (0.30, 0.45, 0.25), (100_000, 450_000), (20, 60), (0.15, 0.60)),
    "change_time": ("customer_change", 8, (0.70, 0.28, 0.02), (0, 150_000), (5, 30), (0.05, 0.35)),
    "change_location": ("customer_change", 6, (0.70, 0.28, 0.02), (50_000, 300_000), (15, 60), (0.10, 0.45)),
    "minor_breakdown": ("vehicle_issue", 8, (0.75, 0.23, 0.02), (100_000, 350_000), (20, 60), (0.10, 0.45)),
    "major_breakdown": ("vehicle_issue", 3, (0.05, 0.35, 0.60), (300_000, 1_200_000), (60, 180), (0.30, 0.85)),
    "accident": ("vehicle_issue", 3, (0.05, 0.25, 0.70), (300_000, 1_500_000), (60, 240), (0.35, 0.90)),
}
SUB_TYPES = list(SUB_TYPE_PROFILE)
SUB_TYPE_WEIGHTS = [SUB_TYPE_PROFILE[st][1] for st in SUB_TYPES]

# outcomes.resolution_type — Kiểu 2 (customer_absent/customer_dispute), đa số
# "giao lại thành công" như thiết kế yêu cầu (xem schemas/decision.py::RESOLUTION_TYPES).
RESOLUTION_TYPES = ["redelivered", "returned_to_depot", "cancelled", "other"]
RESOLUTION_WEIGHTS = [55, 20, 15, 10]
REJECTION_SUB_TYPES = ("customer_absent", "customer_dispute")

AI_FAIL_ERRORS = [
    "Timeout sau 90s không có phản hồi",
    "Vượt hạn mức 100 lượt gọi LLM/ngày",
    "Gemini API trả lỗi 503 (quá tải tạm thời)",
    "Phân tích JSON phản hồi LLM thất bại",
    "Gemini API trả lỗi 429 (RESOURCE_EXHAUSTED)",
]

LLM_EXPLANATION_TEMPLATES = [
    "Tối ưu chi phí phát sinh ở mức thấp nhất, đánh đổi bằng thời gian xử lý lâu hơn các phương án còn lại.",
    "Ưu tiên xử lý nhanh để giảm rủi ro vi phạm SLA, chấp nhận chi phí phát sinh cao hơn.",
    "Cân bằng giữa chi phí và thời gian, phù hợp khi rủi ro SLA còn lại ở mức trung bình.",
    "Giảm thiểu rủi ro vi phạm SLA xuống mức thấp nhất có thể, dù chi phí không phải thấp nhất.",
    "Phương án khả thi với nguồn lực hiện có (xe/tài xế gần nhất), thời gian xử lý ở mức chấp nhận được.",
    "Chi phí và thời gian đều ở mức trung bình so với các phương án khác — lựa chọn an toàn khi chưa rõ diễn biến tiếp theo.",
]

random.seed(42)  # kết quả tái lập được giữa các lần chạy


def _weighted_severity(weights):
    w, s, c = weights
    return random.choices(["warning", "serious", "critical"], weights=[w, s, c], k=1)[0]


def _month_windows(anchor: date, months_back: int):
    """(năm, tháng, ngày_bắt_đầu, ngày_kết_thúc) cho từng tháng trong cửa sổ
    `months_back` tháng gần nhất, cũ -> mới. Tháng hiện tại (chứa `anchor`) bị
    CẮT tới đúng `anchor`, tức CÓ CẢ HÔM NAY: tab "Ngày" của trang Báo cáo mặc
    định neo vào hôm nay, dừng ở hôm qua là mở tab đó ra trống trơn.

    Chuyến lịch sử được xoá mềm ngay lúc tạo (xem chỗ dựng `Schedule`) nên
    chuyến "hôm nay" của dữ liệu giả KHÔNG lọt vào dropdown chọn chuyến của
    NewException.tsx — `/api/schedules` lọc `deleted_at IS NULL`."""
    windows = []
    y, m = anchor.year, anchor.month
    for i in range(months_back - 1, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        start = date(yy, mm, 1)
        end = date(yy, mm, monthrange(yy, mm)[1])
        if (yy, mm) == (y, m):
            end = anchor
        windows.append((start, end))
    return windows


def _random_datetime_in(start: date, end: date, now: datetime) -> datetime:
    """Mốc thời gian ngẫu nhiên trong [start, end], KHÔNG BAO GIỜ ở tương lai.

    Cần cắt trần vì cửa sổ cuối cùng chạy tới hết hôm nay: một ngoại lệ "báo
    lúc 20h" sinh ra lúc 14h là dữ liệu của tương lai, nhìn vào trang Lịch sử
    lúc trình bày là thấy ngay."""
    day_offset = random.randint(0, (end - start).days)
    d = start + timedelta(days=day_offset)
    # Giờ hoạt động thiên về ban ngày (6h-22h) cho giống vận hành thật, vẫn có
    # đuôi nhỏ ngoài giờ (mất liên lạc/tai nạn có thể xảy ra bất kỳ lúc nào).
    hour = random.choices(range(24), weights=[1] * 6 + [6] * 16 + [1] * 2, k=1)[0]
    at = datetime(d.year, d.month, d.day, hour, random.randint(0, 59), random.randint(0, 59))
    return min(at, now)


def purge_existing(db) -> int:
    """Xoá sạch dữ liệu seed lịch sử CŨ (đúng thứ tự FK: outcome -> decision ->
    option -> exception -> schedule), không chỉ skip như bản gốc."""
    exception_ids = [
        row[0] for row in db.execute(
            select(Exception_.exception_id).where(Exception_.description == MARKER)
        ).all()
    ]
    if not exception_ids:
        return 0

    schedule_ids = [
        row[0] for row in db.execute(
            select(Exception_.schedule_id).where(Exception_.exception_id.in_(exception_ids))
        ).all()
    ]
    decision_ids = [
        row[0] for row in db.execute(
            select(Decision.decision_id).where(Decision.exception_id.in_(exception_ids))
        ).all()
    ]

    db.query(LLMUsageLog).filter(LLMUsageLog.exception_id.in_(exception_ids)).delete(synchronize_session=False)
    db.query(Outcome).filter(Outcome.decision_id.in_(decision_ids)).delete(synchronize_session=False)
    db.query(Decision).filter(Decision.exception_id.in_(exception_ids)).delete(synchronize_session=False)
    db.query(Option).filter(Option.exception_id.in_(exception_ids)).delete(synchronize_session=False)
    db.query(Exception_).filter(Exception_.exception_id.in_(exception_ids)).delete(synchronize_session=False)
    # CHỈ xoá chuyến đã hết ngoại lệ trỏ vào. Một chuyến lịch sử vẫn có thể
    # đang cõng ngoại lệ KHÁC không mang marker (gặp thật trên DB dev: 1 chuyến
    # seed cũ có thêm 3 ngoại lệ do người test tạo tay) — xoá thẳng theo
    # `schedule_ids` là vỡ khoá ngoại `exceptions_schedule_id_fkey` và cả lần
    # seed lại hỏng theo.
    if schedule_ids:
        still_used = select(Exception_.schedule_id).where(Exception_.schedule_id.in_(schedule_ids))
        db.query(Schedule).filter(
            Schedule.schedule_id.in_(schedule_ids), ~Schedule.schedule_id.in_(still_used)
        ).delete(synchronize_session=False)
    db.commit()
    return len(exception_ids)


def _make_option(exception_id, sub_type, profile, *, prompt_version_id, llm_explanation, rank, created_at):
    _, _, _, cost_range, time_range, sla_range = profile
    return Option(
        exception_id=exception_id,
        description=f"[Lịch sử] Phương án xử lý {sub_type}"
        + (f" (phương án {rank})" if rank > 1 else ""),
        cost_estimate=random.randint(cost_range[0] // 5_000, cost_range[1] // 5_000) * 5_000,
        time_estimate_minutes=random.randint(*time_range),
        sla_risk_remaining=round(random.uniform(*sla_range), 2),
        score=round(random.uniform(0.35, 0.95), 4),
        rank=rank,
        prompt_version_id=prompt_version_id,
        llm_explanation=llm_explanation,
        created_at=created_at,
    )


def main():
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.company_id == COMPANY_ID).all()
        if not users:
            print("Chưa có user demo — chạy scripts/seed_demo_users.py trước.")
            return

        removed = purge_existing(db)
        if removed:
            print(f"Đã xoá {removed} ngoại lệ lịch sử giả cũ (kèm schedule/option/decision/outcome liên quan).")

        # Tra sẵn prompt active cho từng sub_type — ĐÚNG cách pipeline thật làm
        # (core/option_generator.py::_get_active_prompt), fail sớm và rõ ràng
        # nếu thiếu prompt thay vì âm thầm ghi NULL.
        prompt_version_by_sub_type = {}
        for sub_type in SUB_TYPES:
            _, version_id = _get_active_prompt(db, sub_type)
            prompt_version_by_sub_type[sub_type] = version_id

        trip_seq = TRIP_SEQUENCE_START
        created = 0
        ai_failed_count = 0
        outcome_count = 0
        now = datetime.now()
        today = now.date()

        for month_start, month_end in _month_windows(today, MONTHS_BACK):
            month_target = random.randint(*EXCEPTIONS_PER_MONTH)
            for _ in range(month_target):
                reported_at = _random_datetime_in(month_start, month_end, now)
                vehicle_id = random.choice(VEHICLE_IDS)
                sub_type = random.choices(SUB_TYPES, weights=SUB_TYPE_WEIGHTS, k=1)[0]
                exception_group, _, severity_weights, *_ = SUB_TYPE_PROFILE[sub_type]
                severity = _weighted_severity(severity_weights)
                area = random.choice(AREAS)
                reporter = random.choice(users)

                # `deleted_at` ĐƯỢC SET NGAY (xoá mềm): `/api/dashboard/today`
                # trả về MỌI chuyến chưa xoá, không chỉ chuyến hôm nay
                # (api/dashboard.py, đổi 2026-09-05) và Dashboard.tsx render
                # hết `v.trips` khi mở rộng 1 xe — để nguyên thì mỗi xe demo
                # cõng thêm ~80 chuyến rỗng "0 đơn" của 24 tháng lịch sử, mở
                # bảng ra là một bức tường. Đây cũng chính là trạng thái THẬT
                # sau khi dispatcher dọn chuyến cũ: xoá chuyến chỉ cascade
                # ngoại lệ CHƯA xong (api/exceptions.py::
                # cascade_delete_exceptions_of_schedules), ngoại lệ đã có kết
                # quả vẫn ở lại nguyên vẹn cho báo cáo — nên "chuyến đã xoá +
                # ngoại lệ resolved" không phải trạng thái bịa.
                schedule = Schedule(
                    company_id=COMPANY_ID,
                    vehicle_id=vehicle_id,
                    shift_date=reported_at.date(),
                    trip_sequence=trip_seq,
                    stops=[],
                    created_at=reported_at,
                    deleted_at=min(reported_at + timedelta(days=1), now),
                )
                trip_seq += 1
                db.add(schedule)
                db.flush()

                exc = Exception_(
                    company_id=COMPANY_ID,
                    schedule_id=schedule.schedule_id,
                    exception_group=exception_group,
                    sub_type=sub_type,
                    severity=severity,
                    vehicle_id=vehicle_id,
                    area=area,
                    description=MARKER,
                    # LUÔN "resolved", kể cả 15% case không có outcome (giữ
                    # đúng hành vi bản gốc). KHÔNG dùng "awaiting_outcome" cho
                    # nhóm đó dù nghe có vẻ đúng nghĩa hơn: đó là 1 trong 4
                    # OPEN_STATUSES (api/dashboard.py) nên ~120 ngoại lệ lịch
                    # sử sẽ nhảy hết lên khối "ngoại lệ chưa hoàn thành" ở đầu
                    # Dashboard và vào ô đếm "N ngoại lệ đang mở" — chôn vùi
                    # ngoại lệ THẬT mà dispatcher tạo lúc trình bày.
                    status="resolved",
                    reported_by=reporter.user_id,
                    reported_at=reported_at,
                )
                db.add(exc)
                db.flush()

                ai_failed = random.random() < AI_FAIL_RATE
                prompt_version_id = prompt_version_by_sub_type[sub_type]
                profile = SUB_TYPE_PROFILE[sub_type]

                # 1 lần phân tích THÀNH CÔNG = 1 dòng log; 1 lần THẤT BẠI =
                # MAX_LLM_RETRIES dòng lỗi (core/option_generator.py retry đủ
                # số lần rồi mới bỏ cuộc). Ghi đúng như vậy để "tỷ lệ gọi API
                # thành công" ở bảng Chi phí AI luôn THẤP HƠN "tỷ lệ sinh
                # phương án thành công" — đúng quan hệ mà api/reports.py::
                # get_llm_usage đã ghi rõ trong chú thích, seed 1 dòng/lần thì
                # 2 chỉ số bằng nhau y hệt, nhìn là biết dữ liệu bịa.
                error_message = random.choice(AI_FAIL_ERRORS) if ai_failed else None
                for attempt in range(MAX_LLM_RETRIES if ai_failed else 1):
                    tokens_in = random.randint(600, 1500)
                    tokens_out = random.randint(0, 80) if ai_failed else random.randint(150, 500)
                    db.add(
                        LLMUsageLog(
                            company_id=COMPANY_ID,
                            exception_id=exc.exception_id,
                            model=MODEL_NAME,
                            tokens_in=tokens_in,
                            tokens_out=tokens_out,
                            # Dùng đúng hàm ước giá của pipeline thật thay vì
                            # để NULL — bảng "Chi phí AI" cộng cột này, bỏ
                            # trống là mọi ngày đều hiện 0 USD.
                            cost_usd=estimate_cost_usd(tokens_in, tokens_out),
                            latency_ms=random.randint(3000, 90_000) if ai_failed else random.randint(800, 4000),
                            prompt_version_id=prompt_version_id,
                            success=not ai_failed,
                            error=error_message,
                            created_at=reported_at + timedelta(seconds=random.randint(2, 30) + attempt * 30),
                        )
                    )

                if ai_failed:
                    ai_failed_count += 1
                    # AI không sinh được phương án -> dispatcher tự nhập tay 1
                    # phương án thủ công. Khớp ĐÚNG shape của
                    # api/exceptions.py::create_manual_option thật: chỉ có
                    # description/cost_estimate/time_estimate_minutes — KHÔNG
                    # sla_risk_remaining/score/rank/prompt_version_id/
                    # llm_explanation (những field đó None/absent ở option
                    # thật do dispatcher tự nhập, không phải AI sinh).
                    cost_range, time_range = profile[3], profile[4]
                    option = Option(
                        exception_id=exc.exception_id,
                        description=f"[Lịch sử] Phương án thủ công — AI không sinh được phương án ({sub_type})",
                        cost_estimate=random.randint(cost_range[0] // 5_000, cost_range[1] // 5_000) * 5_000,
                        time_estimate_minutes=random.randint(*time_range),
                        created_at=reported_at + timedelta(minutes=random.randint(3, 20)),
                    )
                    db.add(option)
                    db.flush()
                    selected_option = option
                else:
                    n_options = random.choice([2, 2, 3])  # đa số 2, thỉnh thoảng 3
                    options = [
                        _make_option(
                            exc.exception_id, sub_type, profile,
                            prompt_version_id=prompt_version_id,
                            llm_explanation=random.choice(LLM_EXPLANATION_TEMPLATES),
                            rank=i + 1,
                            created_at=reported_at + timedelta(seconds=random.randint(30, 90)),
                        )
                        for i in range(n_options)
                    ]
                    # rank theo score giảm dần, giống pipeline thật (ranker.py)
                    options.sort(key=lambda o: o.score, reverse=True)
                    for i, opt in enumerate(options, start=1):
                        opt.rank = i
                        db.add(opt)
                    db.flush()
                    # 80% dispatcher chọn đúng phương án hạng 1 (điểm cao nhất AI đề xuất)
                    selected_option = options[0] if random.random() < 0.8 else random.choice(options)

                # `min(..., now)` ở cả 2 mốc dưới: ngoại lệ báo lúc gần nửa
                # đêm hôm nay mà chốt phương án/nhập kết quả sau đó thì rơi vào
                # tương lai. Kẹp lại vẫn giữ đúng thứ tự báo -> chốt -> kết quả.
                confirmed_at = min(reported_at + timedelta(minutes=random.randint(5, 90)), now)
                decision = Decision(
                    company_id=COMPANY_ID,
                    exception_id=exc.exception_id,
                    selected_option_id=selected_option.option_id,
                    confirmed_by=random.choice(users).user_id,
                    confirmed_at=confirmed_at,
                )
                db.add(decision)
                db.flush()

                has_outcome = random.random() < OUTCOME_RATE
                if has_outcome:
                    outcome_count += 1
                    recorded_at = min(confirmed_at + timedelta(hours=random.randint(1, 48)), now)
                    recorder = random.choice(users).user_id
                    cost_estimate = float(selected_option.cost_estimate or 0)
                    # Lệch theo TỶ LỆ, không phải theo số tiền tuyệt đối — xem
                    # COST_DEVIATION ở đầu file để biết vì sao.
                    actual_cost = round(max(0.0, cost_estimate * (1 + random.uniform(*COST_DEVIATION))), -3)

                    if sub_type in REJECTION_SUB_TYPES:
                        # Kiểu 2 (schemas/decision.py::_validate_outcome_fields):
                        # resolution_type có giá trị -> delivered_on_time BẮT BUỘC
                        # None (không suy ra hộ dispatcher); delay_minutes chỉ
                        # được phép khi "giao lại thành công", và là TUỲ CHỌN.
                        resolution_type = random.choices(RESOLUTION_TYPES, weights=RESOLUTION_WEIGHTS, k=1)[0]
                        delay_minutes = None
                        if resolution_type == "redelivered" and random.random() < 0.7:
                            delay_minutes = random.randint(10, 180)
                        db.add(
                            Outcome(
                                decision_id=decision.decision_id,
                                delivered_on_time=None,
                                delay_minutes=delay_minutes,
                                actual_cost=actual_cost,
                                resolution_type=resolution_type,
                                notes=MARKER,
                                recorded_by=recorder,
                                recorded_at=recorded_at,
                            )
                        )
                    else:
                        # Kiểu 1 (9/11 sub_type): delivered_on_time bắt buộc;
                        # delay_minutes bắt buộc > 0 khi trễ, PHẢI None khi đúng giờ.
                        on_time_chance = {"warning": 0.85, "serious": 0.6, "critical": 0.3}[severity]
                        delivered_on_time = random.random() < on_time_chance
                        delay_minutes = random.randint(10, 240) if not delivered_on_time else None
                        db.add(
                            Outcome(
                                decision_id=decision.decision_id,
                                delivered_on_time=delivered_on_time,
                                delay_minutes=delay_minutes,
                                actual_cost=actual_cost,
                                resolution_type=None,
                                notes=MARKER,
                                recorded_by=recorder,
                                recorded_at=recorded_at,
                            )
                        )

                created += 1

        db.commit()
        print(
            f"Đã seed {created} ngoại lệ lịch sử giả trải {MONTHS_BACK} tháng "
            f"({outcome_count} có outcome, {ai_failed_count} mô phỏng AI lỗi/không sinh được phương án)."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
