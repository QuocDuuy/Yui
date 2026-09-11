"""
Module Voice Output (TTS) cho Giai đoạn Yui 2.0
- Engine: edge-tts
- Voice: ja-JP-NanamiNeural
- Bản đồ Pitch & Rate co giãn tự động theo cảm xúc (mood) chuẩn theo giọng gốc anime Yui
- Luồng phát: pygame.mixer (chạy nền, đọc toàn bộ các câu tiếng Nhật)
"""

import asyncio
import os
import threading
import pygame

YUI_VOICE = "ja-JP-NanamiNeural"
AUDIO_OUTPUT_PATH = "yui_temp_voice.mp3"

# Bản đồ âm sắc chuẩn theo giọng anime của Yui (Itou Kanae)
MOOD_CONFIG = {
    "happy": {"pitch": "+50Hz", "rate": "+5%"},      # Vui vẻ, trong sáng, tự nhiên
    "curious": {"pitch": "+52Hz", "rate": "+5%"},    # Tò mò, háo hức
    "caring": {"pitch": "+35Hz", "rate": "-2%"},     # Dịu dàng, an ủi, nhịp chậm vỗ về
    "worried": {"pitch": "+35Hz", "rate": "-2%"},    # Lo lắng chân thành khi Papa mệt
    "pouting": {"pitch": "+58Hz", "rate": "+10%"},   # Càu nhàu trẻ con, dỗi khi Papa thức khuya
}
DEFAULT_CONFIG = {"pitch": "+48Hz", "rate": "+5%"}


def extract_japanese_text(reply_text: str) -> str:
    """
    Trích xuất toàn bộ các dòng tiếng Nhật có trong phản hồi của Yui.
    Bỏ qua các dòng Romaji (...) và dòng dịch tiếng Việt (-> ...).
    """
    lines = [line.strip() for line in reply_text.strip().split("\n") if line.strip()]
    jp_lines = []

    for line in lines:
        # Bỏ qua dòng phiên âm Romaji (bắt đầu bằng '(' hoặc kết thúc bằng ')')
        if line.startswith("(") or line.endswith(")"):
            continue
        # Bỏ qua dòng dịch nghĩa tiếng Việt
        if line.startswith("->") or line.startswith("-> "):
            continue
        
        jp_lines.append(line)

    # Nối tất cả các câu tiếng Nhật lại thành một đoạn văn bản hoàn chỉnh để đọc
    return " ".join(jp_lines)


async def _generate_audio_file(text: str, mood: str, output_path: str):
    import edge_tts
    cfg = MOOD_CONFIG.get(mood, DEFAULT_CONFIG)
    communicate = edge_tts.Communicate(
        text=text,
        voice=YUI_VOICE,
        pitch=cfg["pitch"],
        rate=cfg["rate"]
    )
    await communicate.save(output_path)


def _play_audio_blocking(file_path: str):
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        pygame.mixer.music.unload()
    except Exception as e:
        print(f"[Lỗi Play Audio]: {e}")


def speak_japanese_sync(reply_text: str, mood: str = "happy"):
    jp_text = extract_japanese_text(reply_text)
    if not jp_text:
        return

    try:
        asyncio.run(_generate_audio_file(jp_text, mood, AUDIO_OUTPUT_PATH))
        _play_audio_blocking(AUDIO_OUTPUT_PATH)
    except Exception as e:
        print(f"[Lỗi TTS Voice]: {e}")


def speak_japanese_async(reply_text: str, mood: str = "happy"):
    thread = threading.Thread(
        target=speak_japanese_sync,
        args=(reply_text, mood),
        daemon=True
    )
    thread.start()