import sys
import logging
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit,
    QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect
)
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtCore import Qt, QPoint, QThread, pyqtSignal, QTimer

# Khóa log cảnh báo mạng để terminal sạch sẽ
logging.basicConfig(level=logging.WARNING)
for log_name in ["httpx", "httpx2", "google_genai", "httpcore"]:
    logging.getLogger(log_name).setLevel(logging.WARNING)

from backend.voice.tts import speak_japanese_async
from backend.router import AIRouter
from backend.providers.base import ChatMessage
from backend.persona import SYSTEM_PROMPT
from backend import memory


# --- WORKER THREAD: XỬ LÝ CHAT KHÔNG GÂY ĐƠ GUI ---
class ChatWorker(QThread):
    # Phát ra cả văn bản phản hồi và trạng thái cảm xúc (reply_text, mood)
    reply_ready = pyqtSignal(str, str)

    def __init__(self, user_text: str, ai_router: AIRouter, is_trigger: bool = False):
        super().__init__()
        self.user_text = user_text
        self.ai_router = ai_router
        self.is_trigger = is_trigger

    def run(self):
        if not self.is_trigger:
            if hasattr(memory, "extract_fact_in_background"):
                memory.extract_fact_in_background(self.user_text, self.ai_router)
            history = memory.get_recent_history(limit=20)
        else:
            # Luồng trigger: Chỉ lấy lịch sử ngắn để không loãng ngữ cảnh
            history = memory.get_recent_history(limit=3)

        messages = history + [ChatMessage(role="user", content=self.user_text)]
        system_prompt = memory.build_system_prompt_with_facts(SYSTEM_PROMPT)
        result = self.ai_router.generate_reply(system_prompt=system_prompt, messages=messages)
        
        reply = result.get("reply", "")
        cog_data = result.get("cognitive_data", {})
        mood = cog_data.get("mood", "happy")

        # Lưu lịch sử hội thoại
        if not self.is_trigger:
            memory.log_message("user", self.user_text)
        memory.log_message("assistant", reply)

        self.reply_ready.emit(reply, mood)


