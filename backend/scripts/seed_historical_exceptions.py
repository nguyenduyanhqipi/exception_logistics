"""Seed 25 ngoại lệ lịch sử giả cho báo cáo KPI/trends (BUILD_PLAN.md bước
10.2 — "Phần 4 (fake seed data lịch sử)" hoãn từ TECHNICAL_SPEC.md, làm ở
đây vì hệ thống đã chạy thật, biết rõ format cần seed).

Đây là dữ liệu LỊCH SỬ đã xử lý xong (không phải kịch bản demo sống động —
xem `seed_demo_data.py`), chỉ để `ManagerDashboard.tsx` (Giai đoạn 9) có số
liệu phong phú thay vì trống rỗng. KHÔNG đi qua rule_engine/LLM thật — set
thẳng timestamp quá khứ + option/outcome giả lập hợp lý, vì mục đích là làm
đẹp báo cáo, không phải test lại pipeline (đã test kỹ ở Giai đoạn 4-7).

Chạy: python scripts/seed_historical_exceptions.py
"""
import random
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from models import Decision, Exception_, Option, Outcome, Schedule, User

COMPANY_ID = "00000000-0000-0000-0000-000000000001"
VEHICLE_IDS = ["B01", "B02", "B03", "B04", "B05", "C01", "C02", "C03", "C04", "C05"]

SUB_TYPES = [
    ("delay", "late_departure", "warning"),
    ("delay", "late_departure", "serious"),
    ("delay", "slow_loading", "warning"),
    ("delay", "unknown_delay", "warning"),
    ("road_block", "traffic_jam", "warning"),
    ("road_block", "road_closed", "serious"),
    ("customer_reject", "customer_absent", "warning"),
    ("customer_reject", "customer_dispute", "serious"),
    ("customer_reject", "wrong_address", "warning"),
    ("customer_change", "change_time", "warning"),
    ("customer_change", "cancel_order", "warning"),
    ("vehicle_issue", "minor_breakdown", "warning"),
    ("vehicle_issue", "major_breakdown", "serious"),
    ("vehicle_issue", "accident", "critical"),
]

AREAS = ["Cầu Giấy", "Đống Đa", "Hai Bà Trưng", "Hoàn Kiếm", "Hoàng Mai", "Long Biên", "Nam Từ Liêm", "Tây Hồ", "Thanh Xuân", "Ba Đình"]

random.seed(42)  # kết quả tái lập được giữa các lần chạy


def main():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.company_id == COMPANY_ID, User.role == "dispatcher").first()
        if user is None:
            print("Chưa có dispatcher demo — chạy scripts/seed_demo_users.py trước.")
            return

        existing_count = db.query(Exception_).filter(Exception_.description == "[SEED_HISTORICAL]").count()
        if existing_count > 0:
            print(f"Đã có {existing_count} ngoại lệ lịch sử giả — bỏ qua (xoá thủ công nếu muốn seed lại).")
            return

        created = 0
        for i in range(25):
            days_ago = random.randint(1, 25)
            reported_at = datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            vehicle_id = random.choice(VEHICLE_IDS)
            exception_group, sub_type, severity = random.choice(SUB_TYPES)
            area = random.choice(AREAS)

            schedule = Schedule(
                company_id=COMPANY_ID,
                vehicle_id=vehicle_id,
                shift_date=reported_at.date(),
                trip_sequence=100 + i,  # dải số riêng, không đụng chuyến demo/thật
                stops=[],
                created_at=reported_at,
            )
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
                description="[SEED_HISTORICAL]",
                status="resolved",
                reported_by=user.user_id,
                reported_at=reported_at,
            )
            db.add(exc)
            db.flush()

            cost_estimate = random.randint(0, 20) * 25_000
            time_estimate = random.randint(0, 12) * 10
            sla_risk = round(random.uniform(0, 1), 2)
            option = Option(
                exception_id=exc.exception_id,
                description=f"[Lịch sử] Phương án xử lý {sub_type}",
                cost_estimate=cost_estimate,
                time_estimate_minutes=time_estimate,
                sla_risk_remaining=sla_risk,
                rank=1,
                score=round(random.uniform(0.5, 0.95), 4),
                created_at=reported_at,
            )
            db.add(option)
            db.flush()

            confirmed_at = reported_at + timedelta(minutes=random.randint(5, 60))
            decision = Decision(
                company_id=COMPANY_ID,
                exception_id=exc.exception_id,
                selected_option_id=option.option_id,
                confirmed_by=user.user_id,
                confirmed_at=confirmed_at,
            )
            db.add(decision)
            db.flush()

            # ~85% có outcome (một số vẫn "chưa ai nhập kết quả" cho thực tế)
            if random.random() < 0.85:
                delivered_on_time = random.random() < (0.85 if severity == "warning" else 0.6 if severity == "serious" else 0.3)
                actual_cost = max(0, cost_estimate + random.randint(-30_000, 50_000))
                recorded_at = confirmed_at + timedelta(hours=random.randint(1, 48))
                db.add(
                    Outcome(
                        decision_id=decision.decision_id,
                        delivered_on_time=delivered_on_time,
                        actual_cost=actual_cost,
                        notes="[SEED_HISTORICAL]",
                        recorded_by=user.user_id,
                        recorded_at=recorded_at,
                    )
                )
            created += 1

        db.commit()
        print(f"Đã seed {created} ngoại lệ lịch sử giả (kèm schedule/option/decision/outcome tương ứng).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
