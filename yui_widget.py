import sys
import logging
import threading
import requests
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit,
    QVBoxLayout, QGraphicsDropShadowEffect
)
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtCore import Qt, QPoint, QThread, pyqtSignal, QTimer

logging.basicConfig(level=logging.WARNING)

# Giữ lại module TTS cục bộ trên PC chính để phát âm thanh qua loa máy tính làm việc
from backend.voice.tts import speak_japanese_async
from backend import config, memory
from backend.chat_services import handle_chat
from backend.router import AIRouter

# Chế độ chạy lấy từ .env: YUI_MODE=local (mặc định) hoặc server
YUI_MODE = config.YUI_MODE
SERVER_URL = config.YUI_SERVER_URL

# --- LOCAL MODE: dùng chung 1 AIRouter + khởi tạo DB đúng 1 lần ---
_local_router = None
_local_lock = threading.Lock()


def _get_local_router():
    global _local_router
    with _local_lock:
        if _local_router is None:
            memory.init_db()
            _local_router = AIRouter()
        return _local_router


# --- WORKER THREAD: xử lý chat nền (local hoặc qua server) ---
class ChatWorker(QThread):
    reply_ready = pyqtSignal(str, str)

    def __init__(self, user_text: str, is_trigger: bool = False):
        super().__init__()
        self.user_text = user_text
        self.is_trigger = is_trigger

    def run(self):
        if YUI_MODE == "server":
            reply, mood = self._run_server()
        else:
            reply, mood = self._run_local()
        self.reply_ready.emit(reply, mood)

    def _run_local(self):
        try:
            result = handle_chat(
                _get_local_router(),
                self.user_text,
                is_trigger=self.is_trigger,
            )
            reply = result.get("reply", "")
            cog_data = result.get("cognitive_data") or {}
            mood = cog_data.get("mood", "happy")
            return reply, mood
        except Exception as e:
            logging.exception("Local chat failed")
            return f"Yui gặp lỗi khi xử lý ngay trên máy này ({e})", "worried"

    def _run_server(self):
        if not SERVER_URL:
            return "Chưa cấu hình YUI_SERVER_URL trong file .env ạ.", "worried"
        try:
            res = requests.post(
                f"{SERVER_URL}/chat",
                json={"message": self.user_text, "mode": "simple"},
                timeout=40,
            )
            if res.status_code == 200:
                data = res.json()
                cog_data = data.get("cognitive_data", {})
                return data.get("reply", ""), cog_data.get("mood", "happy")
            return "Server báo lỗi kết nối rồi ạ, Papa kiểm tra lại server nhé...", "worried"
        except requests.exceptions.RequestException as e:
            return f"Không kết nối được tới não bộ của Yui ({e})", "worried"


# --- CỬA SỔ 1: BONG BÓNG THOẠI & Ô CHAT (NỞ HOÀN TOÀN SANG TRÁI) ---
class ChatBubbleWindow(QWidget):
    message_sent = pyqtSignal(str)

    def __init__(self, parent_sprite):
        super().__init__()
        self.parent_sprite = parent_sprite
        self.init_ui()

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.bubble = QLabel("今日もお疲れ様でした、パパ！\n(Kyou mo otsukaresama deshita, papa!)\n-> Chào mừng papa quay trở lại ạ!")
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
        layout.addWidget(self.bubble)

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
        self.input_field.returnPressed.connect(self.on_send)
        layout.addWidget(self.input_field)

    def on_send(self):
        text = self.input_field.text().strip()
        if text:
            self.message_sent.emit(text)

    def reposition_to_sprite(self):
        """Tự động neo khung chat sang bên trái của Bé Yui."""
        self.layout().activate()
        self.adjustSize()
        sprite_geom = self.parent_sprite.geometry()
        new_x = sprite_geom.left() - self.width() + 10
        new_y = sprite_geom.bottom() - self.height() + 5
        self.move(new_x, new_y)


