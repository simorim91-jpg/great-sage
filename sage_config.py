"""Great Sage configuration (config.json) - user-editable settings."""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULTS = {
    "model": "qwen2.5:1.5b",
    "browser": "auto",              # auto | chrome | firefox | edge | brave
    "tts_on_start": True,           # speak out loud at startup
    "tts_voice_rate": 170,
    "proactive_seconds": 45,        # Sage speaks up after silence
    "watch_context": True,          # watch what you do + help
    "typo_watch": True,             # catch typos when you copy text
    "debate_on_start": False,
    "greeting": "【System】 Great Sage online. Tap me to speak, or double-click to type."
}


def load():
    cfg = dict(DEFAULTS)
    try:
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            for k in DEFAULTS:
                if k in user:
                    cfg[k] = user[k]
    except Exception:
        pass
    return cfg


def save(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass