"""
Test nhanh cac provider dang duoc bat trong ENABLE_PROVIDERS (file .env).
Chay: python test_providers.py
"""

from backend import config
from backend.providers.base import ChatMessage
from backend.providers.gemini_provider import GeminiProvider
from backend.providers.groq_provider import GroqProvider

SYSTEM_PROMPT = "Ban la mot tro ly AI. Tra loi ngan gon bang tieng Nhat, sau do ghi nghia tieng Viet."
TEST_MESSAGE = [ChatMessage(role="user", content="Xin chao")]

# DeepSeek dang tat (config.py da comment). Muon bat lai: mo comment trong config.py,
# them DeepSeekProvider vao day va vao AIRouter._get_provider.
AVAILABLE_PROVIDERS = {
    "gemini": GeminiProvider,
    "groq": GroqProvider,
}

for name in config.ENABLE_PROVIDERS:
    provider_class = AVAILABLE_PROVIDERS.get(name)
    if provider_class is None:
        print(f"\n--- Bo qua '{name}': khong co trong danh sach provider ho tro ---")
        continue

    print(f"\n--- Dang test {name} ---")
    try:
        provider = provider_class()
        reply = provider.generate(SYSTEM_PROMPT, TEST_MESSAGE)
        print(f"[OK] {name} tra loi:\n{reply}")
    except Exception as e:
        print(f"[LOI] {name} that bai: {e}")