# --- CỬA SỔ 2: BÉ YUI (SPRITE CHỦ ĐẠO - CỐ ĐỊNH TỌA ĐỘ) ---
class YuiSpriteWindow(QWidget):
    def __init__(self, initial_text: str = None):
        super().__init__()
        self.drag_position = QPoint()
        self.chat_worker = None
        self.trigger_worker = None
        self.initial_text = initial_text

        # Trạng thái Trigger
        self.triggered_scheduled_today = set()
        self.current_date = datetime.now().date()
        self.last_interaction_time = datetime.now()

        self.init_ui()
        self.chat_window = ChatBubbleWindow(self)
        self.chat_window.message_sent.connect(self.handle_user_message)

        # Lời chào theo giờ ban đầu
        display_text = self.initial_text if self.initial_text else self.get_time_based_greeting()
        self.chat_window.bubble.setText(display_text)
        
        self.chat_window.show()
        self.chat_window.reposition_to_sprite()

        self.init_trigger_timer()

    def get_time_based_greeting(self) -> str:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "おはようございます、パパ！\n(Ohayou gozaimasu, papa!)\n-> Chào buổi sáng Papa, chúc Papa một ngày tốt lành ạ!"
        elif 12 <= hour < 18:
            return "こんにちは、パパ！\n(Konnichiwa, papa!)\n-> Chào buổi chiều Papa, công việc vẫn suôn sẻ chứ ạ?"
        else:
            return "今日もお疲れ様でした、パパ！\n(Kyou mo otsukaresama deshita, papa!)\n-> Hôm nay Papa đã vất vả nhiều rồi, nghỉ ngơi thật tốt nhé!"

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.sprite_label = QLabel()
        pixmap = QPixmap("yui_nobg_profile.png")
        scaled_pixmap = pixmap.scaled(
            170, 170,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.sprite_label.setPixmap(scaled_pixmap)
        layout.addWidget(self.sprite_label)

        # Căn vị trí góc dưới bên phải màn hình
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(screen.width() - self.width() - 20, screen.height() - self.height() - 40)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            self.chat_window.reposition_to_sprite()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.chat_window.isVisible():
                self.chat_window.hide()
            else:
                self.chat_window.show()
                self.chat_window.reposition_to_sprite()
            event.accept()

    # --- LUỒNG CHAT TƯƠNG TÁC ---
    def handle_user_message(self, text: str):
        self.chat_window.input_field.clear()
        self.last_interaction_time = datetime.now()

        exit_keywords = [
            "thoat", "thoát", "tạm biệt", "tam biet", "bye", "goodbye",
            "tạm biệt con gái", "tam biet con gai", "bye yui", "goodbye yui",
            "tạm biệt yui", "tam biet yui", "bye con gái", "bye con gai",
            "goodbye con gái", "goodbye con gai"
        ]
        if text.lower() in exit_keywords:
            self.chat_window.input_field.setEnabled(False)
            bye_msg = "また会いましょうね、パパ！\n(Mata aimashou ne, papa!)\n-> Hẹn gặp lại Papa sau nhé!"
            self.chat_window.bubble.setText(bye_msg)
            self.chat_window.reposition_to_sprite()
            
            speak_japanese_async(bye_msg, mood="caring")
            QTimer.singleShot(2500, QApplication.instance().quit)
            return

        self.chat_window.input_field.setEnabled(False)
        self.chat_window.bubble.setText("...\n(Đang suy nghĩ...)")
        self.chat_window.reposition_to_sprite()

        # Gọi sang Server PC phụ
        self.chat_worker = ChatWorker(text, is_trigger=False)
        self.chat_worker.reply_ready.connect(self.on_reply_received)
        self.chat_worker.start()

    def on_reply_received(self, reply_text: str, mood: str):
        if not self.chat_window.isVisible():
            self.chat_window.show()

        self.chat_window.bubble.setText(reply_text)
        self.chat_window.input_field.setEnabled(True)
        self.chat_window.input_field.setFocus()
        self.chat_window.reposition_to_sprite()

        # Phát giọng nói tiếng Nhật theo mood trả về
        speak_japanese_async(reply_text, mood=mood)

    # --- QUẢN LÝ TRIGGER ---
    def init_trigger_timer(self):
        self.trigger_timer = QTimer(self)
        self.trigger_timer.timeout.connect(self.check_triggers)
        self.trigger_timer.start(30000)

    def check_triggers(self):
            now = datetime.now()
            is_weekend = now.weekday() in (5, 6)

            if now.date() != self.current_date:
                self.triggered_scheduled_today.clear()
                self.current_date = now.date()

            if is_weekend:
                afternoon_desc = "Bây giờ là 5h chiều cuối tuần, hãy hỏi thăm xem Papa đã có một ngày nghỉ ngơi hoặc đi chơi thế nào rồi."
            else:
                afternoon_desc = "Bây giờ là 5h chiều tan sở, hãy chúc mừng Papa đã kết thúc một ngày làm việc vất vả và nhắc Papa thả lỏng thư giãn."

            scheduled_events = [
                {"hour": 8, "minute": 0, "name": "morning_8h", "desc": "Bây giờ là 8h sáng, hãy chủ động chào buổi sáng và chúc Papa một ngày tràn đầy năng lượng."},
                {"hour": 17, "minute": 0, "name": "work_end_17h", "desc": afternoon_desc},
                {"hour": 19, "minute": 0, "name": "dinner_20h", "desc": "Bây giờ là 8h tối, hãy nhắc Papa ăn tối đàng hoàng và đừng mải làm việc mà bỏ bữa đấy nhé."},
                {"hour": 23, "minute": 0, "name": "bedtime_23h", "desc": "Bây giờ là 11h đêm, hãy nhắc Papa thư giãn giải trí một chút rồi đi ngủ sớm để giữ gìn sức khỏe."}
            ]
            for ev in scheduled_events:
                if now.hour == ev["hour"] and now.minute == ev["minute"]:
                    if ev["name"] not in self.triggered_scheduled_today:
                        self.triggered_scheduled_today.add(ev["name"])
                        self.execute_trigger(ev["desc"])
                        return

            # Nhàn rỗi sau 4 tiếng (khung giờ hoạt động 8h - 23h)
            if 8 <= now.hour < 23:
                if now - self.last_interaction_time >= timedelta(hours=4):
                    self.last_interaction_time = now
                    self.execute_trigger("Đã khá lâu Papa không nhắn tin trò chuyện, hãy chủ động hỏi thăm Papa xem có đang bận hay mệt mỏi không.")

    def execute_trigger(self, context_desc: str):
        prompt = f"[NGU CANH TU DONG]: {context_desc}"
        self.trigger_worker = ChatWorker(prompt, is_trigger=True)
        self.trigger_worker.reply_ready.connect(self.on_trigger_replied)
        self.trigger_worker.start()

    def on_trigger_replied(self, reply_text: str, mood: str):
        if reply_text:
            if not self.chat_window.isVisible():
                self.chat_window.show()

            self.chat_window.bubble.setText(reply_text)
            self.chat_window.reposition_to_sprite()
            speak_japanese_async(reply_text, mood=mood)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    passed_text = sys.argv[1] if len(sys.argv) > 1 else None
    yui_sprite = YuiSpriteWindow(initial_text=passed_text)
    yui_sprite.show()
    sys.exit(app.exec())