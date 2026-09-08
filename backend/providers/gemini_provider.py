"""
Gemini provider - implement AIProvider bang Google Gemini API.
Dung SDK moi: pip install google-genai
"""

from typing import List

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from .. import config
from .base import (
    AIProvider,
    ChatMessage,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self):
        if not config.GEMINI_API_KEY:
            raise ProviderAuthError("Thieu GEMINI_API_KEY trong bien moi truong.")
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.model_name = config.GEMINI_MODEL

    def generate(self, system_prompt: str, messages: List[ChatMessage]) -> str:
        # Gemini dung dinh dang lich su rieng: role "model" thay vi "assistant"
        history = []
        for m in messages[:-1]:
            role = "model" if m.role == "assistant" else "user"
            history.append(types.Content(role=role, parts=[types.Part(text=m.content)]))

        last_message = messages[-1].content

        try:
            chat = self.client.chats.create(
                model=self.model_name,
                config=types.GenerateContentConfig(system_instruction=system_prompt),
                history=history,
            )
            response = chat.send_message(last_message)
            return response.text

        except genai_errors.ClientError as e:
            code = getattr(e, "code", None)
            if code == 429:
                raise ProviderRateLimitError(str(e)) from e
            if code in (401, 403):
                raise ProviderAuthError(str(e)) from e
            raise ProviderUnavailableError(str(e)) from e
        except genai_errors.ServerError as e:
            raise ProviderUnavailableError(str(e)) from e
        except Exception as e:
            raise ProviderUnavailableError(f"Loi khong xac dinh tu Gemini: {e}") from e