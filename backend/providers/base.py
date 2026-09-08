"""
Provider interface - "hop dong" chung ma moi provider (Gemini, DeepSeek,
Groq...) phai tuan theo.

Nho co interface nay, AIRouter khong can biet minh dang noi chuyen voi
provider nao - no chi goi generate() va nhan ve text hoac 1 loai loi
chuan hoa. Muon them provider moi (vi du OpenAI, Claude...) sau nay,
chi can tao 1 class moi ke thua AIProvider, khong phai sua Router hay
frontend.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class ChatMessage:
    role: str      # "user" hoac "assistant"
    content: str


# ---------------------------------------------------------
# Cac loai loi chuan hoa. Moi provider co the nem ra loi rieng cua SDK
# (vi du google.api_core.exceptions.ResourceExhausted, openai.RateLimitError...)
# nhung phai "dich" lai thanh 1 trong cac loai duoi day truoc khi de
# loi thoat ra khoi ham generate(). Nho vay AIRouter chi can bat
# ProviderError chung, khong can biet chi tiet SDK cua tung hang.
# ---------------------------------------------------------
class ProviderError(Exception):
    """Loi goc cho moi loi lien quan den provider."""


class ProviderRateLimitError(ProviderError):
    """Provider bao rate limit (qua so luong request cho phep)."""


class ProviderTimeoutError(ProviderError):
    """Request toi provider bi timeout."""


class ProviderUnavailableError(ProviderError):
    """Provider dang down / loi ket noi / loi server (5xx)."""


class ProviderAuthError(ProviderError):
    """API key sai hoac thieu."""


class AIProvider(ABC):
    """Interface ma moi provider phai implement."""

    name: str = "unknown"

    @abstractmethod
    def generate(self, system_prompt: str, messages: List[ChatMessage]) -> str:
        """
        Gui yeu cau chat toi provider, tra ve text phan hoi.

        Bat buoc: neu co loi xay ra, phai bat loi goc cua SDK va nem lai
        thanh 1 trong cac ProviderError o tren, khong de loi goc (vi du
        loi rieng cua thu vien openai/google-generativeai) lot ra ngoai.
        """
        raise NotImplementedError
