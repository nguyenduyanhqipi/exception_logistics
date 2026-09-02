"""llm_adapter.py — lớp trung gian DUY NHẤT gọi LLM (mục 2 TECHNICAL_SPEC.md).

Đổi LLM (model khác, provider khác) chỉ cần sửa file này — mọi nơi khác trong
code (option_generator.py) chỉ gọi qua `generate(...)`, không import SDK LLM
trực tiếp.

Dùng SDK `google-genai` (KHÔNG dùng `google-generativeai` như liệt kê ở mục 16
— package đó đã bị Google deprecated hoàn toàn, ngừng nhận update/fix lỗi,
xem cảnh báo FutureWarning khi import). `google-genai` là SDK chính thức thay
thế, cùng thuộc Google, cùng gọi model `gemini-2.5-flash`, đổi 1 dòng cài đặt
trong mục 16 mà không ảnh hưởng gì khác trong spec.
"""
import os
import time

from dotenv import load_dotenv
from google import genai

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

MODEL_NAME = "gemini-2.5-flash"

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY chưa được cấu hình trong .env")
        _client = genai.Client(api_key=api_key)
    return _client


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
    tự quyết định retry/fallback theo mục 8."""
    client = _get_client()
    start = time.monotonic()
    try:
        response = client.models.generate_content(model=model_name, contents=prompt)
        latency_ms = int((time.monotonic() - start) * 1000)
        usage = response.usage_metadata
        tokens_in = usage.prompt_token_count if usage else 0
        tokens_out = usage.candidates_token_count if usage else 0
        return LLMCallResult(response.text, tokens_in, tokens_out, latency_ms, success=True)
    except Exception as exc:  # noqa: BLE001 - LLM có thể lỗi đủ kiểu (network, quota, key sai...)
        latency_ms = int((time.monotonic() - start) * 1000)
        return LLMCallResult("", 0, 0, latency_ms, success=False, error=str(exc))
