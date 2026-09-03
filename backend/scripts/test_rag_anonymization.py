"""Test core/rag_anonymization.py — bucket hoá + redact PII (mục 20.2), phần
THUẦN không cần DB. K-anonymity/resolve_area_bucket cần DB thật, xem
scripts/test_rag_anonymization_db.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.rag_anonymization import bucket_time_to_deadline, bucket_volume_kg, build_case_fields, redact_notes

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


# ---- bucket_time_to_deadline ----
check("None -> None", bucket_time_to_deadline(None) is None)
check("15 phút -> '<30p'", bucket_time_to_deadline(15) == "<30p")
check("29 phút -> '<30p' (biên dưới)", bucket_time_to_deadline(29) == "<30p")
check("30 phút -> '30-90p' (biên trên bao gồm)", bucket_time_to_deadline(30) == "30-90p")
check("90 phút -> '30-90p' (biên trên)", bucket_time_to_deadline(90) == "30-90p")
check("91 phút -> '>90p'", bucket_time_to_deadline(91) == ">90p")
check("số âm (đã trễ hạn) -> '<30p'", bucket_time_to_deadline(-10) == "<30p")

# ---- bucket_volume_kg ----
check("None -> None", bucket_volume_kg(None) is None)
check("20kg -> nhẹ", bucket_volume_kg(20) == "nhẹ(<50kg)")
check("49.9kg -> nhẹ (biên dưới)", bucket_volume_kg(49.9) == "nhẹ(<50kg)")
check("50kg -> vừa (biên)", bucket_volume_kg(50) == "vừa(50-200kg)")
check("200kg -> vừa (biên trên)", bucket_volume_kg(200) == "vừa(50-200kg)")
check("201kg -> nặng", bucket_volume_kg(201) == "nặng(>200kg)")

# ---- redact_notes ----
check("None -> None", redact_notes(None) is None)
check("chuỗi rỗng -> chuỗi rỗng (không lỗi)", redact_notes("") == "")
check(
    "SĐT dạng 0xxxxxxxxx bị redact",
    "[SĐT]" in redact_notes("Gọi khách qua số 0987654321 lúc chiều"),
)
check(
    "SĐT dạng +84xxxxxxxxx bị redact",
    "[SĐT]" in redact_notes("Liên hệ +84987654321"),
)
check(
    "Tên khách xuất hiện y nguyên trong notes bị redact",
    "[TÊN KHÁCH]" in redact_notes("Nguyễn Văn A không có nhà", customer_name="Nguyễn Văn A"),
)
check(
    "Tên tài xế xuất hiện y nguyên trong notes bị redact",
    "[TÊN TÀI XẾ]" in redact_notes("Tài xế Trần Văn B báo xe hỏng", driver_name="Trần Văn B"),
)
check(
    "Địa chỉ xuất hiện y nguyên trong notes bị redact",
    "[ĐỊA CHỈ]" in redact_notes("Không tìm thấy 123 Láng Hạ", address="123 Láng Hạ"),
)
check(
    "Notes không có PII nào thì giữ nguyên nội dung nghiệp vụ",
    redact_notes("Khách đồng ý chờ thêm 30 phút") == "Khách đồng ý chờ thêm 30 phút",
)
check(
    "Redact nhiều loại PII cùng lúc trong 1 câu",
    all(
        marker in redact_notes(
            "Gọi 0987654321 cho Nguyễn Văn A ở 123 Láng Hạ nhưng không nghe máy",
            customer_name="Nguyễn Văn A", address="123 Láng Hạ",
        )
        for marker in ("[SĐT]", "[TÊN KHÁCH]", "[ĐỊA CHỈ]")
    ),
)

# ---- build_case_fields: không raise, map đúng field, KHÔNG có field nào chứa dữ liệu thô nhạy cảm ----
fields = build_case_fields(
    exception_group="road_block", sub_type="traffic_jam", severity="critical",
    area_bucket="Cầu Giấy", shift_label="ca_sang", time_to_deadline_min=20,
    downstream_stops_affected=2, has_priority_order=True, cargo_type="normal",
    volume_kg=80, notes="Gọi 0987654321 cho Nguyễn Văn A",
    customer_name="Nguyễn Văn A", driver_name=None, address=None,
    option_cost_estimate=50000, option_time_estimate_minutes=15, option_sla_risk_remaining=0.15,
    outcome_delivered_on_time=True, outcome_cost_variance_pct=0.05,
)
check("time_to_deadline_bucket bucket đúng từ phút thật", fields["time_to_deadline_bucket"] == "<30p")
check("volume_kg_bucket bucket đúng từ kg thật", fields["volume_kg_bucket"] == "vừa(50-200kg)")
check("notes_redacted không còn SĐT thật", "0987654321" not in fields["notes_redacted"])
check("notes_redacted không còn tên khách thật", "Nguyễn Văn A" not in fields["notes_redacted"])
check("KHÔNG có key 'volume_kg'/'time_to_deadline_min' thô trong dict trả về (chỉ có bản đã bucket)", "volume_kg" not in fields and "time_to_deadline_min" not in fields)
check("area_bucket giữ nguyên (caller đã resolve trước khi gọi)", fields["area_bucket"] == "Cầu Giấy")

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
