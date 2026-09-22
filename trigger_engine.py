"""
Yui Headless Background Service (Phương án 3 - Nâng cao)
-------------------------------------------------------
- Chạy ngầm trong máy tính khi Papa không bật widget.
- Bắn Windows Toast Notification kèm phát giọng đọc tiếng Nhật.
- [MỚI] Khi Papa CLICK VÀO THÔNG BÁO: Tự động khởi động Desktop Widget (yui_widget.py) lên màn hình!
"""

import sys
import os
import subprocess
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Chặn log phụ để terminal sạch sẽ
logging.basicConfig(level=logging.WARNING)
for log_name in ["httpx", "httpx2", "google_genai", "httpcore"]:
    logging.getLogger(log_name).setLevel(logging.WARNING)

from win11toast import toast

from backend.voice.tts import speak_japanese_async
from backend.router import AIRouter
from backend.providers.base import ChatMessage
from backend.persona import SYSTEM_PROMPT
from backend import memory

ai_router = AIRouter()

# Đường dẫn file widget
ROOT_DIR = Path(__file__).resolve().parent
WIDGET_PATH = ROOT_DIR / "yui_widget.py"

# --- CẤU HÌNH SỰ KIỆN THEO GIỜ CỐ ĐỊNH ---
SCHEDULED_EVENTS = [
    {"hour": 8, "minute": 0, "name": "morning_greeting", "desc": "Bây giờ là buổi sáng, hãy chủ động chào Papa và chúc Papa một ngày tốt lành."},
    {"hour": 14, "minute": 0, "name": "afternoon_checkin", "desc": "Bây giờ là buổi chiều, hãy chủ động hỏi thăm xem công việc của Papa thế nào."},
    {"hour": 21, "minute": 0, "name": "evening_checkin", "desc": "Bây giờ là buổi tối, hãy nhắc Papa nghỉ ngơi thật tốt nhé."}
]

# CẤU HÌNH NHÀN RỖI (INACTIVITY TRIGGER)
INACTIVITY_HOURS = 4         # Sau 4 tiếng không có tin nhắn sẽ kích hoạt (chỉnh nhỏ lại khi test)
ACTIVE_START_HOUR = 8          # Khung giờ hoạt động: từ 8h sáng...
ACTIVE_END_HOUR = 21           # ...đến 21h tối
INACTIVITY_COOLDOWN_HOURS = 4  # Tránh spam

last_inactivity_triggered = None
triggered_today = set()
last_reply_text = ""

def open_desktop_widget(args=None):
    """Callback kích hoạt khi Papa click vào thông báo Toast: Mở widget desktop kèm nội dung vừa thông báo."""
    global last_reply_text
    try:
        print("[Hành động]: Papa đã nhấp vào thông báo -> Đang mở Yui Desktop Widget...")
        # Truyền nội dung last_reply_text làm argument dòng lệnh cho yui_widget.py
        cmd = [sys.executable, str(WIDGET_PATH)]
        if last_reply_text:
            cmd.append(last_reply_text)
            
        subprocess.Popen(cmd, cwd=str(ROOT_DIR))
    except Exception as e:
        print(f"[Lỗi mở Widget]: {e}")


def show_toast_notification(title: str, message: str):
    """Bắn thông báo Windows 10/11 có gắn callback on_click."""
    try:
        toast(
            title=title,
            body=message,
            duration="short",
            on_click=open_desktop_widget  # Gắn sự kiện: click vào là mở widget
        )
    except Exception as e:
        print(f"[Lỗi Toast Notification]: {e}")


def execute_service_event(context_desc: str, title: str = "Yui nhắc Papa nè ♪"):
    global last_reply_text
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Kích hoạt Headless Trigger: {context_desc}")

    history = memory.get_recent_history(limit=3)
    prompt = f"[NGỮ CẢNH TỰ ĐỘNG]: {context_desc}"
    messages = history + [ChatMessage(role="user", content=prompt)]
    system_prompt = memory.build_system_prompt_with_facts(SYSTEM_PROMPT)

    result = ai_router.generate_reply(system_prompt=system_prompt, messages=messages)
    cog_data = result.get("cognitive_data", {})
    reply_formatted = result.get("reply", "")

    # Cập nhật câu nói mới nhất vào biến toàn cục
    last_reply_text = reply_formatted

    jp_text = cog_data.get("japanese", "")
    vi_text = cog_data.get("vietnamese", "")
    if not vi_text:
        vi_text = reply_formatted

    toast_title = f"Yui: {jp_text}" if jp_text else title
    show_toast_notification(title=toast_title, message=vi_text)

    # Phát giọng nói tiếng Nhật qua loa
    speak_japanese_async(reply_formatted)

    # Ghi nhận vào DB
    memory.log_message("assistant", reply_formatted)

def check_scheduled_triggers(now: datetime):
    for ev in SCHEDULED_EVENTS:
        ev_key = f"{ev['name']}_{now.date()}"
        if now.hour == ev["hour"] and now.minute == ev["minute"]:
            if ev_key not in triggered_today:
                triggered_today.add(ev_key)
                execute_service_event(ev["desc"], title="Yui nhắc nhở Papa nè!")
                return


def check_inactivity_trigger(now: datetime):
    global last_inactivity_triggered

    if not (ACTIVE_START_HOUR <= now.hour < ACTIVE_END_HOUR):
        return

    last_time = memory.get_last_interaction_time()
    if not last_time:
        return

    if last_inactivity_triggered and last_time <= last_inactivity_triggered:
        return

    idle_seconds = (now - last_time).total_seconds()
    target_seconds = INACTIVITY_HOURS * 3600

    if idle_seconds >= target_seconds:
        last_inactivity_triggered = now
        execute_service_event(
            "Đã khá lâu Papa chưa quay lại trò chuyện, hãy chủ động hỏi thăm Papa xem có đang bận hay mệt mỏi không.",
            title="Yui nhớ Papa quá à...!"
        )

    
def run():
    print("=" * 60)
    print("  YUI HEADLESS BACKGROUND SERVICE (CLICK-TO-WIDGET ENABLED)")
    print("  - Nhấn vào thông báo để mở Yui Desktop Widget")
    print("  - Nhấn Ctrl + C để dừng")
    print("=" * 60)

    last_date = datetime.now().date()
    while True:
        now = datetime.now()
        if now.date() != last_date:
            triggered_today.clear()
            last_date = now.date()

        check_scheduled_triggers(now)
        check_inactivity_trigger(now)
        time.sleep(30)


if __name__ == "__main__":
    run()