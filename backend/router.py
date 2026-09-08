"""
AIRouter - noi duy nhat quyet dinh: dung provider nao cho yeu cau nay,
va lam gi khi provider do loi/rate-limit/timeout.

Day la lop duy nhat "biet" ve viec co 3 provider. Moi noi khac trong
app (trigger engine, /api/chat endpoint sau nay) chi goi
router.generate_reply(...) va khong can quan tam ben duoi dang dung
Gemini, DeepSeek hay Groq.
"""

import logging
from typing import List, Optional

from .providers.base import AIProvider, ChatMessage, ProviderError
from .providers.gemini_provider import GeminiProvider
# from .providers.deepseek_provider import DeepSeekProvider
from .providers.groq_provider import GroqProvider

logger = logging.getLogger("ai_router")


# Tu khoa don gian de nhan biet yeu cau "phuc tap" (giai thich ngu phap,
# ly do, so sanh...). Day la heuristic tam thoi - co the thay bang cach
# phan loai thong minh hon sau nay ma khong dong den phan con lai cua
# router.
COMPLEX_KEYWORDS = [
    # Dặn dò trực tiếp
    "nhớ nhé", "nho nhe", "nhớ nha", "nho nha", 
    "ghi nhớ", "ghi nho", "nhớ kỹ", "nho ky",
    "đừng quên", "dung quen", "nhớ giùm", "nho gium",
    
    # Chia sẻ sở thích, thói quen
    "thích", "thich", "khoái", "khoai",
    "ghét", "ghet", "không thích", "khong thich",
    "dị ứng", "di ung", "thói quen", "thoi quen",
    
    # Thông tin cá nhân
    "tên của", "ten cua", "mình là", "minh la",
    "ba là", "ba la", "papa là", "papa la",
    "công việc", "cong viec", "quê ở", "que o",
]

MEMORY_KEYWORDS = [
    # Dặn dò trực tiếp
    "nhớ nhé", "nho nhe", "nhớ nha", "nho nha", 
    "ghi nhớ", "ghi nho", "nhớ kỹ", "nho ky",
    "đừng quên", "dung quen", "nhớ giùm", "nho gium",
    
    # Chia sẻ sở thích, thói quen
    "thích", "thich", "khoái", "khoai",
    "ghét", "ghet", "không thích", "khong thich",
    "dị ứng", "di ung", "thói quen", "thoi quen",
    
    # Thông tin cá nhân
    "tên của", "ten cua", "mình là", "minh la",
    "ba là", "ba la", "papa là", "papa la",
    "công việc", "cong viec", "quê ở", "que o",
]

def classify_complexity(user_message: str) -> str:
    """Tra ve 'simple' hoac 'complex' dua tren noi dung tin nhan."""
    lowered = user_message.lower()
    if any(keyword in lowered for keyword in COMPLEX_KEYWORDS):
        return "complex"
    if len(user_message) > 200:
        return "complex"
    return "simple"


class AIRouter:
    def __init__(self):
        # Khoi tao provider "lazy" - de neu thieu 1 API key, chi provider
        # do bao loi khi dung toi, khong lam sap ca ung dung ngay tu dau.
        self._providers: dict = {}

    def _get_provider(self, name: str) -> AIProvider:
        if name not in self._providers:
            if name == "gemini":
                self._providers[name] = GeminiProvider()
            elif name == "groq":
                self._providers[name] = GroqProvider()
            # elif name == "deepseek":
            #     self._providers[name] = DeepSeekProvider()
            
            else:
                raise ValueError(f"Provider khong ton tai: {name}")
        return self._providers[name]

    def _fallback_chain(self, task_type: str) -> List[str]:
        """
        Thu tu uu tien provider cho tung loai task.

        - simple: Gemini (mac dinh, re + nhanh) -> Groq (fallback nhanh)
          -> DeepSeek (phuong an cuoi, dat hon)
        - complex: DeepSeek (manh ve reasoning) -> Groq (fallback nhanh)
          -> Gemini (phuong an cuoi)
        """
        if task_type == "complex":
            return ["gemini", "groq" ] #"deepseek"
        return ["gemini", "groq"] #"deepseek"

    def generate_reply(
        self,
        system_prompt: str,
        messages: List[ChatMessage],
        mode: Optional[str] = None,
    ) -> dict:
        """
        mode: neu duoc truyen vao ('simple' hoac 'complex'), bo qua
        buoc tu phan loai va dung luon gia tri nay. De trong (None) de
        router tu quyet dinh dua tren noi dung tin nhan cuoi cung.
        """
        task_type = mode or classify_complexity(messages[-1].content)
        chain = self._fallback_chain(task_type)

        last_error = None
        for provider_name in chain:
            try:
                provider = self._get_provider(provider_name)
                reply_text = provider.generate(system_prompt, messages)
                return {
                    "reply": reply_text,
                    "provider_used": provider_name,
                    "task_type": task_type,
                }
            except ProviderError as e:
                logger.warning(
                    f"[AIRouter] Provider '{provider_name}' loi: {e}. "
                    f"Chuyen sang provider tiep theo trong chain."
                )
                last_error = e
                continue

        raise RuntimeError(
            f"Tat ca provider deu loi cho task_type='{task_type}'. "
            f"Loi cuoi cung: {last_error}"
        )
