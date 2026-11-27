"""
Chat CLI - noi chuyen voi Yui qua terminal, dung chung luong xu ly voi server.
Chay: python chat.py   |   Go "thoat" de dung.
"""
import logging

logging.basicConfig(level=logging.WARNING)
for name in ["httpx", "httpx2", "google_genai", "httpcore"]:
    logging.getLogger(name).setLevel(logging.WARNING)

from backend import memory
from backend.chat_service import handle_chat
from backend.router import AIRouter


def main():
    memory.init_db()
    ai_router = AIRouter()
    print("Yui da san sang. Go 'thoat' de dung.\n")

    while True:
        try:
            user_input = input("Ban: ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not user_input:
            continue
        if user_input.lower() == "thoat":
            break

        result = handle_chat(ai_router, user_input)
        print(f"Yui: {result['reply']}\n")


if __name__ == "__main__":
    main()