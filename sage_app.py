"""Great Sage AI Assistant - Minimal anime-style floating icon + speech bubble."""

import sys
import os
import re
import math
import time
import datetime
import random
import threading

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QMenu, QAction,
    QSystemTrayIcon
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QRect, QPropertyAnimation
)
from PyQt5.QtGui import (
    QFont, QIcon, QPixmap, QColor, QPainter, QPainterPath,
    QPen, QRadialGradient, QBrush, QFontMetrics, QKeySequence
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from sage_engine import route
from sage_brain import SageBrain, PERSONA, DEBATE_PERSONA
from sage_voice import SageVoice

# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------
IDLE      = 0
LISTENING = 1
THINKING  = 2
SPEAKING  = 3

FONT = QFont("Segoe UI", 12)

# ---------------------------------------------------------------------------
# Speech Bubble (anime panel style, auto-sizing, typewriter)
# ---------------------------------------------------------------------------
class SpeechBubble(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._target = None            # target icon/label to sit beside
        self._full = ""
        self._displayed = ""
        self._idx = 0
        self._active = False
        self._fade_anim = None
        self._tw = QTimer(self)
        self._tw.timeout.connect(self._tick)

    # -- public API ---------------------------------------------------------
    def attach(self, target):
        self._target = target
        self.setParent(None)  # top-level window, not child of anything

    def show_speech(self, text, auto_close=True, type_effect=True):
        if self._fade_anim and self._fade_anim.state() == QPropertyAnimation.Running:
            self._fade_anim.stop()
        self._full = text
        self._displayed = ""
        self._idx = 0
        self._active = True
        self._auto_close = auto_close
        self.show()
        self.raise_()
        self._place()
        self._reflow()
        if type_effect:
            self._char_step = max(1, int(len(text) / 40 or 1))  # ~1.5s worst case
            self._tw.start(30)
        else:
            self._displayed = text
            self._idx = len(text)
            self._schedule_close()

    def append_stream(self, chunk):
        """Append text while streaming (no typewriter, immediate)."""
        if self._tw.isActive():
            self._tw.stop()
        if not self._active:
            self._active = True
            self._auto_close = True
            self.show()
            self.raise_()
            self._place()
        self._full += chunk
        self._displayed = self._full
        self._idx = len(self._full)
        self._reflow()

    def finish_stream(self):
        self._schedule_close()

    def skip(self):
        self._displayed = self._full
        self._idx = len(self._full)
        if self._tw.isActive():
            self._tw.stop()
        self._reflow()

    def hide_bubble(self):
        self._active = False
        if self._tw.isActive():
            self._tw.stop()
        self.hide()

    # -- internals ----------------------------------------------------------
    def _tick(self):
        self._idx = min(self._idx + self._char_step, len(self._full))
        self._displayed = self._full[:self._idx]
        self._reflow()
        if self._idx >= len(self._full):
            self._tw.stop()
            self._schedule_close()

    def _schedule_close(self):
        if self._active and self._auto_close:
            QTimer.singleShot(6000, self._soft_close)

    def _soft_close(self):
        if not self._active:
            return
        if self._tw.isActive():
            self._tw.stop()
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(500)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._hide_bubble)
        self._fade_anim.start()

    def _hide_bubble(self):
        self._active = False
        self.hide()
        self.setWindowOpacity(1.0)

    def _place(self):
        if not self._target:
            return
        screen = QApplication.primaryScreen().geometry()
        t = self._target.pos()
        w = self.width()
        # sit to the right of the icon
        x = t.x() + self._target.width() + 10
        if x + w > screen.width() - 12:
            x = screen.width() - w - 12
        y = t.y() + self._target.height() // 2 - self.height() // 2
        y = max(8, min(y, screen.height() - self.height() - 8))
        self.move(x, y)

    def _reflow(self):
        fm = QFontMetrics(FONT)
        avail_w = min(450, 320)
        canvas = QRect(22, 16, avail_w - 44, 100000)
        h = fm.boundingRect(canvas, Qt.TextWordWrap, self._displayed + "  ").height()
        h = max(64, h + 34)
        screen = QApplication.primaryScreen().geometry()
        max_h = screen.height() - 60
        h = min(h, max_h)
        self.resize(avail_w + 16, h)
        if self._target:
            self._place()
        self.update()

    # -- drawing ------------------------------------------------------------
    def paintEvent(self, event):
        if not self._active:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # glow
        p.setPen(QPen(QColor(0, 180, 255, 50), 8))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(4, 4, w - 8, h - 8, 15, 15)

        # panel body
        grad = QRadialGradient(w / 2, h / 2, w * 0.8)
        grad.setColorAt(0, QColor(14, 24, 54, 235))
        grad.setColorAt(1, QColor(7, 11, 28, 245))
        p.setPen(QPen(QColor(0, 200, 255, 190), 2))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(1, 1, w - 2, h - 2, 14, 14)

        # corner accents
        for cx, cy in [(16, 16), (w - 16, 16), (16, h - 16), (w - 16, h - 16)]:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 220, 255, 170))
            p.drawEllipse(int(cx) - 3, int(cy) - 3, 6, 6)

        # text
        p.setFont(FONT)
        p.setPen(QColor(214, 232, 255))
        rect = QRect(22, 14, w - 44, h - 28)
        p.drawText(rect, Qt.TextWordWrap, self._displayed)

        # blinking caret while typing
        if self._tw.isActive():
            fm = QFontMetrics(FONT)
            shown = self._displayed
            lines = shown.split("\n")
            last_line = lines[-1] if lines else ""
            tw = fm.horizontalAdvance(last_line)
            full_h = fm.boundingRect(rect, Qt.TextWordWrap, shown).height()
            line_h = fm.lineSpacing()
            x = 22 + min(tw, max(0, w - 60))
            y_top = 14 + (full_h - len(lines) * line_h)
            y = 14 + full_h
            if time.time() % 1.0 < 0.6:
                p.setPen(QPen(QColor(0, 220, 255), 2))
                p.drawLine(int(x) + 2, max(8, y - line_h + 4), int(x) + 2, y)
        p.end()

    def mousePressEvent(self, event):
        self.skip()


# ---------------------------------------------------------------------------
# Floating Icon (the Great Sage eye)
# ---------------------------------------------------------------------------
class SageIcon(QWidget):
    command = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(72, 72)
        self._state = IDLE
        self._pulse = 0.0
        self._last_press = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(30)
        self._place()

    def _place(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(6, screen.height() // 2 - 36)

    def set_state(self, s):
        self._state = s
        self.update()

    def _animate(self):
        self._pulse += 0.07
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        pulse = (math.sin(self._pulse) + 1) / 2

        if self._state == IDLE:
            col = QColor(0, 155 + int(55 * pulse), 255)
            r = 29 + pulse * 2
        elif self._state == LISTENING:
            col = QColor(0, 255, 120)
            r = 31 + pulse * 3
        elif self._state == THINKING:
            hue = int((time.time() * 60) % 360)
            col = QColor.fromHsv(hue, 200, 255)
            r = 30 + pulse * 3
        else:  # SPEAKING
            col = QColor(130, 235, 255)
            r = 32 + pulse * 4

        # outer glow
        gl = QRadialGradient(cx, cy, r + 20)
        gl.setColorAt(0, QColor(col.red(), col.green(), col.blue(), 100 + int(70 * pulse)))
        gl.setColorAt(0.6, QColor(col.red(), col.green(), col.blue(), 25))
        gl.setColorAt(1, Qt.transparent)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(gl))
        p.drawEllipse(int(cx - r - 18), int(cy - r - 18), int((r + 18) * 2), int((r + 18) * 2))

        # rings
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 160), 3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 70), 1))
        p.drawEllipse(int(cx - r + 8), int(cy - r + 8), int((r - 8) * 2), int((r - 8) * 2))

        # inner body
        inner = QRadialGradient(cx - 4, cy - 4, r)
        inner.setColorAt(0, QColor(col.red(), min(255, col.green() + 20), 255, 235))
        inner.setColorAt(0.55, QColor(col.red() // 2, col.green() // 2, col.blue(), 210))
        inner.setColorAt(1, QColor(8, 12, 26, 230))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(inner))
        p.drawEllipse(int(cx - r + 5), int(cy - r + 5), int((r - 5) * 2), int((r - 5) * 2))

        # bright core
        core_r = int(r * 0.36)
        cg = QRadialGradient(cx, cy, core_r)
        cg.setColorAt(0, QColor(255, 255, 255, 255))
        cg.setColorAt(0.5, QColor(col.red(), 255, 255, 230))
        cg.setColorAt(1, Qt.transparent)
        p.setBrush(QBrush(cg))
        p.setPen(Qt.NoPen)
        p.drawEllipse(int(cx - core_r), int(cy - core_r), core_r * 2, core_r * 2)

        # orbiting sparks while busy
        if self._state in (THINKING, SPEAKING):
            t = time.time()
            for i in range(6):
                ang = t * 1.6 + i * math.pi / 3
                sx = cx + math.cos(ang) * (r - 9)
                sy = cy + math.sin(ang) * (r - 9)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 230, 255, 180))
                p.drawEllipse(int(sx) - 2, int(sy) - 2, 4, 4)
        p.end()

    # -- input --------------------------------------------------------------
    def mousePressEvent(self, event):
        now = time.time()
        if event.button() == Qt.LeftButton:
            if now - self._last_press < 0.35:
                self._last_press = 0
                self.command.emit("__DOUBLE__")
            else:
                self._last_press = now
                QTimer.singleShot(350, self._maybe_single)
            event.accept()

    def _maybe_single(self):
        if self._last_press != 0:
            was = self._last_press
            self._last_press = 0
            if time.time() - was < 0.6:
                self.command.emit("__SINGLE__")

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            pos = event.globalPos() - self.rect().center()
            screen = QApplication.primaryScreen().geometry()
            pos.setX(max(0, min(pos.x(), screen.width() - self.width())))
            pos.setY(max(0, min(pos.y(), screen.height() - self.height())))
            self.move(pos)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#101428; color:#d0e8ff; border:1px solid rgba(0,180,255,140); }"
            "QMenu::item:selected { background:rgba(0,150,220,180); }")
        act_tts = menu.addAction("Toggle Voice (TTS)")
        act_tts.triggered.connect(lambda: self.command.emit("__TTS__"))
        act_quit = menu.addAction("Quit")
        act_quit.triggered.connect(QApplication.quit)
        menu.exec_(event.globalPos())


