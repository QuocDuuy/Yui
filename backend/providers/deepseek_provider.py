"""
DeepSeek provider - DeepSeek API tuong thich voi dinh dang OpenAI, nen
dung luon thu vien "openai" de goi, chi doi base_url. Dung: pip install openai
"""

from typing import List

import openai
from openai import OpenAI

from .. import config
from .base import (
    AIProvider,
    ChatMessage,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class DeepSeekProvider(AIProvider):
    name = "deepseek"

    def __init__(self):
        # DeepSeek hien dang TAT trong config.py (cac bien da comment), nen doc an toan
        api_key = getattr(config, "DEEPSEEK_API_KEY", None)
        if not api_key:
            raise ProviderAuthError(
                "DeepSeek dang tat: chua bat DEEPSEEK_API_KEY trong backend/config.py."
            )
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )
        self.model_name = getattr(config, "DEEPSEEK_MODEL", "deepseek-v4-flash")

    def generate(self, system_prompt: str, messages: List[ChatMessage]) -> str:
        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages += [{"role": m.role, "content": m.content} for m in messages]

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=api_messages,
            )
            return response.choices[0].message.content

        except openai.RateLimitError as e:
            raise ProviderRateLimitError(str(e)) from e
        except openai.APITimeoutError as e:
            raise ProviderTimeoutError(str(e)) from e
        except openai.AuthenticationError as e:
            raise ProviderAuthError(str(e)) from e
        except (openai.APIConnectionError, openai.InternalServerError) as e:
            raise ProviderUnavailableError(str(e)) from e
        except Exception as e:
            raise ProviderUnavailableError(f"Loi khong xac dinh tu DeepSeek: {e}") from e
