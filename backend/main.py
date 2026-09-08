"""
Backend chinh - chay bang: uvicorn backend.main:app --reload

Frontend (sau nay: nhan vat/UI) CHI duoc noi chuyen voi endpoint
/api/chat nay. Khong bao gio goi thang toi Gemini/DeepSeek/Groq tu
frontend - do la ly do API key luon nam o server-side, khong bao gio
lo ra ngoai.
"""

from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .router import AIRouter
from .providers.base import ChatMessage
from .persona import SYSTEM_PROMPT

app = FastAPI(title="AI Japanese Companion Backend")
ai_router = AIRouter()


class HistoryItem(BaseModel):
    role: str      # "user" hoac "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[HistoryItem]] = []
    mode: Optional[str] = None  # "simple" | "complex" | None (de router tu quyet dinh)


class ChatResponse(BaseModel):
    reply: str
    provider_used: str
    task_type: str


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    messages = [ChatMessage(role=h.role, content=h.content) for h in request.history]
    messages.append(ChatMessage(role="user", content=request.message))

    try:
        result = ai_router.generate_reply(
            system_prompt=SYSTEM_PROMPT,
            messages=messages,
            mode=request.mode,
        )
    except RuntimeError as e:
        # Ca 3 provider deu that bai
        raise HTTPException(status_code=503, detail=str(e))

    return ChatResponse(**result)


@app.get("/api/health")
def health():
    return {"status": "ok"}
