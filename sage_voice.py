"""Voice input (SpeechRecognition) and output (pyttsx3) engine."""

import threading
import time
import speech_recognition as sr
import pyttsx3


class SageVoice:
    def __init__(self, rate=170):
        self.rec = sr.Recognizer()
        self.rate = rate
        self._tts = None
        self._tts_lock = threading.Lock()
        self.speaking = False
        self._init_tts()

    def _init_tts(self):
        try:
            self._tts = pyttsx3.init()
            self._tts.setProperty("rate", self.rate)
            voices = self._tts.getProperty("voices")
            # prefer a natural female/en-US voice if available
            fav = None
            for v in voices:
                name = v.name
                if "Zira" in name or "Hazel" in name or ("Aria" in name):
                    fav = v
                    break
            # zira is a good default
            for v in voices:
                if "Zira" in v.name:
                    fav = v
                    break
            if fav is not None:
                self._tts.setProperty("voice", fav.id)
        except Exception:
            self._tts = None

    # -- Speaking (TTS) -----------------------------------------------------
    def say(self, text, wait=False):
        """Speak text (synchronous). Call from a background thread."""
        self.speaking = True
        with self._tts_lock:
            try:
                if self._tts is None:
                    self._init_tts()
                if self._tts is not None:
                    self._tts.say(text)
                    self._tts.runAndWait()
            except Exception:
                try:
                    self._tts = pyttsx3.init()
                    self._tts.setProperty("rate", self.rate)
                    self._tts.say(text)
                    self._tts.runAndWait()
                except Exception:
                    pass
        self.speaking = False

    # -- Listening (STT) ----------------------------------------------------
    def listen_once(self, timeout=8, phrase_limit=12):
        """Capture a short utterance and return text (str) or None."""
        with sr.Microphone() as source:
            self.rec.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = self.rec.listen(source, timeout=timeout,
                                        phrase_time_limit=phrase_limit)
                return self.rec.recognize_google(audio, language="en-US")
            except (sr.WaitTimeoutError, sr.UnknownValueError, sr.RequestError):
                return None