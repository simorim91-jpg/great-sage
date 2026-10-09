"""Great Sage utilities: word<->number, active window, browser detection,
typo checking - all offline, no heavy dependencies."""

import ctypes
import ctypes.wintypes
import os
import re
import subprocess
import difflib

# ---------------------------------------------------------------------------
# English number words -> digits (for math via voice)
# ---------------------------------------------------------------------------
_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1000000}


def _parse_words(s):
    s = s.strip().lower()
    if not s:
        return None
    words = re.sub(r"[- ]", " ", s).split()
    total, current = 0, 0
    for w in words:
        if w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w in _SCALES:
            current *= _SCALES[w]
            total += current
            current = 0
        else:
            return None
    return total + current


def words_to_number(expr):
    """Replace English number words inside an expression with digits."""
    NUM_WORDS = (
        "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
        "thousand|million|ten|eleven|twelve|thirteen|fourteen|fifteen|"
        "sixteen|seventeen|eighteen|nineteen|zero|one|two|three|four|five|"
        "six|seven|eight|nine"
    )
    seq_re = re.compile(
        r"\b(?:" + NUM_WORDS + r")(?:[\- ]+(?:" + NUM_WORDS + r"))*\b", re.I)

    def repl(m):
        digits = _parse_words(m.group(0))
        return str(digits) if digits is not None else m.group(0)
    return seq_re.sub(repl, expr)


# ---------------------------------------------------------------------------
# Active window detection (what is the user doing on screen)
# ---------------------------------------------------------------------------
def active_window_title():
    """Return the title + process name of the currently focused window."""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "Unknown"
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        # process name
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = "Unknown"
        try:
            if pid.value:
                hproc = kernel32.OpenProcess(0x1000, False, pid.value)
                if hproc:
                    name = ctypes.create_unicode_buffer(260)
                    kernel32.QueryFullProcessImageNameW(hproc, 0, name, ctypes.byref(ctypes.c_ulong(260)))
                    proc = os.path.basename(name.value)
                    kernel32.CloseHandle(hproc)
        except Exception:
            pass
        return "%s || %s" % (title, proc)
    except Exception:
        return "Unknown"


def _process_name():
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            hproc = kernel32.OpenProcess(0x1000, False, pid.value)
            if hproc:
                pn = ctypes.create_unicode_buffer(260)
                kernel32.QueryFullProcessImageNameW(hproc, 0, pn, ctypes.byref(ctypes.c_ulong(260)))
                kernel32.CloseHandle(hproc)
                return os.path.basename(pn.value).lower()
    except Exception:
        pass
    return ""


def is_code_editor():
    """True when the foreground app looks like a code editor."""
    pn = _process_name()
    return any(k in pn for k in ("code", "notepad", "sublime", "pycharm",
                                 "vim", "atom", "emacs", "geany"))


# ---------------------------------------------------------------------------
# Browser detection (choose which browser to open search results in)
# ---------------------------------------------------------------------------
def find_browser(which=None):
    """Return the executable path for a browser name, or the default choice."""
    _candidates = {
        "chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
        "edge": [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"],
        "firefox": [r"C:\Program Files\Mozilla Firefox\firefox.exe",
                    r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"],
        "brave": [r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                  os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe")],
        "opera": [r"C:\Program Files\Opera\launcher.exe"],
        "vivaldi": [r"C:\Program Files\Vivaldi\Application\vivaldi.exe"],
    }

    def exists(path):
        return path and os.path.isfile(path)

    # explicit request
    if which:
        key = which.lower()
        key = {"msedge": "edge", "google chrome": "chrome", "mozilla": "firefox",
               "explorer": "edge"}.get(key, key)
        for p in _candidates.get(key, []):
            if exists(p):
                return p, key
    # ordered preference
    order = ["chrome", "edge", "firefox", "brave"]
    for key in order:
        for p in _candidates.get(key, []):
            if exists(p):
                return p, key
    return None, "system"


def open_url(url, browser=None):
    """Open a URL in a chosen browser. Returns (status_string, browser_name)."""
    exe, name = find_browser(browser)
    if exe:
        subprocess.Popen([exe, url])
        return name
    import webbrowser
    webbrowser.open(url)
    return "system default"


def is_installed(browser):
    exe, _ = find_browser(browser)
    return exe is not None


# ---------------------------------------------------------------------------
# Lightweight typo checker (offline, dictionary + difflib)
# ---------------------------------------------------------------------------
_COMMON_WORDS = set("""
the and for are but not you all any can had her was one our out day get has him
how its may new now see two way who did men put set say she too use vs where
look make more only over some them then this what when which will with your
about after again also before could every first great house just know little
large mean might much must never next other place right same should small still
such take than these thing think three through under until very well while world
would write again always believe because through although though thought through
another between both different during enough few follow found give good great
group hand help important include into just kind large leave let life like long
man matter means most move number often open own part people person place point
present problem public real right run seem show side small social sound still
story student study system tell those thing think today together toward try turn
teacher course school learn study teach python code program computer browser
window mouse keyboard screen search video youtube google chrome firefox edge
saturday sunday monday tuesday wednesday thursday friday january february march
april may june july august september october november december today tomorrow
yesterday morning afternoon evening night please thanks thank hello hi hey help
""".split())

_COMMON_TYPOS = {
    "teh": "the", "recieve": "receive", "adress": "address", "definately": "definitely",
    "seperate": "separate", "occured": "occurred", "untill": "until", "wich": "which",
    "becuase": "because", "wich": "which", "alot": "a lot", "wierd": "weird",
    "beleive": "believe", "peice": "piece", "freind": "friend", "calender": "calendar",
    "colum": "column", "excercise": "exercise", "persistant": "persistent",
    "occurence": "occurrence", "tommorow": "tomorrow", "cemetary": "cemetery",
    "guage": "gauge", "maintainance": "maintenance", "neccessary": "necessary",
    "should of": "should have", "could of": "could have", "would of": "would have",
    "compter": "computer", "pthon": "python", "pythen": "python", "calculatin": "calculating",
    "becoz": "because", "u": "you", "plz": "please", "thx": "thanks", "k": "ok",
}


def check_typos(text, max_flags=4):
    """Return list of (wrong, corrected) pairs found in text."""
    if not text or len(text.strip()) < 4:
        return []
    flags = []
    lowered = text.lower()
    # word-level: split on non-letters but keep apostrophes' meaning
    words = re.findall(r"[a-z][a-z']*", lowered)
    seen = set()
    for w in words:
        if w in _COMMON_TYPOS:
            cand = _COMMON_TYPOS[w]
            if cand not in lowered or True:
                if w not in seen:
                    flags.append((w, cand))
                    seen.add(w)
                    if len(flags) >= max_flags:
                        return flags
    return flags


def code_looks_wrong(code):
    """Very light sanity checks for obvious Python mistakes."""
    issues = []
    if code.count("(") != code.count(")"):
        issues.append("Unbalanced parentheses.")
    if code.count("def ") >= 1 and not code.strip().endswith((":", ")", "]", "}")):
        if "\n" not in code and ";" not in code:
            pass
    return issues


if __name__ == "__main__":
    print(words_to_number("what is seven times eight"))
    print(check_typos("I wil recieve teh package tomorow"))
    print(active_window_title())
    print(find_browser("chrome"))