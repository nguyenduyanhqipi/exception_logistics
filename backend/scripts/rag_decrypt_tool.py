"""rag_decrypt_tool.py — công cụ giải mã tra vết, CỐ Ý TÁCH KHỎI ứng dụng
chính (mục 20.3: "không phải 1 API công khai"). Chạy TAY tại chỗ, cần ĐÚNG 2
người có mặt cùng lúc, mỗi người tự gõ nửa khoá của mình (không ai nhìn thấy
nửa khoá của người kia trên màn hình — dùng getpass, không echo). Yêu cầu
tra vết đã có sẵn phải ở trạng thái 'approved' (đã qua approve_trace_request,
người phê duyệt KHÁC người khởi tạo) — script này KHÔNG tự tạo/duyệt yêu cầu,
dùng `POST /api/rag-trace/requests` (+ /approve) qua API bình thường trước.

Chạy: python scripts/rag_decrypt_tool.py <request_id>

Kết quả giải mã CHỈ hiển thị ĐÚNG 1 LẦN ra màn hình — KHÔNG ghi log, KHÔNG
lưu file, KHÔNG lưu lại DB (decrypt_trace() không làm gì trong số đó).
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from core.rag_trace import TraceRequestError, decrypt_trace


def _read_key_half(label: str) -> bytes:
    raw = getpass.getpass(f"Nhập {label} (hex, không hiện lên màn hình): ").strip()
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        print(f"{label} không phải chuỗi hex hợp lệ.")
        sys.exit(1)
    if len(key) != 32:
        print(f"{label} phải đúng 32 byte (64 ký tự hex) cho AES-256, nhận được {len(key)} byte.")
        sys.exit(1)
    return key


def main():
    if len(sys.argv) != 2:
        print("Dùng: python scripts/rag_decrypt_tool.py <request_id>")
        sys.exit(1)
    request_id = sys.argv[1]

    print("=== Công cụ giải mã tra vết RAG (mục 20.3) ===")
    print("Yêu cầu ĐÚNG 2 người có mặt — mỗi người tự gõ nửa khoá của mình.\n")

    k1 = _read_key_half("K1 (founder)")
    k2 = _read_key_half("K2 (người thứ hai được chỉ định)")

    performed_by_company_id = input("company_id của người bấm giải mã (ghi audit log): ").strip()
    performed_by_user_id = input("user_id của người bấm giải mã (ghi audit log): ").strip()

    db = SessionLocal()
    try:
        result = decrypt_trace(db, request_id, k1, k2, performed_by_company_id, performed_by_user_id)
    except TraceRequestError as exc:
        print(f"LỖI: {exc}")
        sys.exit(1)
    finally:
        db.close()

    print("\n=== KẾT QUẢ (chỉ hiển thị 1 lần, không lưu lại ở đâu) ===")
    print(f"company_id:   {result['company_id']}")
    print(f"exception_id: {result['exception_id']}")
    print("===========================================================\n")


if __name__ == "__main__":
    main()
