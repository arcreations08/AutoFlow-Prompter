import sys
import os
import re
import json
import socket
import threading
import webbrowser
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QLineEdit, QFileDialog,
    QProgressBar, QSpinBox, QGroupBox, QSplitter, QMessageBox, QFrame,
    QRadioButton, QButtonGroup, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QObject, QThread, QTimer, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor, QPainter, QPixmap

from bot_engine import GoogleFlowBot, is_port_in_use
import license_manager

if getattr(sys, 'frozen', False):
    CURRENT_DIR = Path(sys.executable).parent.resolve()
else:
    CURRENT_DIR = Path(__file__).parent.resolve()
DEFAULT_OUTPUT_DIR = CURRENT_DIR / "Generated_Images"
CONFIG_FILE = CURRENT_DIR / "profiles_config.json"
BG_ASSET_PATH = CURRENT_DIR / "assets" / "background.jpg"
INSTAGRAM_ICON_PATH = CURRENT_DIR / "assets" / "instagram.png"
INSTAGRAM_URL = "https://www.instagram.com/arcreations008/?utm_source=chatgpt.com"

DEFAULT_PROFILES = {
    1: {"name": "Profile 1", "port": 9222, "dir": "chrome_profile", "default_label": "Gmail Profile 1 (Primary)"},
    2: {"name": "Profile 2", "port": 9223, "dir": "chrome_profile_2", "default_label": "Gmail Profile 2"},
    3: {"name": "Profile 3", "port": 9224, "dir": "chrome_profile_3", "default_label": "Gmail Profile 3"}
}

def load_profiles_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "1": {"label": "Gmail Profile 1 (Primary)"},
        "2": {"label": "Gmail Profile 2"},
        "3": {"label": "Gmail Profile 3"}
    }

