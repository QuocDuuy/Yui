"""
Memory - Quản lý Ký ức và Ngữ cảnh Động cho Yui.
"""

import sqlite3
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from .providers.base import ChatMessage

DB_PATH = Path(__file__).resolve().parent.parent / "yui.db"


def _get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def log_message(role: str, content: str):
    conn = _get_connection()
    conn.execute(
        "INSERT INTO conversation_log (timestamp, role, content) VALUES (?, ?, ?)",
        (datetime.now().isoformat(), role, content),
    )
    conn.commit()
    conn.close()


def get_recent_history(limit: int = 20) -> List[ChatMessage]:
    conn = _get_connection()
    rows = conn.execute(
        "SELECT role, content FROM conversation_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    rows.reverse()
    return [ChatMessage(role=r, content=c) for r, c in rows]


def add_fact(content: str) -> bool:
    content = content.strip()
    if not content:
        return False
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO user_facts (content, created_at) VALUES (?, ?)",
            (content, datetime.now().isoformat()),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_all_facts() -> List[str]:
    conn = _get_connection()
    rows = conn.execute("SELECT content FROM user_facts ORDER BY id ASC").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_relevant_facts(query_text: Optional[str] = None, max_facts: int = 5) -> List[str]:
    """
    Lọc ký ức thông minh: Ưu tiên các facts có từ khóa liên quan đến câu chat hiện tại.
    Nếu không có query hoặc ít liên quan, lấy các facts mới nhất để tránh làm loãng prompt.
    """
    all_facts = get_all_facts()
    if not all_facts:
        return []
    
    if not query_text:
        return all_facts[-max_facts:]

    q_lower = query_text.lower()
    relevant = []
    others = []

    for fact in all_facts:
        f_lower = fact.lower()
        # Tìm từ khóa giao thoa giữa câu nói và fact
        words = [w for w in f_lower.split() if len(w) > 2]
        if any(w in q_lower for w in words):
            relevant.append(fact)
        else:
            others.append(fact)

    # Ghép facts có độ liên quan cao nhất lên đầu
    selected = relevant + others
    return selected[:max_facts]


def build_system_prompt_with_facts(base_persona: str, current_query: Optional[str] = None) -> str:
    now_str = datetime.now().strftime("%A, %d/%m/%Y %H:%M")
    time_block = f"[THÔNG TIN THỜI GIAN THỰC]: {now_str}"

    facts = get_relevant_facts(current_query)
    if facts:
        facts_list = "\n".join(f"- {f}" for f in facts)
        facts_block = f"[KÝ ỨC CỦA YUI VỀ PAPA (CHỌN LỌC ĐỘNG)]:\n{facts_list}"
        return f"{base_persona}\n\n{time_block}\n\n{facts_block}"

    return f"{base_persona}\n\n{time_block}"


def get_last_interaction_time() -> datetime | None:
    conn = _get_connection()
    row = conn.execute("SELECT timestamp FROM conversation_log ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row and row[0]:
        try:
            return datetime.fromisoformat(row[0])
        except Exception:
            return None
    return None


EXTRACTION_PROMPT = """Phân tích câu nói sau của Papa. Nếu câu nói tiết lộ bất kỳ sở thích, thói quen, công việc, sức khỏe hoặc tình cảm cá nhân nào cần nhớ lâu dài, hãy tóm tắt thành 1 câu ngắn gọn (ví dụ: 'Papa thích uống cafe đen', 'Papa hay thức khuya').
Nếu chỉ là câu chào hỏi, đùa vui xã giao, hỏi giờ giấc hoặc trò chuyện thông thường không có dữ liệu mới, chỉ trả về đúng chữ: NONE.

Câu nói của Papa: "{user_text}"
Kết quả:"""


def _async_extract_fact(user_text: str, ai_router):
    try:
        from .providers.base import ChatMessage
        prompt = EXTRACTION_PROMPT.format(user_text=user_text)
        res = ai_router.generate_reply(
            system_prompt="Bạn là bộ lọc trích xuất thông tin. Chỉ trả về 1 fact ngắn hoặc chữ NONE.",
            messages=[ChatMessage(role="user", content=prompt)],
            mode="simple",
        )
        fact = res.get("reply", "").strip()
        if fact and "NONE" not in fact and len(fact) < 150:
            if add_fact(fact):
                print(f"\n*(Yui đã âm thầm ghi nhớ: {fact})*")
    except Exception:
        pass


def extract_fact_in_background(user_text: str, ai_router):
    thread = threading.Thread(
        target=_async_extract_fact,
        args=(user_text, ai_router),
        daemon=True,
    )
    thread.start()

def get_last_session_context() -> str | None:
    """
    Lay tin nhan cuoi cung cua phien truoc (neu da cach hien tai tren 6 tieng)
    de tao su lien ket mach hoi thoai tu nhien khi bat dau ngay moi.
    """
    conn = _get_connection()
    # Lay tin nhan gan nhat cua user
    row = conn.execute(
        "SELECT timestamp, content FROM conversation_log WHERE role = 'user' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if not row or not row[0]:
        return None

    try:
        last_time = datetime.fromisoformat(row[0])
        now = datetime.now()
        # Neu cuoc tro chuyen cu cach hien tai it nhat 6 tieng (vi du: tu toi hom truoc toi sang nay)
        if (now - last_time).total_seconds() >= 6 * 3600:
            return row[1].strip()
    except Exception:
        return None

    return None

init_db()