# ---------------------------------------------------------------------------
# Small input bar (double-click)
# ---------------------------------------------------------------------------
class SageInput(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._target = None
        self._line = QLineEdit(self)
        self._line.setStyleSheet("""
            QLineEdit {
                background: rgba(10,18,48,242);
                color: #d0e8ff;
                border: 1.5px solid rgba(0,200,255,160);
                border-radius: 18px;
                padding: 7px 16px;
                font-size: 13px;
            }
            QLineEdit:focus { border: 1.5px solid rgba(0,220,255,255); }
        """)
        self._line.returnPressed.connect(self._fire)
        self._line.setPlaceholderText("Type your request...")

    def attach(self, target):
        self._target = target
        self.resize(330, 42)

    def open(self):
        if not self._target:
            return
        screen = QApplication.primaryScreen().geometry()
        t = self._target.pos()
        x = t.x() + self._target.width() + 10
        if x + self.width() > screen.width() - 10:
            x = t.x() - self.width() - 10
        y = t.y() + self._target.height() // 2 - self.height() // 2
        y = max(6, min(y, screen.height() - self.height() - 6))
        self.move(x, y)
        self.show()
        self.raise_()
        self._line.setFocus()
        self._line.clear()

    def _fire(self):
        text = self._line.text().strip()
        if text:
            self.submitted.emit(text)
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------
class AIWorker(QThread):
    chunk = pyqtSignal(str)
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, brain, text):
        super().__init__()
        self.brain = brain
        self.text = text

    def run(self):
        try:
            full = self.brain.ask(self.text, self.chunk.emit)
            self.done.emit(full)
        except Exception as e:
            self.error.emit(str(e))


