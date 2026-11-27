"""
Config - moi thu lien quan den provider/model deu doc tu bien moi truong.
Khong hard-code API key hay ten model o bat cu dau khac trong project.
"""

import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
# DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

ENABLE_PROVIDERS = [
    p.strip() for p in os.environ.get("ENABLE_PROVIDERS", "gemini").split(",") if p.strip()
]

# --- Chế độ chạy của widget ---
# "local"  : widget gọi thẳng handle_chat trên máy này (không cần server)
# "server" : widget gọi qua HTTP tới YUI_SERVER_URL
YUI_MODE = os.environ.get("YUI_MODE", "local").strip().lower()
YUI_SERVER_URL = os.environ.get("YUI_SERVER_URL", "").rstrip("/")