def save_profiles_config(data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        process = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if process != 0:
            kernel32.CloseHandle(process)
            return True
        return False
    except Exception:
        return False

def get_profile_lock_owner(profile_id: int) -> int:
    """Returns the PID of the active process holding this profile lock, or 0 if free."""
    lock_file = CURRENT_DIR / f".app_profile_{profile_id}.lock"
    if lock_file.exists():
        try:
            with open(lock_file, "r") as f:
                content = f.read().strip()
            if content.isdigit():
                pid = int(content)
                if is_pid_alive(pid):
                    return pid
                else:
                    lock_file.unlink(missing_ok=True)
        except Exception:
            pass
    return 0

def is_profile_in_use(profile_id: int) -> bool:
    """Checks if a profile is currently in use either by an app instance or active Chrome CDP port."""
    owner = get_profile_lock_owner(profile_id)
    if owner > 0 and owner != os.getpid():
        return True
    port = DEFAULT_PROFILES[profile_id]["port"]
    if is_port_in_use(port):
        return True
    return False

def acquire_profile_lock(profile_id: int):
    lock_file = CURRENT_DIR / f".app_profile_{profile_id}.lock"
    try:
        with open(lock_file, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

def release_profile_lock(profile_id: int):
    lock_file = CURRENT_DIR / f".app_profile_{profile_id}.lock"
    try:
        if lock_file.exists():
            with open(lock_file, "r") as f:
                pid = int(f.read().strip())
            if pid == os.getpid():
                lock_file.unlink(missing_ok=True)
    except Exception:
        pass

def parse_prompts_intelligently(text):
    raw = text.strip()
    if not raw:
        return []

    # Check for numbered/timed prompts like "1) ", "2. ", "(01-0:4)", "01-0:4", "[01-0:4]"
    numbered_split = re.split(r'(?:\r?\n)+(?=\s*(?:[\[\(]?\s*\d+[\s\-_]+\d+[:\-_.]|\d+[\)\.\:]\s+))', raw)
    if len(numbered_split) > 1:
        clean_list = [p.strip() for p in numbered_split if p.strip()]
        return clean_list

    # Check for blank lines between paragraphs
    paragraph_split = re.split(r'(?:\r?\n){2,}', raw)
    if len(paragraph_split) > 1:
        clean_list = [p.strip() for p in paragraph_split if p.strip()]
        return clean_list

    # Fallback to single line split
    lines = [p.strip() for p in raw.splitlines() if p.strip()]
    return lines

# =========================================================================
# CINEMATIC GLASSMORPHISM BACKGROUND & ANIMATED WIDGETS
# =========================================================================

class GlassCentralWidget(QWidget):
    """
    Renders the background artwork seamlessly across the window with a 
    subtle dark glassmorphism tint for crystal clear readability.
    """
    def __init__(self, bg_path, parent=None):
        super().__init__(parent)
        self.bg_pixmap = QPixmap(str(bg_path)) if Path(bg_path).exists() else QPixmap()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if self.bg_pixmap and not self.bg_pixmap.isNull():
            scaled = self.bg_pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            # Subtle glass tint overlay to ensure sharp UI contrast
            painter.fillRect(self.rect(), QColor(10, 12, 22, 100))
        else:
            painter.fillRect(self.rect(), QColor(14, 16, 26))
        super().paintEvent(event)


class InstagramLinkWidget(QWidget):
    """
    Clickable Instagram badge with icon and username.
    Opens user's Instagram profile in default browser on click.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Open Instagram: @arcreations008")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(6)

        self.icon_lbl = QLabel()
        if INSTAGRAM_ICON_PATH.exists():
            pixmap = QPixmap(str(INSTAGRAM_ICON_PATH)).scaled(
                16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.icon_lbl.setPixmap(pixmap)
        else:
            self.icon_lbl.setText("📷")
            self.icon_lbl.setFont(QFont("Segoe UI Emoji", 11))
        self.icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.icon_lbl)

        self.text_lbl = QLabel("@arcreations008")
        self.text_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.text_lbl.setStyleSheet("color: #fb7185; letter-spacing: 0.3px;")
        self.text_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.text_lbl)

        layout.addStretch()

    def enterEvent(self, event):
        self.text_lbl.setStyleSheet("color: #ffffff; text-decoration: underline; letter-spacing: 0.3px;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.text_lbl.setStyleSheet("color: #fb7185; text-decoration: none; letter-spacing: 0.3px;")
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            webbrowser.open(INSTAGRAM_URL)
        super().mousePressEvent(event)


class GlowButton(QPushButton):
    """
    Modern Glassmorphism button equipped with:
    - Smooth hover glow via QGraphicsDropShadowEffect
    - Smooth press-down tactile micro-feedback
    - Ambient breathing pulse during generation / active state
    """
    def __init__(self, text="", glow_color="#e11d48", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.glow_color = QColor(glow_color)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setColor(self.glow_color)
        self.shadow.setOffset(0, 0)
        self.shadow.setBlurRadius(0)
        self.setGraphicsEffect(self.shadow)

        # Hover Animation
        self.hover_anim = QPropertyAnimation(self.shadow, b"blurRadius")
        self.hover_anim.setDuration(160)
        self.hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Ambient Breathing Pulse
        self.pulse_anim = QPropertyAnimation(self.shadow, b"blurRadius")
        self.pulse_anim.setDuration(900)
        self.pulse_anim.setStartValue(10)
        self.pulse_anim.setEndValue(28)
        self.pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
        self.pulse_anim.setLoopCount(-1)

    def enterEvent(self, event):
        if self.isEnabled() and self.pulse_anim.state() != QPropertyAnimation.Running:
            self.hover_anim.stop()
            self.hover_anim.setStartValue(self.shadow.blurRadius())
            self.hover_anim.setEndValue(24)
            self.hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.pulse_anim.state() != QPropertyAnimation.Running:
            self.hover_anim.stop()
            self.hover_anim.setStartValue(self.shadow.blurRadius())
            self.hover_anim.setEndValue(0)
            self.hover_anim.start()
        super().leaveEvent(event)

    def start_pulse(self):
        self.hover_anim.stop()
        self.pulse_anim.start()

    def stop_pulse(self):
        self.pulse_anim.stop()
        self.shadow.setBlurRadius(0)


class AnimatedProgressBar(QProgressBar):
    """
    Smoothly interpolating glassmorphism progress bar.
    Eliminates abrupt jumping; smoothly glides from value to value.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._animated_val = 0
        self.anim = QPropertyAnimation(self, b"animatedValue")
        self.anim.setDuration(320)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    @Property(int)
    def animatedValue(self):
        return self._animated_val

    @animatedValue.setter
    def animatedValue(self, val):
        self._animated_val = val
        super().setValue(val)

    def setSmoothValue(self, val):
        self.anim.stop()
        self.anim.setStartValue(self._animated_val)
        self.anim.setEndValue(val)
        self.anim.start()


class PulsingStatusBadge(QLabel):
    """
    Status badge with a gentle breathing ambient glow when active.
    """
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setColor(QColor("#10b981"))
        self.shadow.setOffset(0, 0)
        self.shadow.setBlurRadius(0)
        self.setGraphicsEffect(self.shadow)

        self.pulse_anim = QPropertyAnimation(self.shadow, b"blurRadius")
        self.pulse_anim.setDuration(1200)
        self.pulse_anim.setStartValue(2)
        self.pulse_anim.setEndValue(16)
        self.pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
        self.pulse_anim.setLoopCount(-1)

    def setActive(self, is_active, color="#10b981"):
        self.shadow.setColor(QColor(color))
        if is_active:
            if self.pulse_anim.state() != QPropertyAnimation.Running:
                self.pulse_anim.start()
        else:
            self.pulse_anim.stop()
            self.shadow.setBlurRadius(0)

# =========================================================================
# WORKER & LOGIC
# =========================================================================

class WorkerSignals(QObject):
    log = Signal(str)
    progress = Signal(int, int)
    finished = Signal()

class BotWorker(QThread):
    def __init__(self, bot, prompts, target_url, delay, timeout, char_tag):
        super().__init__()
        self.bot = bot
        self.prompts = prompts
        self.target_url = target_url
        self.delay = delay
        self.timeout = timeout
        self.char_tag = char_tag
        self.signals = WorkerSignals()

        self.bot.log_callback = lambda msg: self.signals.log.emit(msg)
        self.bot.progress_callback = lambda cur, tot: self.signals.progress.emit(cur, tot)

    def run(self):
        self.bot.run_batch(
            self.prompts,
            target_url=self.target_url,
            delay_seconds=self.delay,
            timeout_per_image=self.timeout,
            character_tag=self.char_tag
        )
        self.signals.finished.emit()

class MainWindow(QMainWindow):
    def __init__(self, requested_profile=None, license_result=None):
        super().__init__()
        self.config_data = load_profiles_config()
        self.worker = None
        self.license_result = license_result

        # Auto-detect profile if not explicitly requested
        auto_switched = False
        if requested_profile in (1, 2, 3) and (get_profile_lock_owner(requested_profile) == 0 or get_profile_lock_owner(requested_profile) == os.getpid()):
            self.current_profile_id = requested_profile
        else:
            if not is_profile_in_use(1):
                self.current_profile_id = 1
            elif not is_profile_in_use(2):
                self.current_profile_id = 2
                auto_switched = True
            elif not is_profile_in_use(3):
                self.current_profile_id = 3
                auto_switched = True
            else:
                free_pid = None
                for p in (1, 2, 3):
                    if get_profile_lock_owner(p) == 0:
                        free_pid = p
                        break
                self.current_profile_id = free_pid if free_pid else 1
                auto_switched = True

        acquire_profile_lock(self.current_profile_id)

        self.resize(1240, 840)
        self.setup_ui()
        self.init_bot_for_current_profile()
        self.apply_reference_glassmorphism_theme()
        self.update_active_profile_banner()
        self.update_window_title()

        if self.license_result:
            if self.license_result.message:
                self.append_log(f"🔑 License: {self.license_result.message}")
            if self.license_result.update_available:
                self.append_log(
                    f"🌟 NEW UPDATE AVAILABLE! Version {self.license_result.latest_version} is out.\n"
                    f"👉 Check updates: {self.license_result.update_url}"
                )

        if auto_switched and self.current_profile_id > 1:
            self.append_log(
                f"ℹ️ Profile 1 is in use. Auto-selected Profile {self.current_profile_id} "
                f"({self.get_profile_label(self.current_profile_id)}) on Port {self.get_profile_port(self.current_profile_id)}."
            )

        # Periodic status refresh
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_profile_statuses)
        self.status_timer.start(2500)
        self.refresh_profile_statuses()

    def closeEvent(self, event):
        release_profile_lock(self.current_profile_id)
        if self.worker and self.worker.isRunning():
            self.bot.stop()
            self.worker.wait(1500)
        event.accept()

    def get_profile_dir(self, pid):
        return CURRENT_DIR / DEFAULT_PROFILES[pid]["dir"]

    def get_profile_port(self, pid):
        return DEFAULT_PROFILES[pid]["port"]

    def get_profile_label(self, pid):
        return self.config_data.get(str(pid), {}).get("label", DEFAULT_PROFILES[pid]["default_label"])

    def init_bot_for_current_profile(self):
        p_dir = self.get_profile_dir(self.current_profile_id)
        p_port = self.get_profile_port(self.current_profile_id)
        p_label = self.get_profile_label(self.current_profile_id)
        out_dir = Path(self.input_folder.text().strip()) if hasattr(self, 'input_folder') else DEFAULT_OUTPUT_DIR
        self.bot = GoogleFlowBot(
            profile_dir=p_dir,
            output_dir=out_dir,
            profile_id=self.current_profile_id,
            cdp_port=p_port,
            profile_label=p_label,
            log_callback=self.append_log,
            progress_callback=self.update_progress
        )

    def setup_ui(self):
        # 1. Background Glass Central Widget (Renders exact visual artwork with glass tint)
        central_widget = GlassCentralWidget(BG_ASSET_PATH, self)
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(18, 14, 18, 14)

        # 2. Header Row (Glass Card on Left, Glowing Profile Pill on Right)
        header_row = QHBoxLayout()
        header_row.setSpacing(14)

        # Left Header Card
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(16, 10, 20, 10)
        h_layout.setSpacing(14)

        shield_lbl = QLabel("🛡️")
        shield_lbl.setFont(QFont("Segoe UI Emoji", 20))
        h_layout.addWidget(shield_lbl)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_label = QLabel("ARCreations")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title_label.setStyleSheet("color: #ffffff; letter-spacing: 0.5px;")

        self.instagram_link = InstagramLinkWidget()
        title_box.addWidget(title_label)
        title_box.addWidget(self.instagram_link)
        h_layout.addLayout(title_box)
        h_layout.addStretch()
        header_row.addWidget(header_card, 3)

        # Right Header Glowing Profile Card
        self.header_profile_card = QFrame()
        self.header_profile_card.setObjectName("headerProfileCard")
        hp_layout = QHBoxLayout(self.header_profile_card)
        hp_layout.setContentsMargins(16, 10, 16, 10)
        hp_layout.setSpacing(10)

        self.lbl_header_profile = QLabel()
        self.lbl_header_profile.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.lbl_header_profile.setStyleSheet("color: #ffffff;")
        hp_layout.addWidget(self.lbl_header_profile)
        header_row.addWidget(self.header_profile_card, 1)

        main_layout.addLayout(header_row)

        # 3. Main Split Workspace (Left Prompts, Right Side Panels)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        # --- LEFT PANEL: PROMPTS WORKSPACE ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        prompt_grp = QGroupBox("📝  PROMPTS WORKSPACE")
        prompt_grp_layout = QVBoxLayout(prompt_grp)
        prompt_grp_layout.setContentsMargins(14, 16, 14, 14)
        prompt_grp_layout.setSpacing(10)

        self.txt_prompts = QTextEdit()
        self.txt_prompts.setObjectName("txtPrompts")
        self.txt_prompts.setPlaceholderText(
            "Paste your prompts here:\n\n"
            "(01-0:4) A cinematic wide shot of ancient river sorting bronze sediment...\n\n"
            "(02-0:4) Early craftsmen discovering tin grains in warm glowing sand...\n\n"
            "(03-0:8) Smelting copper and tin together to forge mythical blade..."
        )
        self.txt_prompts.setFont(QFont("Consolas", 10))
        self.txt_prompts.textChanged.connect(self.update_prompt_count)
        prompt_grp_layout.addWidget(self.txt_prompts)

        # Prompts Action Bar
        p_bar = QHBoxLayout()
        self.lbl_count = QLabel("Prompts Detected: 0")
        self.lbl_count.setStyleSheet("font-weight: 800; color: #f43f5e; font-size: 13px;")
        p_bar.addWidget(self.lbl_count)
        p_bar.addStretch()

        btn_load_txt = GlowButton("📂 Load .txt File", glow_color="#38bdf8")
        btn_load_txt.clicked.connect(self.load_prompts_file)
        btn_load_txt.setStyleSheet("background: rgba(18, 22, 36, 0.85); border: 1.2px solid rgba(255, 255, 255, 0.16); border-radius: 8px; padding: 6px 16px; color: #ffffff; font-weight: 600;")
        p_bar.addWidget(btn_load_txt)

        btn_clear = GlowButton("🗑 Clear", glow_color="#f43f5e")
        btn_clear.clicked.connect(lambda: self.txt_prompts.clear())
        btn_clear.setStyleSheet("background: rgba(28, 14, 22, 0.85); border: 1.2px solid rgba(244, 63, 94, 0.35); border-radius: 8px; padding: 6px 16px; color: #fda4af; font-weight: 600;")
        p_bar.addWidget(btn_clear)
        prompt_grp_layout.addLayout(p_bar)

        left_layout.addWidget(prompt_grp)
        splitter.addWidget(left_widget)

        # --- RIGHT SIDE PANEL: 3 CARDS ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        # Card 1: Profile & Account Selection
        profile_grp = QGroupBox("👤  PROFILE  GMAIL SELECTION (SIDE PANEL)")
        profile_grp_layout = QVBoxLayout(profile_grp)
        profile_grp_layout.setContentsMargins(14, 16, 14, 14)
        profile_grp_layout.setSpacing(10)

        p_top = QHBoxLayout()
        lbl_p_title = QLabel("Select Profile:")
        lbl_p_title.setStyleSheet("font-weight: 700; color: #cbd5e1;")
        p_top.addWidget(lbl_p_title)
        
        self.profile_group = QButtonGroup(self)
        self.profile_radios = {}
        for pid in (1, 2, 3):
            radio = QRadioButton(f"Profile {pid}")
            radio.setFont(QFont("Segoe UI", 9, QFont.Bold))
            if pid == self.current_profile_id:
                radio.setChecked(True)
            self.profile_group.addButton(radio, pid)
            self.profile_radios[pid] = radio
            p_top.addWidget(radio)

        self.profile_group.idClicked.connect(self.on_profile_selected)
        p_top.addStretch()

        self.lbl_profile_status = PulsingStatusBadge("⚪ Port 9222 (Offline)")
        self.lbl_profile_status.setStyleSheet("color: #cbd5e1; font-size: 11px; font-weight: 600;")
        p_top.addWidget(self.lbl_profile_status)
        profile_grp_layout.addLayout(p_top)

        p_row = QHBoxLayout()
        lbl_gmail = QLabel("Gmail:")
        lbl_gmail.setStyleSheet("font-weight: 700; color: #cbd5e1;")
        p_row.addWidget(lbl_gmail)
        self.input_gmail = QLineEdit(self.get_profile_label(self.current_profile_id))
        self.input_gmail.setPlaceholderText("e.g. user@gmail.com")
        self.input_gmail.textChanged.connect(self.on_gmail_label_changed)
        p_row.addWidget(self.input_gmail, 2)

        self.btn_login = GlowButton(f"▶ Launch (P{self.current_profile_id})", glow_color="#0ea5e9")
        self.btn_login.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.btn_login.clicked.connect(self.launch_chrome_browser)
        self.btn_login.setStyleSheet(
            "background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0ea5e9); "
            "color: white; padding: 7px 18px; border-radius: 8px; border: 1.2px solid rgba(255, 255, 255, 0.3);"
        )
        p_row.addWidget(self.btn_login, 1)
        profile_grp_layout.addLayout(p_row)

        right_layout.addWidget(profile_grp)

        # Card 2: Automation Settings & Safety
        settings_grp = QGroupBox("⚙️  AUTOMATION SETTINGS  SAFETY")
        settings_layout = QVBoxLayout(settings_grp)
        settings_layout.setContentsMargins(14, 16, 14, 14)
        settings_layout.setSpacing(10)

        # Save Location
        folder_layout = QHBoxLayout()
        lbl_save = QLabel("Save Images To:")
        lbl_save.setStyleSheet("font-weight: 700; color: #cbd5e1;")
        folder_layout.addWidget(lbl_save)
        default_p_out = DEFAULT_OUTPUT_DIR / f"Profile_{self.current_profile_id}"
        default_p_out.mkdir(parents=True, exist_ok=True)
        self.input_folder = QLineEdit(str(default_p_out))
        self.input_folder.setReadOnly(True)
        folder_layout.addWidget(self.input_folder)
        btn_browse = GlowButton("📁 Browse", glow_color="#38bdf8")
        btn_browse.clicked.connect(self.browse_folder)
        btn_browse.setStyleSheet("background: rgba(18, 22, 36, 0.85); border: 1.2px solid rgba(255, 255, 255, 0.16); border-radius: 8px; padding: 6px 16px; color: #ffffff; font-weight: 600;")
        folder_layout.addWidget(btn_browse)
        settings_layout.addLayout(folder_layout)

        # Character / Tag
        char_layout = QHBoxLayout()
        lbl_char = QLabel("Character Tag:")
        lbl_char.setStyleSheet("font-weight: 700; color: #cbd5e1;")
        char_layout.addWidget(lbl_char)
        self.input_char = QLineEdit("")
        self.input_char.setPlaceholderText("e.g. @Character 1 (optional consistency tag)")
        char_layout.addWidget(self.input_char)
        settings_layout.addLayout(char_layout)

        # Timings Row
        time_layout = QHBoxLayout()
        lbl_w = QLabel("Wait per Image:")
        lbl_w.setStyleSheet("font-weight: 700; color: #cbd5e1;")
        time_layout.addWidget(lbl_w)
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(25, 240)
        self.spin_timeout.setValue(80)
        time_layout.addWidget(self.spin_timeout)

        time_layout.addSpacing(18)
        lbl_d = QLabel("Safe Delay:")
        lbl_d.setStyleSheet("font-weight: 700; color: #cbd5e1;")
        time_layout.addWidget(lbl_d)
        self.spin_delay = QSpinBox()
        self.spin_delay.setRange(4, 60)
        self.spin_delay.setValue(8)
        time_layout.addWidget(self.spin_delay)
        time_layout.addStretch()
        settings_layout.addLayout(time_layout)

        # Safety Banner
        safety_lbl = QLabel("🛡️ Account Protection: Direct DOM injection & natural cooldowns. Isolated browser profile & ports.")
        safety_lbl.setStyleSheet("color: #34d399; font-size: 11px; font-weight: 600; padding: 2px;")
        safety_lbl.setWordWrap(True)
        settings_layout.addWidget(safety_lbl)

        right_layout.addWidget(settings_grp)

        # Card 3: Live Activity Terminal
        log_grp = QGroupBox("📋  LIVE ACTIVITY TERMINAL")
        log_layout = QVBoxLayout(log_grp)
        log_layout.setContentsMargins(14, 16, 14, 14)

        self.txt_log = QTextEdit()
        self.txt_log.setObjectName("txtLog")
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas", 9))
        self.txt_log.setStyleSheet(
            "background-color: rgba(6, 8, 16, 0.78); color: #34d399; "
            "border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 8px;"
        )
        log_layout.addWidget(self.txt_log)
        right_layout.addWidget(log_grp)

        splitter.addWidget(right_widget)
        splitter.setSizes([540, 640])
        main_layout.addWidget(splitter)

        # 4. Progress Bar & Action Controls (Glassmorphism Footer Bar)
        bottom_bar = QFrame()
        bottom_bar.setObjectName("bottomBar")
        bottom_layout = QVBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(18, 12, 18, 12)
        bottom_layout.setSpacing(10)

        self.progress_bar = AnimatedProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Ready (%p%)")
        bottom_layout.addWidget(self.progress_bar)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_start = GlowButton("🚀 Start Batch Generation", glow_color="#f43f5e")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.btn_start.setStyleSheet(
            "background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #9f1239, stop:0.5 #e11d48, stop:1 #fb7185); "
            "color: white; padding: 12px; border-radius: 10px; border: 1.5px solid rgba(255, 255, 255, 0.25);"
        )
        self.btn_start.clicked.connect(self.start_batch)
        btn_row.addWidget(self.btn_start, 3)

        self.btn_pause = GlowButton("⏸ Pause", glow_color="#f59e0b")
        self.btn_pause.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_pause.setEnabled(False)
        self.btn_pause.setStyleSheet(
            "background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #b45309, stop:1 #f59e0b); "
            "color: white; padding: 10px; border-radius: 10px; border: 1.5px solid rgba(255, 255, 255, 0.2);"
        )
        self.btn_pause.clicked.connect(self.toggle_pause)
        btn_row.addWidget(self.btn_pause, 1)

        self.btn_stop = GlowButton("⏹ Stop", glow_color="#be123c")
        self.btn_stop.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            "background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #881337, stop:1 #be123c); "
            "color: white; padding: 10px; border-radius: 10px; border: 1.5px solid rgba(255, 255, 255, 0.2);"
        )
        self.btn_stop.clicked.connect(self.stop_batch)
        btn_row.addWidget(self.btn_stop, 1)

        bottom_layout.addLayout(btn_row)
        main_layout.addWidget(bottom_bar)

        self.append_log("✨ Ready! Select your profile on the right panel, open Chrome, then click 'Start Batch Generation'.")

    def on_profile_selected(self, pid):
        if pid == self.current_profile_id:
            return

        owner = get_profile_lock_owner(pid)
        if owner > 0 and owner != os.getpid():
            QMessageBox.warning(
                self,
                "Profile Locked",
                f"⚠️ Profile {pid} is strictly locked to another active window (Process ID {owner}).\n\n"
                f"Each window must strictly run its own assigned profile to prevent batch conflicts."
            )
            self.profile_radios[self.current_profile_id].setChecked(True)
            return

        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Batch Running", "A batch generation is currently running on this profile. Please wait or stop it before switching.")
            self.profile_radios[self.current_profile_id].setChecked(True)
            return

        release_profile_lock(self.current_profile_id)
        self.current_profile_id = pid
        acquire_profile_lock(self.current_profile_id)

        # Strictly update dedicated output folder for this profile
        profile_out = DEFAULT_OUTPUT_DIR / f"Profile_{pid}"
        profile_out.mkdir(parents=True, exist_ok=True)
        self.input_folder.setText(str(profile_out))

        self.init_bot_for_current_profile()
        self.input_gmail.blockSignals(True)
        self.input_gmail.setText(self.get_profile_label(pid))
        self.input_gmail.blockSignals(False)

        self.update_active_profile_banner()
        self.update_window_title()
        self.append_log(f"🔄 Switched active target strictly to Profile {pid} ({self.get_profile_label(pid)}) [Port {self.get_profile_port(pid)}]")

    def on_gmail_label_changed(self):
        new_label = self.input_gmail.text().strip()
        str_id = str(self.current_profile_id)
        if str_id not in self.config_data:
            self.config_data[str_id] = {}
        self.config_data[str_id]["label"] = new_label
        save_profiles_config(self.config_data)

        self.bot.profile_label = new_label
        self.update_active_profile_banner()
        self.update_window_title()

    def update_window_title(self):
        pid = self.current_profile_id
        label = self.get_profile_label(pid)
        port = self.get_profile_port(pid)
        self.setWindowTitle(f"Google Flow Auto-Prompter — Profile {pid}: {label} (Port {port})")

    def update_active_profile_banner(self):
        pid = self.current_profile_id
        label = self.get_profile_label(pid)
        port = self.get_profile_port(pid)
        if hasattr(self, 'lbl_header_profile'):
            self.lbl_header_profile.setText(f"🎯 Profile {pid} ({label}) | Port: {port}")
        if hasattr(self, 'btn_login'):
            self.btn_login.setText(f"▶ Launch (P{pid})")
        self.btn_start.setText(f"🚀 Start Batch Generation (Profile {pid})")

    def refresh_profile_statuses(self):
        for pid in (1, 2, 3):
            owner = get_profile_lock_owner(pid)
            radio = self.profile_radios.get(pid)
            if owner > 0 and owner != os.getpid():
                if radio and not radio.isChecked():
                    radio.setEnabled(False)
                    radio.setText(f"P{pid} 🔒")
            else:
                if radio:
                    radio.setEnabled(True)
                    radio.setText(f"Profile {pid}")

        # Update status badge in side panel
        cur_port = DEFAULT_PROFILES[self.current_profile_id]["port"]
        cur_active = is_port_in_use(cur_port)
        if hasattr(self, 'lbl_profile_status'):
            if cur_active:
                self.lbl_profile_status.setText(f"🟢 Port {cur_port} (Active)")
                self.lbl_profile_status.setStyleSheet("color: #34d399; font-size: 11px; font-weight: bold;")
                self.lbl_profile_status.setActive(True, color="#10b981")
            else:
                self.lbl_profile_status.setText(f"⚪ Port {cur_port} (Offline)")
                self.lbl_profile_status.setStyleSheet("color: #cbd5e1; font-size: 11px;")
                self.lbl_profile_status.setActive(False)

    def update_prompt_count(self):
        prompts = parse_prompts_intelligently(self.txt_prompts.toPlainText())
        self.lbl_count.setText(f"Prompts Detected: {len(prompts)}")

    def load_prompts_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Prompts File", "", "Text Files (*.txt);;All Files (*.*)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.txt_prompts.setPlainText(content)
                self.append_log(f"Loaded prompts file: {path}")
            except Exception as e:
                self.append_log(f"Error reading file: {e}")

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.input_folder.text())
        if folder:
            self.input_folder.setText(folder)
            self.bot.output_dir = Path(folder)
            self.append_log(f"Output folder updated: {folder}")

    def append_log(self, message):
        self.txt_log.append(message)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def update_progress(self, current, total):
        pct = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setSmoothValue(pct)
        self.progress_bar.setFormat(f"Processing {current} / {total} ({pct}%)")

    def launch_chrome_browser(self):
        pid = self.current_profile_id
        label = self.get_profile_label(pid)
        self.append_log(f"🌐 Launching Chrome for Profile {pid} ({label}) on port {self.bot.cdp_port}...")
        threading.Thread(target=self.bot.launch_browser, args=("https://flow.google.com",), daemon=True).start()

    def start_batch(self):
        prompts = parse_prompts_intelligently(self.txt_prompts.toPlainText())
        if not prompts:
            QMessageBox.warning(self, "No Prompts", "Please enter or paste at least one prompt in the prompts box!")
            return

        self.bot.output_dir = Path(self.input_folder.text().strip())
        self.bot.output_dir.mkdir(parents=True, exist_ok=True)

        delay = self.spin_delay.value()
        timeout = self.spin_timeout.value()
        char_tag = self.input_char.text().strip()

        self.btn_start.setEnabled(False)
        self.btn_start.start_pulse()
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setSmoothValue(0)

        pid = self.current_profile_id
        label = self.get_profile_label(pid)
        self.append_log(f"\n==========================================")
        self.append_log(f"🚀 Launching Batch on Profile {pid} ({label}) [Port: {self.bot.cdp_port}]")
        self.append_log(f"==========================================")

        self.worker = BotWorker(
            self.bot, prompts, "https://flow.google.com",
            delay, timeout, char_tag
        )
        self.worker.signals.log.connect(self.append_log)
        self.worker.signals.progress.connect(self.update_progress)
        self.worker.signals.finished.connect(self.on_batch_finished)
        self.worker.start()

    def toggle_pause(self):
        self.bot.pause()
        if self.bot.is_paused:
            self.btn_pause.setText("▶️ Resume")
            self.btn_start.stop_pulse()
        else:
            self.btn_pause.setText("⏸ Pause")
            self.btn_start.start_pulse()

    def stop_batch(self):
        self.bot.stop()
        self.btn_stop.setEnabled(False)
        self.btn_pause.setEnabled(False)
        self.btn_start.setEnabled(True)
        self.btn_start.stop_pulse()

    def on_batch_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_start.stop_pulse()
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ Pause")
        self.append_log("✨ All tasks finished safely!")

    def apply_reference_glassmorphism_theme(self):
        """
        Exact Glassmorphism theme matching the reference visual:
        Translucent dark glass cards, glowing neon pink/red borders, 
        smooth rounded corners, vibrant button gradients and glowing accents.
        """
        self.setStyleSheet("""
            #headerCard {
                background: rgba(14, 18, 30, 0.72);
                border: 1.5px solid rgba(244, 63, 94, 0.35);
                border-radius: 14px;
            }
            #headerProfileCard {
                background: rgba(22, 16, 28, 0.78);
                border: 1.5px solid #f43f5e;
                border-radius: 14px;
            }
            #bottomBar {
                background: rgba(14, 17, 28, 0.82);
                border: 1.5px solid rgba(244, 63, 94, 0.35);
                border-radius: 14px;
            }
            QGroupBox {
                background-color: rgba(12, 15, 26, 0.70);
                border: 1.5px solid rgba(244, 63, 94, 0.45);
                border-radius: 14px;
                font-weight: 700;
                font-size: 11px;
                letter-spacing: 0.5px;
                margin-top: 16px;
                padding-top: 14px;
                padding-left: 12px;
                padding-right: 12px;
                padding-bottom: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                top: 4px;
                padding: 3px 12px;
                color: #f43f5e;
                font-weight: 800;
                font-size: 11px;
                background-color: rgba(26, 16, 26, 0.95);
                border: 1.2px solid rgba(244, 63, 94, 0.75);
                border-radius: 6px;
            }
            #txtPrompts {
                background-color: rgba(8, 10, 18, 0.45);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 10px;
                color: #f8fafc;
                font-size: 12px;
            }
            #txtPrompts:focus {
                border: 1.5px solid #f43f5e;
                background-color: rgba(12, 14, 24, 0.65);
            }
            QLineEdit, QSpinBox {
                background-color: rgba(10, 12, 20, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 7px 11px;
                color: #f8fafc;
                font-size: 12px;
                selection-background-color: #be123c;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1.5px solid #f43f5e;
                background-color: rgba(16, 18, 30, 0.90);
            }
            QPushButton {
                background: rgba(24, 28, 44, 0.85);
                border: 1.2px solid rgba(255, 255, 255, 0.16);
                border-radius: 8px;
                padding: 7px 14px;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(40, 48, 76, 0.95);
                border: 1.2px solid rgba(255, 255, 255, 0.3);
            }
            QPushButton:pressed {
                background: rgba(16, 20, 34, 0.95);
                padding-top: 8px;
                padding-left: 15px;
            }
            QPushButton:disabled {
                background: rgba(20, 24, 36, 0.4);
                color: rgba(255, 255, 255, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
            QRadioButton {
                color: #e2e8f0;
                font-weight: 600;
                font-size: 11px;
                spacing: 6px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
            }
            QRadioButton::indicator:checked {
                background-color: #f43f5e;
                border: 2px solid #ffffff;
                border-radius: 7px;
            }
            QRadioButton::indicator:unchecked {
                background-color: rgba(14, 16, 26, 0.9);
                border: 2px solid #64748b;
                border-radius: 7px;
            }
            QRadioButton::indicator:unchecked:hover {
                border: 2px solid #f43f5e;
            }
            QProgressBar {
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                text-align: center;
                height: 22px;
                background-color: rgba(8, 10, 18, 0.85);
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:0.5 #10b981, stop:1 #34d399);
                border-radius: 7px;
            }
            QSplitter::handle {
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(10, 12, 20, 0.5);
                width: 8px;
                border-radius: 4px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(244, 63, 94, 0.4);
                min-height: 25px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #f43f5e;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 1. Remote License & Kill-Switch Check
    lic_res = license_manager.check_license()
    if not lic_res.allowed:
        msg_box = QMessageBox()
        msg_box.setWindowTitle("ARCreations — Access Verification")
        msg_box.setText(lic_res.message)
        msg_box.setIcon(QMessageBox.Critical)
        btn_ig = msg_box.addButton("Contact on Instagram (@arcreations008)", QMessageBox.ActionRole)
        btn_exit = msg_box.addButton("Exit", QMessageBox.RejectRole)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #0f111a;
                color: #ffffff;
                font-family: 'Segoe UI';
            }
            QLabel {
                color: #f8fafc;
                font-size: 12px;
            }
            QPushButton {
                background: rgba(225, 29, 72, 0.9);
                color: white;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
            }
        """)
        msg_box.exec()
        if msg_box.clickedButton() == btn_ig:
            webbrowser.open("https://www.instagram.com/arcreations008/?utm_source=chatgpt.com")
        sys.exit(0)

    requested = None
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        requested = int(sys.argv[1])
    window = MainWindow(requested_profile=requested, license_result=lic_res)
    window.show()
    sys.exit(app.exec())