class VoiceListener(QThread):
    result = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, voice_engine):
        super().__init__()
        self.voice = voice_engine

    def run(self):
        try:
            text = self.voice.listen_once(timeout=8, phrase_limit=12)
            if text:
                self.result.emit(text)
            else:
                self.error.emit("No speech detected")
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Main controller
# ---------------------------------------------------------------------------
class GreatSageApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.hide()  # invisible host

        from sage_config import load as load_cfg
        self.cfg = load_cfg()

        self.brain = SageBrain(self.cfg["model"])
        self.voice = SageVoice(self.cfg.get("tts_voice_rate", 170))
        self.tts_enabled = bool(self.cfg.get("tts_on_start", True))
        self._ai_worker = None
        self._voice_worker = None
        self._last_interaction = time.time()
        self._quiz = None
        self._debate = False
        self._busy = False

        self.icon = SageIcon()
        self.bubble = SpeechBubble()
        self.inp = SageInput()

        self.bubble.attach(self.icon)
        self.inp.attach(self.icon)

        self.icon.command.connect(self._on_icon_command)
        self.inp.submitted.connect(self._on_text)

        self._tray()

        self._proactive = QTimer(self)
        self._proactive.timeout.connect(self._proactive_check)
        self._proactive.start(15000)

        threading.Thread(target=self._boot, daemon=True).start()

    def run(self):
        self.icon.show()
        QTimer.singleShot(1800, self._greet)
        if self.cfg.get("watch_context", True):
            self._start_context_watch()

    # -- init ---------------------------------------------------------------
    def _boot(self):
        self.brain.ensure_running()
        self.brain.ensure_model()
        # pre-load the model so the first reply is fast
        self.brain.warm()
        if self.cfg.get("debate_on_start", False):
            self._debate = True
            self.brain.set_persona(DEBATE_PERSONA)

    def _greet(self):
        if self.cfg.get("tts_on_start", True):
            threading.Thread(target=self.voice.say,
                             args=("Great Sage online, Master.",), daemon=True).start()
        self.bubble.show_speech(
            self.cfg.get("greeting",
                         "【System】 Great Sage online. Tap me to speak, or double-click to type."))

    # -- context awareness ---------------------------------------------------
    def _start_context_watch(self):
        """Watch what the Master is doing on the main thread (Qt-safe):
        active window + clipboard typos. Helps proactively, with a cooldown."""
        from sage_utils import active_window_title, check_typos, is_code_editor
        self._ctx = {"window": "", "clip": "", "last_prompt": 0.0}

        def tick():
            if self._busy or self.icon._state != IDLE:
                self._ctx["window"] = ""
                return
            title = active_window_title()
            # --- typos from clipboard (when you copy text) ---
            if self.cfg.get("typo_watch", True) and title:
                from PyQt5.QtWidgets import QApplication
                clip = QApplication.clipboard().text()
                if clip and clip != self._ctx["clip"] and len(clip) > 3:
                    self._ctx["clip"] = clip
                    flags = check_typos(clip, max_flags=3)
                    if flags and time.time() - self._ctx["last_prompt"] > 30:
                        self._ctx["last_prompt"] = time.time()
                        fixes = ", ".join("'%s' -> '%s'" % f for f in flags[:3])
                        self._say_proactive(
                            "Master, I spotted a possible typo: %s.\n"
                            "I can help you make it perfect." % fixes)
            # --- react to a change of window ---
            if title and title != self._ctx["window"]:
                self._ctx["window"] = title
                parts = title.split(" || ")
                shown = parts[0][:70] if parts else title[:70]
                low = shown.lower()
                cooldown = self.cfg.get("proactive_seconds", 120) * 2.5
                if self._ctx["last_prompt"] == 0:
                    self._ctx["last_prompt"] = time.time() - cooldown + 40
                elif time.time() - self._ctx["last_prompt"] > cooldown:
                    if is_code_editor() and ("." in shown or "notepad" in low or "code" in low):
                        self._ctx["last_prompt"] = time.time()
                        self._say_proactive(
                            "Working on '%s', Master?\n"
                            "Say 'review my code' and I will check it for you." % shown)

        self._ctx_timer = QTimer(self)
        self._ctx_timer.timeout.connect(tick)
        self._ctx_timer.start(4000)

    def _say_proactive(self, text):
        if self.icon._state != IDLE:
            return
        if self._busy:
            return
        self._last_interaction = time.time()
        self.bubble.show_speech(text, auto_close=True)
        if self.tts_enabled:
            threading.Thread(target=self.voice.say,
                             args=(re.sub(r"【.*?】", "", text)[:300],), daemon=True).start()

    # -- icon actions -------------------------------------------------------
    def _on_icon_command(self, cmd):
        self._last_interaction = time.time()
        if cmd == "__SINGLE__":
            self._start_listening()
        elif cmd == "__DOUBLE__":
            self.inp.open()
        elif cmd == "__TTS__":
            self._toggle_tts()

    def _start_listening(self):
        if self._voice_worker and self._voice_worker.isRunning():
            return
        self.icon.set_state(LISTENING)
        self.bubble.show_speech("Listening...", auto_close=False)
        self._voice_worker = VoiceListener(self.voice)
        self._voice_worker.result.connect(self._on_voice)
        self._voice_worker.error.connect(self._on_voice_error)
        self._voice_worker.start()

    def _on_voice(self, text):
        self._last_interaction = time.time()
        self.bubble.show_speech("【Heard】 %s" % text, auto_close=False)
        QTimer.singleShot(600, lambda: self._process(text))

    def _on_voice_error(self, msg):
        self.icon.set_state(IDLE)
        if "No speech" in msg:
            self.bubble.show_speech("I did not hear anything, Master. Try again.")
        else:
            self.bubble.show_speech("Voice error: %s" % msg)
        QTimer.singleShot(2500, self.bubble.hide_bubble)

    # -- text ---------------------------------------------------------------
    def _on_text(self, text):
        self._last_interaction = time.time()
        self.bubble.show_speech("【Request】 %s" % text, auto_close=False)
        QTimer.singleShot(600, lambda: self._process(text))

    # -- core processing ----------------------------------------------------
    def _process(self, text):
        if self._quiz is not None:
            self._quiz_answer(text)
            return

        t = text.lower().strip()

        # ----- control commands -----
        if re.match(r"^\s*(debate|argue|challenge)\s+", t):
            topic = re.sub(r"^\s*(debate|argue|challenge)\s+", "", text, flags=re.I).strip()
            self._debate = True
            self.brain.set_persona(DEBATE_PERSONA)
            self.bubble.show_speech("【Debate】 Started. I will challenge you on '%s'.\n"
                                    "Say 'end debate' to stop." % topic, auto_close=False)
            QTimer.singleShot(1500, lambda: self._ask_ai("Let's debate: %s. State your position first." % topic))
            return
        if "end debate" in t or "stop debating" in t:
            if self._debate:
                self._debate = False
                self.brain.set_persona(PERSONA)
                self.bubble.show_speech("【Debate】 Ended. You argue well, Master.", auto_close=True)
            else:
                self.bubble.show_speech("We are not debating, Master.", auto_close=True)
            return
        if re.search(r"\b(what am i doing|what are we doing|whats on my screen|context)\b", t):
            from sage_utils import active_window_title
            info = active_window_title()
            shown, proc = (info.split(" || ") + [""])[:2]
            self.bubble.show_speech("【Context】 You are on: %s\n(Application: %s)"
                                    % (shown.strip(), proc.strip()), auto_close=True)
            return

        self.icon.set_state(THINKING)
        cat, result = route(text)

        if cat == "learn":
            self._learn(text, result)
        elif cat == "quiz" or cat == "code_request":
            self._ask_ai(text)
        elif cat == "code_review":
            self._review()
        elif cat and result:
            self.icon.set_state(SPEAKING)
            self.bubble.show_speech(result, auto_close=True)
            self._speak(result)
            QTimer.singleShot(9000, lambda: self.icon.set_state(IDLE))
        else:
            self._ask_ai(text)

    def _ask_ai(self, text):
        if self._ai_worker and self._ai_worker.isRunning():
            self.bubble.show_speech("Still generating, Master...")
            return
        if not self.brain.is_available():
            self.icon.set_state(IDLE)
            self.bubble.show_speech("Ollama is offline. Please start the Ollama application.")
            return
        self.bubble.show_speech("", auto_close=False)
        self._busy = True
        self._ai_worker = AIWorker(self.brain, text)
        self._ai_worker.chunk.connect(self.bubble.append_stream)
        self._ai_worker.done.connect(self._on_ai_done)
        self._ai_worker.error.connect(self._on_ai_error)
        self._ai_worker.start()

    def _on_ai_done(self, full):
        self._busy = False
        self.icon.set_state(SPEAKING)
        self.bubble.finish_stream()
        self._speak(full)
        QTimer.singleShot(9000, lambda: self.icon.set_state(IDLE))

    def _on_ai_error(self, msg):
        self._busy = False
        self.icon.set_state(IDLE)
        self.bubble.show_speech("【Error】 %s" % msg)
        QTimer.singleShot(4000, self.bubble.hide_bubble)

    # -- learn / quiz / review ---------------------------------------------
    def _learn(self, text, topic):
        import sage_search
        import sage_automation as auto

        def worker():
            self.bubble.show_speech("Researching '%s' for you, Master..." % topic, auto_close=False)
            outline = self.brain.learn_outline(topic)
            self.icon.set_state(SPEAKING)
            self.bubble.show_speech(outline, auto_close=False)
            self._speak("Opening YouTube course for %s. Say test me when ready." % topic)
            auto.show_desktop()
            time.sleep(0.8)
            sage_search.search_youtube_and_open(topic + " tutorial course for beginners")
            QTimer.singleShot(12000, lambda: self.icon.set_state(IDLE))
        threading.Thread(target=worker, daemon=True).start()

    def _quiz_start(self):
        topic = "general knowledge"
        self.bubble.show_speech("Generating quiz...", auto_close=False)

        def worker():
            qs = self.brain.generate_quiz(topic, 4)
            if not qs:
                self.bubble.show_speech("Could not generate quiz.", auto_close=True)
                return
            self._quiz = {"qs": qs, "idx": 0, "correct": 0}
            self._quiz_next()

        threading.Thread(target=worker, daemon=True).start()

    def _quiz_next(self):
        q = self._quiz["qs"][self._quiz["idx"]]
        self.bubble.show_speech(
            "【Quiz %d/%d】\n%s\n\nDouble-click me & type your answer."
            % (self._quiz["idx"] + 1, len(self._quiz["qs"]), q["q"]),
            auto_close=False)

    def _quiz_answer(self, text):
        q = self._quiz["qs"][self._quiz["idx"]]
        self.bubble.show_speech("Grading...", auto_close=False)

        def worker():
            label, fb = self.brain.grade_answer(q, text)
            if label.lower() == "correct":
                self._quiz["correct"] += 1
            self._quiz["idx"] += 1
            if self._quiz["idx"] >= len(self._quiz["qs"]):
                n = self._quiz["correct"]
                total = len(self._quiz["qs"])
                self.bubble.show_speech(
                    "【Quiz Done】 %d/%d correct (%d%%).\n\n%s"
                    % (n, total, int(100 * n / total), fb), auto_close=True)
                self._quiz = None
            else:
                self.bubble.show_speech(fb, auto_close=False)
                QTimer.singleShot(1200, self._quiz_next)
        threading.Thread(target=worker, daemon=True).start()

    def _review(self):
        from sage_engine import list_code_files
        self.bubble.show_speech("Looking for code to review...", auto_close=False)

        def worker():
            files = list_code_files()
            if not files:
                self.bubble.show_speech("No code files found to review.")
                return
            latest = max(files, key=os.path.getmtime)
            self.bubble.show_speech("Reviewing %s..." % os.path.basename(latest), auto_close=False)
            corrected, summary = self.brain.review_code(latest)
            if corrected:
                base, ext = os.path.splitext(latest)
                out = base + "_corrected" + ext
                with open(out, "w", encoding="utf-8") as f:
                    f.write(corrected)
                self.bubble.show_speech("【Reviewed】\n%s\n\nSaved corrected: %s"
                                        % (summary, os.path.basename(out)), auto_close=True)
            else:
                self.bubble.show_speech(summary or "Could not review.")

        threading.Thread(target=worker, daemon=True).start()

    # -- speech output ------------------------------------------------------
    def _speak(self, text):
        if not self.tts_enabled:
            return
        clean = re.sub(r"【.*?】", "", text)
        if clean.strip():
            threading.Thread(target=self.voice.say, args=(clean[:400],), daemon=True).start()

    def _toggle_tts(self):
        self.tts_enabled = not self.tts_enabled
        self.bubble.show_speech("Voice output %s." % ("on" if self.tts_enabled else "off"))

    # -- proactive ----------------------------------------------------------
    def _proactive_check(self):
        if self.icon._state != IDLE:
            return
        if time.time() - self._last_interaction > 45:
            phrases = [
                "Master, do you need assistance?",
                "I am standing by. What shall we do next?",
                "Is there anything I can help with?",
                "At your service, Master.",
                "Shall I search or open something for you?",
            ]
            self.bubble.show_speech(random.choice(phrases))
            self._last_interaction = time.time()

    # -- tray ---------------------------------------------------------------
    def _tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray_icon = QSystemTrayIcon()
        icon_path = os.path.join(BASE_DIR, "assets", "great_sage_icon.png")
        if os.path.isfile(icon_path):
            self._tray_icon.setIcon(QIcon(icon_path))
        tray_menu = QMenu()
        tray_menu.setStyleSheet(
            "QMenu { background:#101428; color:#d0e8ff; border:1px solid rgba(0,180,255,140); }"
            "QMenu::item:selected { background:rgba(0,150,220,180); }")
        a_show = tray_menu.addAction("Show Sage")
        a_show.triggered.connect(lambda: (self.icon.show(), self.icon.raise_()))
        a_tts = tray_menu.addAction("Toggle Voice (TTS)")
        a_tts.triggered.connect(self._toggle_tts)
        a_quit = tray_menu.addAction("Quit")
        a_quit.triggered.connect(QApplication.quit)
        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.show()


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    sage = GreatSageApp()
    sage.run()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()