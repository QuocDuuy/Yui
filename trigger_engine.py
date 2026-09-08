"""
Trigger Engine - Giai đoạn Yui 1.5
----------------------------------
Mục đích: chạy nền liên tục, kiểm tra định kỳ:
1. Các mốc giờ cố định trong ngày (sáng, chiều, tối).
2. Kiểm tra nếu Papa lâu không tương tác thì chủ động hỏi thăm.
"""

import time
import logging
from datetime import datetime, timedelta
import random

# Chặn log cảnh báo thư viện mạng để terminal luôn sạch sẽ
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)

from backend.router import AIRouter
from backend.providers.base import ChatMessage
from backend.persona import SYSTEM_PROMPT
from backend import memory

ai_router = AIRouter()


def call_ai(context: str) -> str:
    """Goi AIRouter cho mot su kien tu dong, co dinh kem lich su + facts."""
    facts = memory.get_all_facts()
    facts_hint = ""
    if facts:
        chosen_fact = random.choice(facts)
        facts_hint = f" (Gợi ý thêm: Papa từng chia sẻ rằng '{chosen_fact}')."



    prompt_content = (
        f"Day la mot su kien tu dong: '{context}'.{facts_hint} "
        f"Hay chu dong noi mot cau phu hop, an can va tu nhien voi su kien nay."
    )

    # Giảm limit xuống 3 để tránh việc Yui bị phân tâm bởi câu chuyện cũ
    history = memory.get_recent_history(limit=3)
    messages = history + [ChatMessage(role="user", content=prompt_content)]
    system_prompt = memory.build_system_prompt_with_facts(SYSTEM_PROMPT)

    result = ai_router.generate_reply(
        system_prompt=system_prompt,
        messages=messages,
        mode="simple",
    )

    reply = result["reply"]
    memory.log_message("assistant", reply)  # chi luu cau Yui noi, khong luu prompt noi bo
    return reply


# ---------------------------------------------------------
# CẤU HÌNH: 1. Sự kiện theo giờ cố định
# ---------------------------------------------------------
SCHEDULED_EVENTS = [
    {"hour": 8, "minute": 0, "event_name": "Bây giờ là buổi sáng, hãy chủ động chào Papa và chúc Papa một ngày tốt lành."},
    {"hour": 12, "minute": 0, "event_name": "Bây giờ là buổi trưa, hãy hỏi Papa một chút về bữa trưa."},
    {"hour": 20, "minute": 0, "event_name": "Bây giờ là buổi tối, hãy hỏi Papa một chút về ngày hôm nay."},
]

# CẤU HÌNH: 2. Kích hoạt khi lâu không tương tác (Inactivity Trigger)
INACTIVITY_HOURS = 4           # Sau 4 tiếng không có tin nhắn mới sẽ hỏi thăm
ACTIVE_START_HOUR = 8          # Chỉ hỏi thăm từ 8h sáng...
ACTIVE_END_HOUR = 21           # ...đến 21h tối (tránh làm phiền lúc ngủ)
INACTIVITY_COOLDOWN_HOURS = 4  # Giãn cách giữa các lần hỏi thăm khi nhàn rỗi

last_inactivity_triggered = None
triggered_today = set()


def reset_daily_state_if_new_day(last_reset_date: datetime.date):
    """Neu sang ngay moi, xoa lai danh sach su kien da kich hoat."""
    today = datetime.now().date()
    if today != last_reset_date:
        triggered_today.clear()
        return today
    return last_reset_date


def check_scheduled_events():
    """Kiem tra xem co su kien theo gio co dinh nao can kich hoat khong."""
    now = datetime.now()

    for event in SCHEDULED_EVENTS:
        event_key = f"{event['event_name']}_{now.date()}"

        already_triggered = event_key in triggered_today
        time_matches = (now.hour == event["hour"] and now.minute == event["minute"])

        if time_matches and not already_triggered:
            trigger_event(event["event_name"])
            triggered_today.add(event_key)

def check_inactivity_event():
    """Kiểm tra nếu Papa đã lâu không trò chuyện thì chủ động bắt chuyện."""
    global last_inactivity_triggered
    now = datetime.now()

    # 1. Khung giờ hoạt động
    if not (ACTIVE_START_HOUR <= now.hour < ACTIVE_END_HOUR):
        return

    # 2. Lấy timestamp của tương tác cuối từ SQLite
    last_time = memory.get_last_interaction_time()
    if not last_time:
        return

    # Nếu tương tác cuối cùng chính là câu hỏi thăm gần nhất của Trigger -> bỏ qua để không spam liên tục
    if last_inactivity_triggered and last_time <= last_inactivity_triggered:
        return

    # 3. Tính số giây nhàn rỗi kể từ tin nhắn cuối cùng
    idle_seconds = (now - last_time).total_seconds()
    target_seconds = INACTIVITY_HOURS * 3600  # 0.005h = 18s

    print(f"[Debug] Tin nhắn cuối cách: {int(idle_seconds)}s / Cần: {int(target_seconds)}s")

    # 4. Kích hoạt khi đủ thời gian không tương tác
    if idle_seconds >= target_seconds:
        last_inactivity_triggered = now
        trigger_event("Đã khá lâu Papa chưa quay lại trò chuyện, hãy chủ động hỏi thăm Papa xem có đang bận hay mệt mỏi không.")


def trigger_event(event_name: str):
    """Goi AI theo su kien duoc kich hoat."""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Trigger kich hoat: {event_name}")
    reply = call_ai(event_name)
    print(f"Yui:\n{reply}\n")


def run():
    """Vong lap chinh - chay nen, kiem tra moi 30 giay."""
    print("Trigger engine (Yui 1.5) da khoi dong. Dang theo doi su kien...")
    last_reset_date = datetime.now().date()

    while True:
        last_reset_date = reset_daily_state_if_new_day(last_reset_date)
        check_scheduled_events()
        check_inactivity_event()
        time.sleep(30)


if __name__ == "__main__":
    run()