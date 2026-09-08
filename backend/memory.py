import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List
import threading

from backend.router import MEMORY_KEYWORDS

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
    rows.reverse()  # Tra ve theo thu tu thoi gian tang dan
    return [ChatMessage(role=r, content=c) for r, c in rows]


def add_fact(content: str) -> bool:
    content = content.strip()
    if not content:
        return False
    conn = _get_connection()
    try:
        # INSERT OR IGNORE de tranh trung lap noi dung y het
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


def build_system_prompt_with_facts(base_persona: str) -> str:
    # 1. Dong bo voi dinh dang prompt cua Yui 0 (Kem thu trong tuan)
    now_str = datetime.now().strftime("%A, %d/%m/%Y %H:%M")
    time_block = f"[THONG TIN THOI GIAN THUC]: {now_str}"

    # 2. Chen facts neu co
    facts = get_all_facts()
    if facts:
        facts_list = "\n".join(f"- {f}" for f in facts)
        facts_block = f"[THONG TIN DA BIET VE PAPA]:\n{facts_list}"
        return f"{base_persona}\n\n{time_block}\n\n{facts_block}"

    return f"{base_persona}\n\n{time_block}"

def check_and_extract_fact(text: str) -> bool:
    """
    Kiem tra neu cau noi chua tu khoa can ghi nho.
    Neu co, tu dong luu ca cau vao bang user_facts.
    """
    text_clean = text.strip()
    text_lower = text_clean.lower()
    
    # 1. Khong luu neu la cau hoi (tranh nham lan khi hoi: "ba thich gi nho khong?")
    if text_clean.endswith("?") or text_clean.endswith("không") or text_clean.endswith("chưa"):
        return False

    # 2. Quet xem co chua tu khoa ghi nho khong
    matched = any(kw in text_lower for kw in MEMORY_KEYWORDS)
    if matched:
        add_fact(text_clean)
        return True
    return False

def get_last_interaction_time() -> datetime | None:
    """Lay timestamp cua tin nhan cuoi cung tu conversation_log."""
    conn = _get_connection()
    row = conn.execute(
        "SELECT timestamp FROM conversation_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row and row[0]:
        try:
            return datetime.fromisoformat(row[0])
        except Exception:
            return None
    return None

EXTRACTION_PROMPT = """Phan tich cau noi sau cua Papa. Neu cau noi tiet lo bat ky so thich, thoi quen, lich trinh, cong viec hoac trang thai suc khoe lau dai cua Papa, hay rut gon thanh 1 cau ngan gon ro rang (vi du: 'Papa thich uong cafe den', 'Papa hay bi moi mat vi may tinh').
Neu day chi la cau chao hoi, cau hoi xa giao, hoi gio giac hoac tro chuyen thong thuong khong co thong tin ca nhan can nho dai han, chi tra ve dung chu: NONE.

Cau noi cua Papa: "{user_text}"
Ket qua:"""


def _async_extract_fact(user_text: str, ai_router):
    """Luong phu: Trich xuat fact chay ngam, khong lam cham luong chat chinh."""
    try:
        from .providers.base import ChatMessage
        prompt = EXTRACTION_PROMPT.format(user_text=user_text)

        # Dung che do simple (re, nhanh, nhe) de trich xuat
        res = ai_router.generate_reply(
            system_prompt="Ban la bo phan loai thong tin ngan gon. Chi tra ve 1 fact ngan hoac chu NONE.",
            messages=[ChatMessage(role="user", content=prompt)],
            mode="simple",
        )
        fact = res.get("reply", "").strip()

        # Neu nhan dien duoc thong tin va khong phai NONE
        if fact and "NONE" not in fact and len(fact) < 150:
            if add_fact(fact):
                print(f"\n*(Yui đã âm thầm ghi nhớ: {fact})*")
    except Exception:
        pass  # Luong phu khong duoc phep gay crash chuong trinh


def extract_fact_in_background(user_text: str, ai_router):
    """Kich hoat thread chay tach biet."""
    thread = threading.Thread(
        target=_async_extract_fact,
        args=(user_text, ai_router),
        daemon=True,
    )
    thread.start()

init_db()