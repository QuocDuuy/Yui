"""
Chat service - luồng xử lý chat duy nhất của Yui.
server.py và chat.py đều gọi handle_chat(), không tự làm lại các bước này.
"""

import logging
from typing import Callable, Optional

from . import memory
from .persona import SYSTEM_PROMPT
from .providers.base import ChatMessage

logger = logging.getLogger("chat_service")

TRIGGER_PREFIX = "[NGU CANH TU DONG]"
MIN_FACT_TEXT_LENGTH = 8
CHAT_HISTORY_LIMIT = 10
TRIGGER_HISTORY_LIMIT = 3


def handle_chat(
    ai_router,
    user_text: str,
    image_bytes: Optional[bytes] = None,
    is_trigger: bool = False,
    vision_fn: Optional[Callable] = None,
) -> dict:
    """
    Xử lý 1 lượt chat. Trả về {"reply": str, "cognitive_data": dict}.
    vision_fn(system_prompt, user_text, image_bytes) -> dict: tạm thời do server.py truyền vào
    (sẽ chuyển vào provider ở Bước 3, mục Y-19).
    """
    user_text = (user_text or "").strip()
    is_trigger = is_trigger or user_text.startswith(TRIGGER_PREFIX)

    # 1. Trích xuất ký ức ngầm (chỉ với chat chữ thông thường)
    if not is_trigger and not image_bytes and len(user_text) > MIN_FACT_TEXT_LENGTH:
        memory.extract_fact_in_background(user_text, ai_router)

    # 2. Dựng system prompt (trigger không dùng câu nói để lọc ký ức)
    system_prompt = memory.build_system_prompt_with_facts(
        SYSTEM_PROMPT,
        current_query=None if is_trigger else user_text,
    )

    # 3. Gọi model
    if image_bytes and vision_fn:
        result = vision_fn(system_prompt, user_text, image_bytes)
    else:
        limit = TRIGGER_HISTORY_LIMIT if is_trigger else CHAT_HISTORY_LIMIT
        history = memory.get_recent_history(limit=limit)
        messages = history + [ChatMessage(role="user", content=user_text)]
        result = ai_router.generate_reply(system_prompt=system_prompt, messages=messages)

    reply = result.get("reply", "")
    # Nhánh ảnh trả dữ liệu phẳng (không có cognitive_data), nên lấy chính result làm dự phòng
    cognitive_data = result.get("cognitive_data") or result

    # 4. Ghi log + cập nhật mood (bỏ qua nếu là câu báo lỗi, để lịch sử không bị nhiễm)
    if not result.get("is_fallback", False):
        if not is_trigger:
            logged_text = f"[Gửi ảnh]: {user_text}" if image_bytes else user_text
            memory.log_message("user", logged_text)
        memory.log_message("assistant", reply)

        if not is_trigger:
            mood = cognitive_data.get("mood")
            if mood:
                try:
                    memory.update_emotional_state(mood, cognitive_data.get("inner_thought", ""))
                except Exception:
                    logger.exception("Khong cap nhat duoc emotional_state")

    return {"reply": reply, "cognitive_data": cognitive_data}