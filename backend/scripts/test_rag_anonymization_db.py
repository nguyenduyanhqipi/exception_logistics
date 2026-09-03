"""Test core/rag_anonymization.py::resolve_area_bucket + check_k_anonymity_count
— cần DB thật (đọc/ghi rag_case_bank). Tự dọn dữ liệu test ở đầu/cuối."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete

from database import SessionLocal
from core.rag_anonymization import K_ANONYMITY_THRESHOLD, CITY_LEVEL_FALLBACK, check_k_anonymity_count, resolve_area_bucket
from models import RagCaseBank

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


TEST_GROUP = "__test_k_anon__"
TEST_SUB_TYPE = "__test_sub__"
TEST_AREA = "__TestDistrict__"

db = SessionLocal()
try:
    # Dọn sạch trước (phòng lần chạy trước bị gián đoạn để lại rác)
    db.execute(
        delete(RagCaseBank).where(RagCaseBank.exception_group == TEST_GROUP)
    )
    db.commit()

    # ---- Chưa có case nào cùng tổ hợp -> count = 0, generalize lên city-level ----
    check("count=0 khi chưa có case nào", check_k_anonymity_count(db, TEST_GROUP, TEST_SUB_TYPE, TEST_AREA, "ca_sang") == 0)
    resolved = resolve_area_bucket(db, TEST_GROUP, TEST_SUB_TYPE, TEST_AREA, "ca_sang")
    check(f"generalize lên '{CITY_LEVEL_FALLBACK}' khi dưới ngưỡng k-anonymity", resolved == CITY_LEVEL_FALLBACK)

    # ---- Thêm đủ K_ANONYMITY_THRESHOLD case cùng tổ hợp -> không generalize nữa, giữ nguyên area gốc ----
    for i in range(K_ANONYMITY_THRESHOLD):
        db.add(
            RagCaseBank(
                exception_group=TEST_GROUP, sub_type=TEST_SUB_TYPE, area_bucket=TEST_AREA, shift_label="ca_sang",
            )
        )
    db.commit()

    check(
        f"count={K_ANONYMITY_THRESHOLD} sau khi thêm đủ case",
        check_k_anonymity_count(db, TEST_GROUP, TEST_SUB_TYPE, TEST_AREA, "ca_sang") == K_ANONYMITY_THRESHOLD,
    )
    resolved_after = resolve_area_bucket(db, TEST_GROUP, TEST_SUB_TYPE, TEST_AREA, "ca_sang")
    check("giữ nguyên area gốc khi ĐỦ ngưỡng k-anonymity", resolved_after == TEST_AREA)

    # ---- Tổ hợp shift_label KHÁC không bị ảnh hưởng (đếm đúng theo đủ tổ hợp, không lẫn) ----
    check(
        "tổ hợp shift_label khác không tính chung (vẫn = 0)",
        check_k_anonymity_count(db, TEST_GROUP, TEST_SUB_TYPE, TEST_AREA, "ca_chieu") == 0,
    )

    # ---- area=None (không có thông tin khu vực) -> trả về None, không lỗi ----
    check("area=None -> resolve trả None, không lỗi", resolve_area_bucket(db, TEST_GROUP, TEST_SUB_TYPE, None, "ca_sang") is None)

finally:
    db.execute(delete(RagCaseBank).where(RagCaseBank.exception_group == TEST_GROUP))
    db.commit()
    db.close()

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
