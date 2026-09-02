"""Test xoay vòng nhiều API key trong llm_adapter.py (bổ sung sau Giai đoạn 10
— user cấp thêm 2 key dự phòng vì free tier 20 request/ngày/key không đủ).
Mock client thay vì gọi Gemini thật, để test logic xoay vòng độc lập với
trạng thái quota thật của các key tại thời điểm chạy."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.llm_adapter as la

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if cond:
        passed += 1
    else:
        failed += 1


def make_fake_response(text="ok"):
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata.prompt_token_count = 5
    resp.usage_metadata.candidates_token_count = 3
    return resp


QUOTA_ERROR = Exception("429 RESOURCE_EXHAUSTED. quota exceeded")
NETWORK_ERROR = Exception("Connection timed out")

with patch.object(la, "_load_keys", return_value=["key1", "key2", "key3"]):
    la._clients.clear()
    la._current_key_index = 0

    # ---- Test 1: key1 hết hạn mức -> tự xoay sang key2, thành công ----
    call_log = []

    def fake_get_client(api_key):
        client = MagicMock()

        def generate_content(model, contents):
            call_log.append(api_key)
            if api_key == "key1":
                raise QUOTA_ERROR
            return make_fake_response("từ " + api_key)

        client.models.generate_content.side_effect = generate_content
        return client

    with patch.object(la, "_get_client_for_key", side_effect=fake_get_client):
        result = la.generate("prompt test")
        check("Xoay từ key1 (hết hạn mức) sang key2 thành công", result.success and "key2" in result.text)
        check("Đã thử đúng key1 trước rồi mới tới key2", call_log == ["key1", "key2"])
        check("_current_key_index cập nhật về key2 (index=1) cho lần gọi sau", la._current_key_index == 1)

    # ---- Test 2: lỗi KHÔNG PHẢI hạn mức (network) -> dừng ngay, không xoay lung tung ----
    call_log.clear()
    la._current_key_index = 0

    def fake_get_client_network_error(api_key):
        client = MagicMock()

        def generate_content(model, contents):
            call_log.append(api_key)
            raise NETWORK_ERROR

        client.models.generate_content.side_effect = generate_content
        return client

    with patch.object(la, "_get_client_for_key", side_effect=fake_get_client_network_error):
        result = la.generate("prompt test 2")
        check("Lỗi network (không phải hạn mức): thất bại graceful, không raise", result.success is False)
        check("Lỗi network: KHÔNG thử hết cả 3 key (dừng ngay ở key đầu)", call_log == ["key1"])

    # ---- Test 3: cả 3 key đều hết hạn mức -> thất bại graceful sau khi thử đủ 3 ----
    call_log.clear()
    la._current_key_index = 0

    def fake_get_client_all_quota(api_key):
        client = MagicMock()

        def generate_content(model, contents):
            call_log.append(api_key)
            raise QUOTA_ERROR

        client.models.generate_content.side_effect = generate_content
        return client

    with patch.object(la, "_get_client_for_key", side_effect=fake_get_client_all_quota):
        result = la.generate("prompt test 3")
        check("Cả 3 key hết hạn mức: thất bại graceful (không raise exception)", result.success is False)
        check("Đã thử đủ cả 3 key trước khi báo thất bại", set(call_log) == {"key1", "key2", "key3"})

print(f"\n{passed} PASS, {failed} FAIL")
if failed:
    sys.exit(1)
