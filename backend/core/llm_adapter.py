"""llm_adapter.py — lớp trung gian DUY NHẤT gọi LLM (mục 2 TECHNICAL_SPEC.md).

Đổi LLM (model khác, provider khác) chỉ cần sửa file này — mọi nơi khác trong
code (option_generator.py) chỉ gọi qua `generate(...)`, không import SDK LLM
trực tiếp.

Dùng SDK `google-genai` (KHÔNG dùng `google-generativeai` như liệt kê ở mục 16
— package đó đã bị Google deprecated hoàn toàn, ngừng nhận update/fix lỗi,
xem cảnh báo FutureWarning khi import). `google-genai` là SDK chính thức thay
thế, cùng thuộc Google, cùng gọi model `gemini-2.5-flash`, đổi 1 dòng cài đặt
trong mục 16 mà không ảnh hưởng gì khác trong spec.

XOAY VÒNG NHIỀU KEY: free tier Gemini giới hạn 20 request/ngày/key — với
lượng test thật xuyên suốt Giai đoạn 6-10, 1 key không đủ (đã thật sự chạm
giới hạn lúc test 10.3, rồi lại chạm lần nữa lúc regression test 2026-09-03
dù đã có 3 key). User tiếp tục cấp thêm key dự phòng (đến `_5` tại thời điểm
viết dòng này) — `_load_keys()` tự quét `GEMINI_API_KEY`, `GEMINI_API_KEY_2`
... `GEMINI_API_KEY_10` (chỉ lấy biến nào thực sự có trong .env), KHÔNG cần
sửa code mỗi lần thêm/bớt key, chỉ cần thêm dòng `GEMINI_API_KEY_N=...` vào
.env. Khi 1 key báo lỗi hạn mức (429 RESOURCE_EXHAUSTED) HOẶC lỗi quá tải
tạm thời phía Google (503 UNAVAILABLE — quan sát thực tế 2026-09-03: key vừa
lỗi 503 thử lại vài phút sau lại thành công), tự động xoay sang key tiếp
theo NGAY TRONG 1 lần gọi `generate()`, không cần option_generator.py biết
chuyện này (đúng nguyên tắc mục 2: chi tiết LLM chỉ nằm trong file này).

ĐỔI MODEL sang `gemini-3.6-flash` (khác mục 8 TECHNICAL_SPEC.md ghi
`gemini-2.5-flash`) — lý do kỹ thuật bắt buộc: gọi thử `gemini-2.5-flash`
bằng 2 key mới (`_2`/`_3`) trả lỗi thật `404 NOT_FOUND — "This model
models/gemini-2.5-flash is no longer available to new users. Please update
your code to use models/gemini-3.6-flash"`. Google đã sunset model này cho
API key/project mới — chỉ key gốc (tạo trước) còn gọi được (nhưng đang hết
quota). `gemini-3.6-flash` gọi được trên CẢ 3 key (kể cả key gốc — quota
riêng, không tính chung với quota `2.5-flash` đã hết), xác nhận bằng gọi
thật. Xem TECHNICAL_SPEC.md mục 8 đã cập nhật theo quyết định này.
"""
import os
import re
import time

from dotenv import load_dotenv
from google import genai

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

MODEL_NAME = "gemini-3.6-flash"

_MAX_KEYS = 10  # GEMINI_API_KEY, GEMINI_API_KEY_2, ..., GEMINI_API_KEY_10 — xem docstring đầu file
_clients: dict[str, genai.Client] = {}
_current_key_index = 0


def _load_keys() -> list[str]:
    names = ["GEMINI_API_KEY"] + [f"GEMINI_API_KEY_{i}" for i in range(2, _MAX_KEYS + 1)]
    keys = [os.environ.get(name) for name in names]
    return [k for k in keys if k]


def _get_client_for_key(api_key: str) -> genai.Client:
    if api_key not in _clients:
        _clients[api_key] = genai.Client(api_key=api_key)
    return _clients[api_key]


_RETRYABLE_ERROR_PATTERN = re.compile(r"RESOURCE_EXHAUSTED|429|quota|UNAVAILABLE|503", re.IGNORECASE)


def _is_retryable_error(exc: Exception) -> bool:
    """429/quota (hạn mức riêng của key này) và 503/UNAVAILABLE (Google quá
    tải tạm thời — quan sát thực tế: thử lại sau vài phút, có khi ngay key
    khác, là qua) đều đáng thử key khác trước khi bỏ cuộc. Lỗi còn lại (key
    sai, network...) xoay key không giúp được gì, dừng ngay."""
    return bool(_RETRYABLE_ERROR_PATTERN.search(str(exc)))


class LLMCallResult:
    def __init__(self, text: str, tokens_in: int, tokens_out: int, latency_ms: int, success: bool, error: "str | None" = None):
        self.text = text
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.latency_ms = latency_ms
        self.success = success
        self.error = error


def generate(prompt: str, model_name: str = MODEL_NAME) -> LLMCallResult:
    """Gọi LLM với 1 prompt đầy đủ (đã ghép system+user+CONTEXT). Trả về
    `LLMCallResult` — KHÔNG raise exception khi lỗi, để caller (option_generator)
    tự quyết định retry/fallback theo mục 8. Tự xoay vòng key khi gặp lỗi
    hạn mức (xem docstring đầu file) — thử LẦN LƯỢT hết các key trước khi
    báo thất bại."""
    global _current_key_index
    keys = _load_keys()
    if not keys:
        raise RuntimeError("Chưa cấu hình GEMINI_API_KEY (hoặc _2.._10) trong .env")

    last_error = None
    start = time.monotonic()
    for attempt in range(len(keys)):
        key_index = (_current_key_index + attempt) % len(keys)
        api_key = keys[key_index]
        client = _get_client_for_key(api_key)
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            latency_ms = int((time.monotonic() - start) * 1000)
            usage = response.usage_metadata
            tokens_in = usage.prompt_token_count if usage else 0
            tokens_out = usage.candidates_token_count if usage else 0
            _current_key_index = key_index  # key này còn dùng được -> giữ làm key ưu tiên cho lần gọi sau
            return LLMCallResult(response.text, tokens_in, tokens_out, latency_ms, success=True)
        except Exception as exc:  # noqa: BLE001 - LLM có thể lỗi đủ kiểu (network, quota, key sai...)
            last_error = exc
            if not _is_retryable_error(exc):
                break  # lỗi không phải hạn mức/quá tải tạm thời (vd network, key sai) -> xoay key không giúp được gì, dừng ngay
            # Hạn mức hoặc quá tải tạm thời -> thử key tiếp theo trong vòng lặp, không trả lỗi vội.

    latency_ms = int((time.monotonic() - start) * 1000)
    _current_key_index = (_current_key_index + 1) % len(keys)  # lần gọi sau bắt đầu từ key khác, tránh kẹt ở key vừa hết hạn mức
    return LLMCallResult("", 0, 0, latency_ms, success=False, error=str(last_error))
