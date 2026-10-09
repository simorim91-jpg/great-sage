"""Mouse, keyboard and browser automation - lets Great Sage do anything
you can do with a mouse and keyboard (scroll, click, like, dislike, etc)."""

import time
from pynput.mouse import Button, Controller as MouseCtrl
from pynput.keyboard import Controller as KeyCtrl, Key

_mouse = MouseCtrl()
_keys = KeyCtrl()


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def tap(key):
    """Press and release one key."""
    _keys.press(key)
    _keys.release(key)


def chord(keys):
    """Press several keys together then release (e.g. hotkeys)."""
    if not isinstance(keys, (tuple, list)):
        keys = [keys]
    for k in keys:
        _keys.press(k)
    for k in reversed(keys):
        _keys.release(k)


def _ctrl(key):
    chord([Key.ctrl, key])


def _alt(key):
    chord([Key.alt, key])


def _win(key):
    chord([Key.cmd, key])


# ---------------------------------------------------------------------------
# Mouse actions
# ---------------------------------------------------------------------------
def click(button="left"):
    b = Button.left if button == "left" else Button.right if button == "right" else Button.middle
    _mouse.click(b)
    return "Clicked mouse (%s) at current position." % button


def double_click():
    _mouse.click(Button.left, 2)
    return "Double-clicked mouse."


def right_click():
    _mouse.click(Button.right)
    return "Right-clicked mouse."


def scroll(direction="down", amount=3):
    dy = -amount if direction == "down" else amount
    _mouse.scroll(0, dy)
    return "Scrolled %s." % direction


def move_mouse(offset="center"):
    try:
        from ctypes import windll
        width = windll.user32.GetSystemMetrics(0)
        height = windll.user32.GetSystemMetrics(1)
        sx, sy = windll.user32.GetSystemMetrics(76), windll.user32.GetSystemMetrics(77)
    except Exception:
        width, height, sx, sy = 1920, 1080, 0, 0
    if offset == "center":
        x, y = sx + width // 2, sy + height // 2
    elif offset.startswith("top"):
        x, y = sx + width // 2, sy + height // 4
    elif offset.startswith("bottom"):
        x, y = sx + width // 2, sy + height * 3 // 4
    elif offset.startswith("left"):
        x, y = sx + width // 4, sy + height // 2
    elif offset.startswith("right"):
        x, y = sx + width * 3 // 4, sy + height // 2
    else:
        x, y = sx + width // 2, sy + height // 2
    _mouse.position = (x, y)
    return "Mouse moved to %s of the screen." % offset


# ---------------------------------------------------------------------------
# Browser / media hotkeys
# ---------------------------------------------------------------------------
def like():
    tap("l")
    return "Pressed Like (L). Tip: click the video first so YouTube shortcuts work."


def dislike():
    tap(";")
    return "Pressed Dislike (;)."


def new_tab():
    _ctrl("t")
    return "Opened a new tab."


def close_tab():
    _ctrl("w")
    return "Closed the current tab."


def refresh():
    tap(Key.f5)
    return "Refreshed the page."


def hard_refresh():
    chord([Key.ctrl, Key.shift, "r"])
    return "Hard-refreshed the page."


def go_back():
    _alt(Key.left)
    return "Went back."


def go_forward():
    _alt(Key.right)
    return "Went forward."


def fullscreen():
    tap(Key.f11)
    return "Toggled fullscreen."


def play_pause():
    tap(Key.space)
    return "Played / paused."


def mute_toggle():
    tap("m")
    return "Toggled mute on media player."


def show_desktop():
    _win("d")
    return "Showed the desktop (minimized all windows)."


def close_current_window():
    _alt(Key.f4)
    return "Closed the active window."


def select_all():
    _ctrl("a")
    return "Selected all."


def copy_key():
    _ctrl("c")
    return "Copied selection."


def paste_key():
    _ctrl("v")
    return "Pasted."


def undo_key():
    _ctrl("z")
    return "Undid last action."


def find_in_page():
    _ctrl("f")
    return "Opened find-in-page."


# ---------------------------------------------------------------------------
# Command router for mouse/keyboard words
# ---------------------------------------------------------------------------
_AUTOMAP = {
    "scroll up": lambda _: scroll("up"),
    "scroll down": lambda _: scroll("down"),
    "scroll more": lambda _: scroll("down", 6),
    "scroll a lot": lambda _: scroll("down", 12),
    "scroll top": lambda _: scroll("up", 20),
    "click": lambda _: click(),
    "click left": lambda _: click("left"),
    "double click": lambda _: double_click(),
    "double-click": lambda _: double_click(),
    "right click": lambda _: right_click(),
    "right-click": lambda _: right_click(),
    "like": lambda _: like(),
    "thumbs up": lambda _: like(),
    "dislike": lambda _: dislike(),
    "thumbs down": lambda _: dislike(),
    "new tab": lambda _: new_tab(),
    "open new tab": lambda _: new_tab(),
    "close tab": lambda _: close_tab(),
    "refresh": lambda _: refresh(),
    "reload": lambda _: refresh(),
    "back": lambda _: go_back(),
    "go back": lambda _: go_back(),
    "forward": lambda _: go_forward(),
    "fullscreen": lambda _: fullscreen(),
    "play": lambda _: play_pause(),
    "pause": lambda _: play_pause(),
    "play and pause": lambda _: play_pause(),
    "mute": lambda _: mute_toggle(),
    "show desktop": lambda _: show_desktop(),
    "desktop": lambda _: show_desktop(),
    "minimize": lambda _: show_desktop(),
    "close window": lambda _: close_current_window(),
    "close this window": lambda _: close_current_window(),
    "select all": lambda _: select_all(),
    "copy": lambda _: copy_key(),
    "paste": lambda _: paste_key(),
    "undo": lambda _: undo_key(),
    "find": lambda _: find_in_page(),
    "move mouse center": lambda _: move_mouse("center"),
    "mouse center": lambda _: move_mouse("center"),
    "mouse top": lambda _: move_mouse("top"),
    "mouse bottom": lambda _: move_mouse("bottom"),
    "mouse left": lambda _: move_mouse("left"),
    "mouse right": lambda _: move_mouse("right"),
}


def route_mouse(text):
    """Route a natural-language mouse/keyboard command. Returns status text or None."""
    t = text.lower().strip()
    # patterns with arguments
    m = __import__("re").search(r"scroll (up|down)\s+(\d+)", t)
    if m:
        return scroll(m.group(1), min(30, int(m.group(2))))
    if t in _AUTOMAP:
        return _AUTOMAP[t](t)
    return None