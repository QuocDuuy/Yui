"""
Chat CLI - noi chuyen truc tiep voi Yui qua terminal, dung de test memory.
Chay: python chat.py
Go "thoat" de dung. Go "nho: <dieu can nho>" de luu 1 fact lau dai.
"""
import logging
logging.basicConfig(level=logging.WARNING)
for name in ["httpx", "httpx2", "google_genai", "httpcore"]:
    logging.getLogger(name).setLevel(logging.WARNING)


from backend.router import AIRouter
from backend.providers.base import ChatMessage
from backend.persona import SYSTEM_PROMPT
from backend import memory

ai_router = AIRouter()

print("Yui da san sang. Go 'thoat' de dung, 'nho: ...' de luu 1 dieu can nho lau dai.\n")

while True:
    user_input = input("Ban: ").strip()

    if not user_input:
        continue

    if user_input.lower() == "thoat":
        break

    # Tu dong bat va luu fact neu chua tu khoa (Khong can go 'nho:' nua)
    if memory.check_and_extract_fact(user_input):
        print(f"*(Yui da lang nghe va ghi nho vao ky uc)*")

    # Tiep tuc luong hoi thoai binh thuong ma khong bi dung lai
    history = memory.get_recent_history(limit=20)
    messages = history + [ChatMessage(role="user", content=user_input)]
    system_prompt = memory.build_system_prompt_with_facts(SYSTEM_PROMPT)

    result = ai_router.generate_reply(system_prompt=system_prompt, messages=messages)
    reply = result["reply"]
    print(f"Yui: {reply}\n")

    memory.log_message("user", user_input)
    memory.log_message("assistant", reply)