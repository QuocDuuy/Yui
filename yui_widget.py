import sys
import logging
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit,
    QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect
)
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtCore import Qt, QPoint, QThread, pyqtSignal, QTimer

# Khóa log mạng
logging.getLogger("httpx").disabled = True
logging.getLogger("httpx2").disabled = True
logging.getLogger("google_genai").setLevel(logging.WARNING)

from backend.router import AIRouter
from backend.providers.base import ChatMessage
from backend.persona import SYSTEM_PROMPT
from backend import memory

# --- WORKER THREAD: XỬ LÝ CHAT KHÔNG GÂY ĐƠ GUI ---
class ChatWorker(QThread):
    reply_ready = pyqtSignal(str)

    def __init__(self, user_text: str, ai_router: AIRouter):
        super().__init__()
        self.user_text = user_text
        self.ai_router = ai_router

    def run(self):
        # 1. Trích xuất fact tự nhiên ngầm
        if hasattr(memory, "check_and_extract_fact"):
            memory.check_and_extract_fact(self.user_text)

        # 2. Chuẩn bị prompt và gọi AI
        history = memory.get_recent_history(limit=20)
        messages = history + [ChatMessage(role="user", content=self.user_text)]
        system_prompt = memory.build_system_prompt_with_facts(SYSTEM_PROMPT)

        result = self.ai_router.generate_reply(system_prompt=system_prompt, messages=messages)
        reply = result.get("reply", "")

        # 3. Lưu lịch sử
        memory.log_message("user", self.user_text)
        memory.log_message("assistant", reply)

        self.reply_ready.emit(reply)


# --- MAIN WIDGET: CỬA SỔ HIỆN DIỆN CỦA YUI ---
class YuiWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.ai_router = AIRouter()
        self.drag_position = QPoint()
        self.chat_worker = None

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
        self.input_field.setEnabled(False)
        self.bubble.setText("...\n(Dang suy nghi...)")

        self.chat_worker = ChatWorker(text, self.ai_router)
        self.chat_worker.reply_ready.connect(self.on_reply_received)
        self.chat_worker.start()

    def on_reply_received(self, reply_text: str):
        self.bubble.setText(reply_text)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()
        # Tự động co giãn widget theo nội dung mới mà không cần kéo chuột
        self.update_bubble_geometry()

    def update_bubble_geometry(self):
        """Tự động tính toán lại kích thước và giữ cố định vị trí mép dưới của widget."""
        old_bottom = self.geometry().bottom()
        old_right = self.geometry().right()

        # Ép layout tính lại kích thước theo text mới
        self.layout().activate()
        self.adjustSize()

        # Căn chỉnh lại vị trí để widget nở dần lên trên chứ không bị tràn xuống dưới
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

        # 1. Hẹn giờ cố định
        scheduled_events = [
            {"hour": 8, "minute": 0, "name": "morning_greeting", "desc": "Bay gio la buoi sang, hay chu dong chao Papa va chuc Papa mot ngay tot lanh."},
            {"hour": 14, "minute": 0, "name": "afternoon_checkin", "desc": "Bay gio la buoi chieu, hay chu dong hoi tham xem cong viec cua Papa the nao."},
            {"hour": 21, "minute": 0, "name": "evening_checkin", "desc": "Bay gio la buoi toi, hay nhac Papa nghi ngoi that tot nhe."}
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
                            self.execute_trigger("Da kha lau Papa khong nhan tin tro chuyen, hay chu dong hoi tham Papa xem co dang ban hay met moi khong.")

    def execute_trigger(self, context_desc: str):
        history = memory.get_recent_history(limit=3)
        prompt = f"[NGU CANH TU DONG]: {context_desc}"
        messages = history + [ChatMessage(role="user", content=prompt)]
        system_prompt = memory.build_system_prompt_with_facts(SYSTEM_PROMPT)

        result = self.ai_router.generate_reply(system_prompt=system_prompt, messages=messages)
        reply = result.get("reply", "")
        if reply:
            self.bubble.setText(reply)
            self.update_bubble_geometry()  # Thêm dòng này để trigger cũng tự bung khung
            memory.log_message("assistant", reply)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = YuiWidget()
    widget.show()
    sys.exit(app.exec())