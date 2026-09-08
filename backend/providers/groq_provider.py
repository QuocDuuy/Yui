"""
Groq provider - dung SDK chinh thuc cua Groq (co cau truc loi giong openai).
Dung: pip install groq
"""

from typing import List

import groq
from groq import Groq

from .. import config
from .base import (
    AIProvider,
    ChatMessage,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class GroqProvider(AIProvider):
    name = "groq"

    def __init__(self):
        if not config.GROQ_API_KEY:
            raise ProviderAuthError("Thieu GROQ_API_KEY trong bien moi truong.")
        self.client = Groq(api_key=config.GROQ_API_KEY)
        self.model_name = config.GROQ_MODEL

    def generate(self, system_prompt: str, messages: List[ChatMessage]) -> str:
        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages += [{"role": m.role, "content": m.content} for m in messages]

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=api_messages,
            )
            return response.choices[0].message.content

        except groq.RateLimitError as e:
            raise ProviderRateLimitError(str(e)) from e
        except groq.APITimeoutError as e:
            raise ProviderTimeoutError(str(e)) from e
        except groq.AuthenticationError as e:
            raise ProviderAuthError(str(e)) from e
        except (groq.APIConnectionError, groq.InternalServerError) as e:
            raise ProviderUnavailableError(str(e)) from e
        except Exception as e:
            raise ProviderUnavailableError(f"Loi khong xac dinh tu Groq: {e}") from e
