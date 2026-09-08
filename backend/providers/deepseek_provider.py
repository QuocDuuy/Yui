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
        if not config.DEEPSEEK_API_KEY:
            raise ProviderAuthError("Thieu DEEPSEEK_API_KEY trong bien moi truong.")
        self.client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )
        self.model_name = config.DEEPSEEK_MODEL

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
