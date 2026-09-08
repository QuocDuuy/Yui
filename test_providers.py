from backend.providers.base import ChatMessage
from backend.providers.gemini_provider import GeminiProvider
from backend.providers.deepseek_provider import DeepSeekProvider
from backend.providers.groq_provider import GroqProvider

SYSTEM_PROMPT = "Ban la mot tro ly AI. Tra loi ngan gon bang tieng Nhat, sau do ghi nghia tieng Viet."
TEST_MESSAGE = [ChatMessage(role="user", content="Xin chao")]

providers_to_test = {
    "Gemini": GeminiProvider,
    "DeepSeek": DeepSeekProvider,
    "Groq": GroqProvider,
}

for provider_name, provider_class in providers_to_test.items():
    print(f"\n--- Dang test {provider_name} ---")
    try:
        provider = provider_class()
        reply = provider.generate(SYSTEM_PROMPT, TEST_MESSAGE)
        print(f"[OK] {provider_name} tra loi:\n{reply}")
    except Exception as e:
        print(f"[LOI] {provider_name} that bai: {e}")