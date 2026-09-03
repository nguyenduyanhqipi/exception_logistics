"""Test core/rag_anonymization.py::admit_from_decision/run_pending_admissions
end-to-end với dữ liệu THẬT đã seed sẵn (decisions/outcomes/exceptions) —
cần DB thật. Tự khôi phục company.rag_data_sharing_consent + outcome.
admitted_to_rag_at về trạng thái ban đầu sau khi test xong."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select

from database import SessionLocal
from core.rag_anonymization import admit_from_decision, find_admission_candidates, run_pending_admissions
from core.rag_trace import combine_key, decrypt_value
from models import Company, Decision, Outcome, RagCaseBank, RagCaseSourceMap

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


k1, k2 = os.urandom(32), os.urandom(32)
key = combine_key(k1, k2)

db = SessionLocal()
try:
    outcome = db.execute(
        select(Outcome).join(Decision, Decision.decision_id == Outcome.decision_id).where(Decision.exception_id.is_not(None))
    ).scalars().first()
    if outcome is None:
        print("Bỏ qua — không có outcome nào gắn với decision đơn lẻ (không phải combined-mode) trong DB local.")
    else:
        decision = db.get(Decision, outcome.decision_id)
        company = db.get(Company, decision.company_id)
        original_consent = company.rag_data_sharing_consent
        original_admitted_at = outcome.admitted_to_rag_at

        # ---- consent=False -> KHÔNG được nạp ----
        company.rag_data_sharing_consent = False
        db.commit()
        result_no_consent = admit_from_decision(db, outcome, key)
        check("company chưa bật consent -> admit_from_decision trả None (không nạp)", result_no_consent is None)
        db.rollback()

        # ---- consent=True -> nạp thành công, mã hoá đúng, giải mã round-trip đúng company/exception thật ----
        company.rag_data_sharing_consent = True
        db.commit()
        real_company_id = str(decision.company_id)
        real_exception_id = str(decision.exception_id)

        case = admit_from_decision(db, outcome, key)
        db.commit()
        check("consent=True -> admit_from_decision trả về 1 RagCaseBank", case is not None)

        if case is not None:
            source = db.execute(select(RagCaseSourceMap).where(RagCaseSourceMap.case_id == case.case_id)).scalar_one_or_none()
            check("có bản ghi rag_case_source_map tương ứng", source is not None)
            if source is not None:
                check(
                    "company_id_encrypted giải mã đúng company thật",
                    decrypt_value(source.company_id_encrypted, key) == real_company_id,
                )
                check(
                    "exception_id_encrypted giải mã đúng exception thật",
                    decrypt_value(source.exception_id_encrypted, key) == real_exception_id,
                )
            check(
                "rag_case_bank KHÔNG lưu company_id/exception_id thô ở đâu cả",
                not hasattr(case, "company_id") and not hasattr(case, "exception_id"),
            )
            db.refresh(outcome)
            check("outcome.admitted_to_rag_at được set sau khi nạp", outcome.admitted_to_rag_at is not None)

            # Gọi lại lần 2 -> outcome đã admitted, không còn trong candidate list nữa (tránh nạp trùng)
            candidates_after = find_admission_candidates(db, min_delay_days=0, max_delay_days=1)
            check("outcome đã nạp rồi thì KHÔNG còn trong danh sách candidate nữa", outcome.outcome_id not in [o.outcome_id for o in candidates_after])

        # Dọn dẹp
        if case is not None:
            db.execute(delete(RagCaseSourceMap).where(RagCaseSourceMap.case_id == case.case_id))
            db.execute(delete(RagCaseBank).where(RagCaseBank.case_id == case.case_id))
        outcome.admitted_to_rag_at = original_admitted_at
        company.rag_data_sharing_consent = original_consent
        db.commit()
finally:
    db.close()

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