# --- MAIN WIDGET: CỬA SỔ HIỆN DIỆN CỦA YUI ---
class YuiWidget(QWidget):
    def __init__(self, initial_text: str = None):
        super().__init__()
        self.ai_router = AIRouter()
        self.drag_position = QPoint()
        self.chat_worker = None
        self.trigger_worker = None
        self.initial_text = initial_text

        # Trạng thái Trigger
        self.triggered_scheduled_today = set()
        self.current_date = datetime.now().date()
        self.last_inactivity_trigger_time = None

        self.init_ui()
        self.init_trigger_timer()

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Cột trái: Bong bóng thoại + Ô nhập liệu
        left_col = QVBoxLayout()

        # Bong bóng thoại
        default_bubble_text = "今日もお疲れ様でした、パパ！\n(Kyou mo otsukaresama deshita, papa!)\n-> Chào mừng papa quay trở lại ạ!"
        display_text = self.initial_text if self.initial_text else default_bubble_text
        
        self.bubble = QLabel(display_text)
        self.bubble.setWordWrap(True)
        self.bubble.setFixedWidth(320)
        self.bubble.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.95);
                color: #2c3e50;
                border: 2px solid #e0c3fc;
                border-radius: 12px;
                padding: 10px;
                font-family: 'Segoe UI', 'Meiryo', sans-serif;
                font-size: 13px;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(2, 2)
        self.bubble.setGraphicsEffect(shadow)
        left_col.addWidget(self.bubble)

        # Ô nhập liệu
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Nói chuyện với Yui...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.9);
                color: #2c3e50;
                border: 1.5px solid #dcdde1;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1.5px solid #8e44ad;
            }
        """)
        self.input_field.returnPressed.connect(self.on_send_message)
        left_col.addWidget(self.input_field)

        main_layout.addLayout(left_col)

        # Cột phải: Sprite Yui
        self.sprite_label = QLabel()
        pixmap = QPixmap("yui_nobg_profile.png")
        scaled_pixmap = pixmap.scaled(
            170, 170,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.sprite_label.setPixmap(scaled_pixmap)
        main_layout.addWidget(self.sprite_label)

        # Căn vị trí góc dưới bên phải màn hình
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(screen.width() - self.width() - 30, screen.height() - self.height() - 40)

    # --- KÉO THẢ DI CHUYỂN BẰNG CHUỘT ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    # --- LUỒNG CHAT TƯƠNG TÁC ---
    def on_send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()

        # 1. Kiểm tra từ khóa thoát / tạm biệt
        exit_keywords = [
            "thoat", "thoát", "tạm biệt", "tam biet", "bye", "goodbye",
            "tạm biệt con gái", "tam biet con gai", "bye yui", "goodbye yui",
            "tạm biệt yui", "tam biet yui", "bye con gái", "bye con gai",
            "goodbye con gái", "goodbye con gai"
        ]
        if text.lower() in exit_keywords:
            self.input_field.setEnabled(False)
            bye_msg = "また会いましょうね、パパ！\n(Mata aimashou ne, papa!)\n-> Hẹn gặp lại Papa sau nhé!"
            self.bubble.setText(bye_msg)
            self.update_bubble_geometry()
            
            # Yui nói câu chào tạm biệt bằng âm sắc dịu dàng
            speak_japanese_async(bye_msg, mood="caring")
            
            # Đợi 2.5 giây cho Yui nói xong rồi tự thoát
            QTimer.singleShot(2500, self.close)
            return

        # 2. Luồng chat thông thường
        self.input_field.setEnabled(False)
        self.bubble.setText("...\n(Dang suy nghi...)")

        self.chat_worker = ChatWorker(text, self.ai_router, is_trigger=False)
        self.chat_worker.reply_ready.connect(self.on_reply_received)
        self.chat_worker.start()

    def on_reply_received(self, reply_text: str, mood: str):
        self.bubble.setText(reply_text)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()
        self.update_bubble_geometry()

        # Phát giọng nói tiếng Nhật co giãn theo cảm xúc (Edge-TTS)
        speak_japanese_async(reply_text, mood=mood)

    def update_bubble_geometry(self):
        """Tự động tính toán lại kích thước và giữ cố định vị trí mép dưới của widget."""
        old_bottom = self.geometry().bottom()
        old_right = self.geometry().right()

        self.layout().activate()
        self.adjustSize()

        new_height = self.height()
        new_width = self.width()
        self.move(old_right - new_width, old_bottom - new_height)
        self.update()

    # --- QUẢN LÝ TRIGGER TỰ ĐỘNG ---
    def init_trigger_timer(self):
        self.trigger_timer = QTimer(self)
        self.trigger_timer.timeout.connect(self.check_triggers)
        self.trigger_timer.start(30000)  # Rà soát mỗi 30 giây

    def check_triggers(self):
            now = datetime.now()

            # Reset cờ theo ngày mới
            if now.date() != self.current_date:
                self.triggered_scheduled_today.clear()
                self.current_date = now.date()

            # 1. Hẹn giờ cố định (Đã nâng cấp Context Continuity cho buổi sáng)
            last_context = memory.get_last_session_context() if hasattr(memory, "get_last_session_context") else None
            context_hint = f" (Ngữ cảnh tối hôm trước Papa từng nói: '{last_context}'). Hãy hỏi thăm tiếp mạch nếu phù hợp." if last_context else ""

            scheduled_events = [
                {
                    "hour": 8, 
                    "minute": 0, 
                    "name": "morning_greeting", 
                    "desc": f"Bây giờ là buổi sáng, hãy chủ động chào Papa và chúc Papa một ngày tốt lành.{context_hint}"
                },
                {
                    "hour": 14, 
                    "minute": 0, 
                    "name": "afternoon_checkin", 
                    "desc": "Bây giờ là buổi chiều, hãy chủ động hỏi thăm xem công việc của Papa thế nào."
                },
                {
                    "hour": 21, 
                    "minute": 0, 
                    "name": "evening_checkin", 
                    "desc": "Bây giờ là buổi tối, hãy nhắc Papa nghỉ ngơi thật tốt nhé."
                }
            ]
            for ev in scheduled_events:
                if now.hour == ev["hour"] and now.minute == ev["minute"]:
                    if ev["name"] not in self.triggered_scheduled_today:
                        self.triggered_scheduled_today.add(ev["name"])
                        self.execute_trigger(ev["desc"])
                        return

            # 2. Kiểm tra nhàn rỗi (8h - 21h, sau 4 tiếng)
            if 8 <= now.hour < 21:
                if hasattr(memory, "get_last_interaction_time"):
                    last_time = memory.get_last_interaction_time()
                    if last_time:
                        if self.last_inactivity_trigger_time is None or (now - self.last_inactivity_trigger_time >= timedelta(hours=4)):
                            if now - last_time >= timedelta(hours=4):
                                self.last_inactivity_trigger_time = now
                                self.execute_trigger("Đã khá lâu Papa không nhắn tin trò chuyện, hãy chủ động hỏi thăm Papa xem có đang bận hay mệt mỏi không.")

    def execute_trigger(self, context_desc: str):
        prompt = f"[NGU CANH TU DONG]: {context_desc}"
        
        self.trigger_worker = ChatWorker(prompt, self.ai_router, is_trigger=True)
        self.trigger_worker.reply_ready.connect(self.on_trigger_replied)
        self.trigger_worker.start()

    def on_trigger_replied(self, reply_text: str, mood: str):
        if reply_text:
            self.bubble.setText(reply_text)
            self.update_bubble_geometry()
            speak_japanese_async(reply_text, mood=mood)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Lấy text truyền từ notification nếu có
    passed_text = sys.argv[1] if len(sys.argv) > 1 else None
    
    widget = YuiWidget(initial_text=passed_text)
    widget.show()
    
    # Nếu có text truyền vào, ép cập nhật kích thước bong bóng cho vừa vặn
    if passed_text:
        widget.update_bubble_geometry()
        
    sys.exit(app.exec())