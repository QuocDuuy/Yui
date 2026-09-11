"""
AIRouter - Điều phối thông minh & Phân tích nhận thức JSON cho Yui.
"""

import json
import logging
import re
from typing import List, Optional

from .providers.base import (
    AIProvider,
    ChatMessage,
    ProviderError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError
)
from .providers.gemini_provider import GeminiProvider
from .providers.groq_provider import GroqProvider

logger = logging.getLogger("ai_router")

# Phân loại độ phức tạp THỰC SỰ
COMPLEX_KEYWORDS = [
    "ngữ pháp", "ngu phap", "tại sao", "tai sao", "giải thích", "giai thich",
    "so sánh", "so sanh", "phân tích", "phan tich", "khác nhau", "khac nhau",
    "cách dùng", "cach dung", "cấu trúc", "cau truc"
]

RATE_LIMIT_FALLBACK = {
    "inner_thought": "Hệ thống bị chạm trần hạn mức (429 Rate Limit), Yui cần chợp mắt nghỉ ngơi.",
    "mood": "worried",
    "japanese": "パパ、ユイは少しエネルギーが切れちゃいました…少しの間、休ませてくださいね。",
    "romaji": "(Papa, Yui wa sukoshi enerugii ga kirechaimashita... Sukoshi no aida, yasumasete kudasai ne.)",
    "vietnamese": "-> Papa ơi, Yui bị cạn năng lượng mất rồi... Cho Yui nghỉ ngơi một lát nhé ạ."
}


def classify_complexity(user_message: str) -> str:
    lowered = user_message.lower()
    if any(keyword in lowered for keyword in COMPLEX_KEYWORDS):
        return "complex"
    if len(user_message) > 250:
        return "complex"
    return "simple"


def parse_yui_json_response(raw_text: str) -> dict:
    """
    Bóc tách JSON nhận thức từ LLM bằng JSON Parser kết hợp Regex Fallback.
    Chống hiện tượng trào text thô do ngoặc kép hoặc rò rỉ tiếng Việt vào tiếng Nhật.
    """
    clean_text = raw_text.strip()
    data = None

    # 1. Thử phân tích JSON chuẩn
    match = re.search(r"\{.*\}", clean_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
        except Exception:
            data = None

    # 2. Fallback bằng Regex nếu AI chèn ký tự đặc biệt/ngoặc kép làm hỏng JSON chuẩn
    if not isinstance(data, dict):
        data = {}
        fields = ["inner_thought", "mood", "japanese", "romaji", "vietnamese"]
        for f in fields:
            pattern = rf'"{f}"\s*:\s*"(.*?)(?="\s*,\s*"[a-zA-Z_]+"|"\s*\}}|\Z)'
            m = re.search(pattern, clean_text, re.DOTALL)
            if m:
                val = m.group(1).replace('\\"', '"').replace('\\n', '\n').strip()
                data[f] = val

    ja = data.get("japanese", "").strip()
    ro = data.get("romaji", "").strip()
    vi = data.get("vietnamese", "").strip()
    mood = data.get("mood", "happy")
    thought = data.get("inner_thought", "")

    # 3. CHỐNG RÒ RỈ TIẾNG VIỆT VÀO TIẾNG NHẬT (Bảo vệ giọng đọc TTS và Widget)
    has_vietnamese = bool(re.search(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", ja, re.IGNORECASE))
    has_japanese = bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", ja))

    if has_vietnamese and not has_japanese:
        # Nếu model vô tình viết tiếng Việt vào dòng japanese -> Hoán đổi an toàn
        if not vi:
            vi = ja
        ja = "パパ、それはですね…！"
        ro = "(Papa, sore wa desu ne...!)"

    # Định dạng chuỗi hiển thị tương thích ngược cho giao diện widget
    if not ja and not vi:
        formatted_reply = clean_text.replace("{", "").replace("}", "").strip()
    else:
        parts = [ja]
        if ro:
            parts.append(ro if (ro.startswith("(") and ro.endswith(")")) else f"({ro})")
        if vi:
            parts.append(vi if vi.startswith("->") else f"-> {vi}")
        formatted_reply = "\n".join(parts)

    return {
        "inner_thought": thought,
        "mood": mood,
        "japanese": ja,
        "romaji": ro,
        "vietnamese": vi,
        "reply": formatted_reply,
        "cognitive_data": data
    }


class AIRouter:
    def __init__(self):
        self._providers: dict = {}

    def _get_provider(self, name: str) -> AIProvider:
        if name not in self._providers:
            if name == "gemini":
                self._providers[name] = GeminiProvider()
            elif name == "groq":
                self._providers[name] = GroqProvider()
            else:
                raise ValueError(f"Provider khong ton tai: {name}")
        return self._providers[name]

    def _fallback_chain(self, task_type: str) -> List[str]:
        # Ưu tiên Gemini -> Groq
        return ["gemini", "groq"]

    def generate_reply(self, system_prompt: str, messages: list, mode: str = "simple") -> dict:
        last_error = None
        hit_rate_limit = False

        for provider_name in self._fallback_chain(mode):
            try:
                provider = self._get_provider(provider_name)
                raw_text = provider.generate(system_prompt=system_prompt, messages=messages)

                # Bóc tách JSON
                return parse_yui_json_response(raw_text)

            except ProviderRateLimitError as e:
                hit_rate_limit = True
                last_error = e
                continue  # Thử provider tiếp theo trong chain
            except Exception as e:
                last_error = e
                continue

        # NẾU TẤT CẢ ĐỀU HẾT HẠN MỨC HOẶC GẶP RATE LIMIT:
        if hit_rate_limit or isinstance(last_error, ProviderRateLimitError):
            formatted_reply = (
                f"{RATE_LIMIT_FALLBACK['japanese']}\n"
                f"{RATE_LIMIT_FALLBACK['romaji']}\n"
                f"{RATE_LIMIT_FALLBACK['vietnamese']}"
            )
            return {
                "reply": formatted_reply,
                "cognitive_data": RATE_LIMIT_FALLBACK
            }

        # Các lỗi không xác định khác (mạng rớt, timeout...)
        logger.error(f"Tat ca provider deu loi cho mode='{mode}'. Loi cuoi: {last_error}")
        return {
            "reply": "パパ、少し通信が不安定みたいです…\n(Papa, sukoshi tsuushin ga fuantei mitai desu...)\n-> Papa ơi, kết nối mạng có vẻ hơi chập chờn một chút ạ...",
            "cognitive_data": {
                "mood": "worried",
                "japanese": "パパ、少し通信が不安定みたいです…",
                "vietnamese": "-> Papa ơi, kết nối mạng có vẻ hơi chập chờn một chút ạ..."
            }
        }