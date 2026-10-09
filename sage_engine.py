"""Great Sage command engine: opens programs, calculates, writes files,
types text, and controls the system - all from natural language."""

import os
import re
import ast
import time
import glob
import math
import ctypes
import shutil
import subprocess
import datetime
import webbrowser
import urllib.parse

from PIL import ImageGrab
from sage_automation import route_mouse

import sage_search
import sage_automation as auto
from sage_utils import words_to_number, open_url, find_browser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(os.path.expanduser("~"), "Documents")
SAGE_FOLDER = os.path.join(DOCS_DIR, "GreatSage")
NOTES_FILE = os.path.join(SAGE_FOLDER, "sage_notes.txt")
CODE_FOLDER = os.path.join(SAGE_FOLDER, "GreatSage_Code")
SHOT_FOLDER = os.path.join(SAGE_FOLDER, "GreatSage_Screenshots")

for folder in (SAGE_FOLDER, CODE_FOLDER, SHOT_FOLDER):
    os.makedirs(folder, exist_ok=True)

# ---------------------------------------------------------------------------
# Safe math evaluator (no evil eval)
# ---------------------------------------------------------------------------
_MATH_OPS = {
    "pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf,
    "abs": abs, "min": min, "max": max, "round": round, "sum": sum,
    "sqrt": math.sqrt, "cbrt": getattr(math, "cbrt", None),
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "atan2": math.atan2, "log": math.log, "log10": math.log10,
    "log2": math.log2, "exp": math.exp, "pow": pow,
    "floor": math.floor, "ceil": math.ceil, "trunc": math.trunc,
    "factorial": math.factorial, "gcd": math.gcd, "lcm": getattr(math, "lcm", None),
    "degrees": math.degrees, "radians": math.radians,
    "hypot": math.hypot, "degrees": math.degrees, "modf": math.modf,
    "isqrt": getattr(math, "isqrt", None), "copysign": math.copysign,
}
for _n in ("cbrt", "lcm", "isqrt"):
    if _MATH_OPS.get(_n) is None:
        _MATH_OPS.pop(_n, None)


class _SafeEval:
    def __init__(self):
        self.names = {"__builtins__": {}}
        self.names.update(_MATH_OPS)

    def _walk(self, node):
        if isinstance(node, ast.Expression):
            return self._walk(node.body)
        if isinstance(node, ast.Num):
            return node.n
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            left = self._walk(node.left)
            right = self._walk(node.right)
            import operator
            ops = {ast.Add: operator.add, ast.Sub: operator.sub,
                   ast.Mult: operator.mul, ast.Div: operator.truediv,
                   ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
                   ast.Pow: operator.pow}
            for cls, fn in ops.items():
                if isinstance(node.op, cls):
                    return fn(left, right)
            raise ValueError("unsupported operator")
        if isinstance(node, ast.UnaryOp):
            operand = self._walk(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            raise ValueError("unsupported unary op")
        if isinstance(node, ast.Call):
            fn = self._walk(node.func)
            args = [self._walk(a) for a in node.args]
            if not callable(fn):
                raise ValueError("not callable")
            return fn(*args)
        if isinstance(node, ast.Name):
            if node.id in self.names:
                return self.names[node.id]
            raise ValueError("unknown symbol: %s" % node.id)
        if isinstance(node, ast.Attribute):
            obj = self._walk(node.value)
            if isinstance(obj, (int, float)) and node.attr == "__class__":
                raise ValueError("denied")
            val = getattr(obj, node.attr, None)
            if isinstance(val, (int, float)) or callable(val):
                return val
            raise ValueError("denied attribute")
        raise ValueError("unsupported expression")

    def eval(self, expr):
        tree = ast.parse(expr, mode="eval")
        return self._walk(tree)


def calculate(text):
    """Try to extract and solve a math expression from natural text."""
    expr = text
    expr = expr.lower()
    # convert spoken number words -> digits ("seven times eight" -> "7 * 8")
    expr = words_to_number(expr)
    # handle "what is X% of Y" -> X/100 * Y
    expr = re.sub(r"\bpercent of\b", "% of", expr)
    m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:of)?\s*(\d+(?:\.\d+)?)", expr)
    if m_pct:
        pct = float(m_pct.group(1)) / 100.0
        base = float(m_pct.group(2))
        res = pct * base
        return "【Answer】 %s%% of %s = %s" % (
            m_pct.group(1), m_pct.group(2), _fmt_num(round(res, 6) if isinstance(res, float) and res.is_integer() else res))
    expr = expr.replace("x", " * ").replace("X", " * ")
    expr = re.sub(r"\bplus\b", "+", expr)
    expr = re.sub(r"\bminus\b", "-", expr)
    expr = re.sub(r"\btimes\b", "*", expr)
    expr = re.sub(r"\bmultiplied by\b", "*", expr)
    expr = re.sub(r"\bdivided by\b", "/", expr)
    expr = re.sub(r"\bover\b", "/", expr)
    expr = re.sub(r"\bpercent\b", "/100", expr)
    expr = re.sub(r"\bpower\b", "**", expr)
    expr = re.sub(r"\bto the\b", "**", expr)
    expr = re.sub(r"\bmod\b", "%", expr)
    expr = re.sub(r"\bsquare root\b", "sqrt", expr)
    expr = re.sub(r"\bsqrt\b", "sqrt", expr)
    expr = re.sub(r"\babsolute value\b", "abs", expr)
    expr = expr.replace(",", "").replace("calculate", "").replace("calc", "")
    expr = expr.replace("what is", "").replace("what's", "").replace("whats", "")
    expr = expr.replace("=", "").replace("?", "").strip().strip(".")
    expr = expr.replace("^", "**")
    # allow only safe content
    if not re.match(r"^[\d\s\.\+\-\*\/\(\)%<>=!\^,]*(pi|e|tau|abs|sqrt|sin|cos|tan|log|exp|pow|floor|ceil|round|min|max|mod|%)*[\d\s\.\+\-\*\/\(\)%<>=!^,]*$", expr):
        return None
    if not re.search(r"\d", expr):
        return None
    try:
        result = _SafeEval().eval(expr)
    except Exception:
        return None
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    if isinstance(result, (int, float)):
        return "【Answer】 %s = %s" % (text.strip().rstrip("?"), _fmt_num(result))
    return None


def _fmt_num(n):
    if isinstance(n, float):
        return ("%.6f" % n).rstrip("0").rstrip(".")
    return str(n)


# ---------------------------------------------------------------------------
# App / website launching
# ---------------------------------------------------------------------------
_KNOWN_APPS = {
    "chrome": ["chrome", "google chrome"], "firefox": ["firefox"],
    "edge": ["msedge", "microsoft edge", "edge"], "brave": ["brave"],
    "notepad": ["notepad", "note pad"], "calculator": ["calc", "calculator"],
    "paint": ["mspaint", "paint"], "wordpad": ["wordpad", "word pad"],
    "cmd": ["cmd", "command prompt", "terminal"], "powershell": ["powershell"],
    "explorer": ["explorer", "file explorer", "files"], "task manager": ["taskmgr"],
    "control panel": ["control panel", "control"], "settings": ["ms-settings"],
    "paint": ["mspaint"], "word": ["winword", "microsoft word", "word"],
    "excel": ["excel", "microsoft excel"], "powerpoint": ["powerpoint", "microsoft powerpoint"],
    "outlook": ["outlook"], "onenote": ["onenote"], "teams": ["ms-teams", "teams"],
    "vs code": ["code", "visual studio code", "vs code"], "vscode": ["code"],
    "pycharm": ["pycharm"], "ij": ["idea"], "spotify": ["spotify"],
    "games": ["xbox", "xbox app"], "steam": ["steam"], "epic": ["epic games launcher"],
    "vlc": ["vlc", "media player"], "winamp": ["winamp"],
    "whatsapp": ["whatsapp"], "telegram": ["telegram"], "discord": ["discord"],
    "zoom": ["zoom"], "skype": ["skype"], "slack": ["slack"],
    "photoshop": ["photoshop"], "gimp": ["gimp"],
    "snipping": ["snippingtool", "snipping tool", "snip"],
    "youtube": ["youtube"], "netflix": ["netflix"],
    "ccleaner": ["ccleaner"], "malwarebytes": ["malwarebytes"],
}

_KNOWN_SITES = {
    "google": "https://www.google.com", "youtube": "https://www.youtube.com",
    "github": "https://github.com", "gmail": "https://mail.google.com",
    "gmail inbox": "https://mail.google.com", "chatgpt": "https://chatgpt.com",
    "translate": "https://translate.google.com", "maps": "https://maps.google.com",
    "maps google": "https://maps.google.com", "maps google": "https://maps.google.com",
    "wikipedia": "https://www.wikipedia.org", "reddit": "https://www.reddit.com",
    "twitter": "https://x.com", "x.com": "https://x.com", "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com", "tiktok": "https://www.tiktok.com",
    "netflix": "https://www.netflix.com", "spotify": "https://open.spotify.com",
    "stackoverflow": "https://stackoverflow.com", "amazon": "https://www.amazon.com",
    "ebay": "https://www.ebay.com", "drive": "https://drive.google.com",
    "docs": "https://docs.google.com", "sheets": "https://sheets.google.com",
    "slides": "https://slides.google.com", "calendar": "https://calendar.google.com",
    "freecodecamp": "https://www.freecodecamp.org", "w3schools": "https://www.w3schools.com",
    "mdn": "https://developer.mozilla.org",
}

_SYS_APPS = {
    "cmd": "cmd.exe", "command prompt": "cmd.exe",
    "powershell": "powershell.exe", "pwsh": "powershell.exe",
    "notepad": "notepad.exe", "calculator": "calc.exe",
    "paint": "mspaint.exe", "wordpad": "write.exe",
    "task manager": "taskmgr.exe", "explorer": "explorer.exe",
    "control panel": "control.exe", "file explorer": "explorer.exe",
    "run": "rundll32",
}


def _start_menu_apps():
    """Fuzzy search of installed programs in the Start Menu."""
    roots = [
        os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    hits = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for lnk in glob.glob(os.path.join(root, "**", "*.lnk"), recursive=True):
            hits.append(lnk)
    return hits


def find_app(name):
    """Resolve a spoken app name to something we can launch."""
    name = name.strip().lower()
    name = re.sub(r"^\s*(open|launch|start|run)\s+", "", name)
    # direct system command match
    if name in _SYS_APPS:
        return ("system", _SYS_APPS[name])
    # known apps list
    for key, aliases in _KNOWN_APPS.items():
        if name == key or name in aliases or (len(name) > 3 and key in name):
            return ("known", key)
    # try start menu scan
    for lnk in _start_menu_apps():
        base = os.path.splitext(os.path.basename(lnk))[0].lower()
        if name == base or name in base or base in name:
            return ("lnk", lnk)
    return (None, None)


def open_app(name):
    clean = re.sub(r"^\s*(open|launch|start|run|show)\s+", "", name, flags=re.I).strip()
    kind, target = find_app(name)
    if kind == "system":
        subprocess.Popen(target, shell=True)
        return "【Executed】 Opened %s." % clean
    if kind == "known":
        if target in ("chrome", "google chrome"):
            subprocess.Popen(["cmd", "/c", "start", "chrome"], shell=True)
        elif target == "msedge":
            subprocess.Popen(["cmd", "/c", "start", "msedge"], shell=True)
        elif target in ("code", "visual studio code", "vs code"):
            subprocess.Popen(["cmd", "/c", "start", "code"], shell=True)
        elif target == "ms-settings":
            os.system("start ms-settings:") if os.name == "nt" else webbrowser.open("ms-settings:")
        else:
            subprocess.Popen(["cmd", "/c", "start", target], shell=True)
        return "【Executed】 Opened %s." % clean
    if kind == "lnk":
        os.startfile(target)
        return "【Executed】 Opened %s." % os.path.splitext(os.path.basename(target))[0]
    return None


def open_website(name):
    name = name.lower().strip()
    name = re.sub(r"^\s*(open|launch|go to|visit)\s+", "", name)
    name = name.replace(" ", "").replace("dot", ".").replace("com", ".com")
    url = _KNOWN_SITES.get(name, _KNOWN_SITES.get(name.replace(".com", "")))
    if url:
        webbrowser.open(url)
        return "【Executed】 Opened %s." % name
    if re.match(r"^[a-zA-Z0-9\-\.]+\.(com|net|org|io|ai|dev|xyz|edu|gov|me|info|co|tv)$", name):
        webbrowser.open("https://" + name)
        return "【Executed】 Opened https://%s" % name
    if "/" in name or "http" in name:
        webbrowser.open(name if name.startswith("http") else "https://" + name)
        return "【Executed】 Opened %s" % name
    return None


# ---------------------------------------------------------------------------
# Writing / typing / files
# ---------------------------------------------------------------------------
def write_note(text, filename=None):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path = filename if filename else NOTES_FILE
    if not os.path.isabs(path):
        path = os.path.join(SAGE_FOLDER, path)
    with open(path, "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (ts, text))
    return "【Saved】 Saved to %s" % path


def save_code(text, language="py", filename=None):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    ext_map = {"py": "py", "python": "py", "js": "js", "html": "html",
               "css": "css", "c": "c", "cpp": "cpp", "c++": "cpp",
               "java": "java", "sh": "sh", "bash": "sh", "bat": "bat",
               "json": "json", "txt": "txt", "md": "md"}
    ext = ext_map.get(language.lower(), "py")
    fname = filename or ("code_%s.%s" % (ts, ext))
    if not fname.endswith("." + ext):
        fname += "." + ext
    path = os.path.join(CODE_FOLDER, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return "【Saved】 Saved to %s" % path


def type_text(text):
    """Simulate real keyboard typing into the focused window."""
    try:
        from pynput.keyboard import Controller, Key
    except ImportError:
        return "【Error】 typing module unavailable"
    kb = Controller()
    for line in text.split("\n"):
        for ch in line:
            try:
                kb.type(ch)
            except Exception:
                try:
                    kb.press(ch)
                    kb.release(ch)
                except Exception:
                    pass
        kb.press(Key.enter)
        kb.release(Key.enter)
    return "【Executed】 Typed into your active window."


def copy_to_clipboard(text):
    subprocess.run(["powershell", "-Command", "Set-Clipboard -Value $text"],
                   input=text, text=True, shell=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    return "【Copied】 Copied to clipboard."


def screenshot():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SHOT_FOLDER, "shot_%s.png" % ts)
    img = ImageGrab.grab(all_screens=True)
    img.save(path)
    return "【Snapshot】 Saved %s" % path


def read_file(path):
    if not os.path.isabs(path):
        path = os.path.join(SAGE_FOLDER, path)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return content[:4000]


# ---------------------------------------------------------------------------
# System controls
# ---------------------------------------------------------------------------
def _vol(keycode):
    ctypes.windll.user32.keybd_event(keycode, 0, 0, 0)
    ctypes.windll.user32.keybd_event(keycode, 0, 2, 0)

VOL_UP, VOL_DOWN, VOL_MUTE = 0xAF, 0xAE, 0xAD


def system_command(text):
    t = text.lower()
    if re.search(r"\block\b", t) or "lock computer" in t or "lockscreen" in t:
        ctypes.windll.user32.LockWorkStation()
        return "【Executed】 Workstation locked."
    if "shutdown" in t:
        subprocess.Popen("shutdown /s /t 15", shell=True)
        return "【Executed】 Shutting down in 15 seconds (cancel: shutdown /a)."
    if "cancel shutdown" in t or "abort shutdown" in t:
        subprocess.Popen("shutdown /a", shell=True)
        return "【Executed】 Shutdown cancelled."
    if "restart" in t:
        subprocess.Popen("shutdown /r /t 15", shell=True)
        return "【Executed】 Restarting in 15 seconds."
    if "sleep" in t:
        subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
        return "【Executed】 Going to sleep."
    if "mute" in t:
        _vol(VOL_MUTE)
        return "【Executed】 Muted."
    if "volume up" in t or "volume increase" in t or "louder" in t:
        for _ in range(5):
            _vol(VOL_UP)
        return "【Executed】 Volume up."
    if "volume down" in t or "decrease" in t or "quieter" in t or "lower volume" in t:
        for _ in range(5):
            _vol(VOL_DOWN)
        return "【Executed】 Volume down."
    return None


def get_info(text):
    t = text.lower()
    if re.search(r"\b(time|what.*clock)\b", t):
        return "【Answer】 It is " + datetime.datetime.now().strftime("%I:%M %p") + "."
    if re.search(r"\bdate\b", t):
        return "【Answer】 Today is " + datetime.datetime.now().strftime("%A, %B %d, %Y") + "."
    return None


def list_installed_apps():
    apps = set()
    for lnk in _start_menu_apps():
        apps.add(os.path.splitext(os.path.basename(lnk))[0])
    for key in list(_KNOWN_APPS.keys()) + list(_KNOWN_SITES.keys()):
        apps.add(key)
    return sorted(apps)


def list_code_files():
    files = []
    for root, _, names in os.walk(CODE_FOLDER):
        for name in names:
            if os.path.splitext(name)[1].lower() in {
                ".py", ".js", ".ts", ".html", ".css", ".json",
                ".c", ".cpp", ".java", ".bat", ".ps1", ".sh", ".md"}:
                files.append(os.path.join(root, name))
    extra = []
    for f in os.listdir(DOCS_DIR or os.path.expanduser("~")):
        full = os.path.join(DOCS_DIR or os.path.expanduser("~"), f)
        if os.path.isfile(full) and os.path.splitext(f)[1].lower() in {".py", ".js", ".html", ".ts"}:
            extra.append(full)
    return sorted(set(files + extra))


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def route(text):
    """Return (category, result) or (None, None) if not a local command."""
    t = text.strip().lower()

    # system / info / calc first (cheap, deterministic)
    info = get_info(t)
    if info:
        return ("info", info)

    sysr = system_command(t)
    if sysr:
        return ("system", sysr)

    # open website explicitly
    if re.search(r"\b(open|launch|go to|visit)\s+\S*\.?(com|net|org|io|ai)\b", t) or \
       any(s in t for s in (" youtube", "google", " github", " gmail", " netflix", "reddit", " wikipedia")):
        res = open_website(t)
        if res:
            return ("web", res)

    # open apps
    if re.search(r"^\s*(open|launch|start|run|show)\s+", t):
        res = open_app(t)
        if res:
            return ("app", res)
        res = open_website(t)
        if res:
            return ("web", res)

    # typing dictation
    if re.match(r"^\s*(type|dictate|typing|keys)\s+", t):
        payload = re.sub(r"^\s*(type|dictate|typing|keys)\s+", "", text, flags=re.I).strip()
        if payload:
            return ("type", type_text(payload))

    # calculator
    # calculator
    _num_words = re.compile(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
        r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
        r"thousand|million)\b", re.I)
    if re.search(r"\b(calculate|calc|multiply|addition|minus|times|divided|what is|what's|how much|how much is|solve|percent|%)\b", t) \
       or re.search(r"\d+\s*[+\-*/%^]\s*\d+", t) \
       or (_num_words.search(t) and re.search(r"\b(times|plus|minus|divided|multiplied|percent|over|%|\+|/|\*)\b", t)):
        res = calculate(text)
        if res:
            return ("calc", res)

    # write note
    if re.match(r"^\s*(write|save|remember|note)\s+", t):
        payload = re.sub(r"^\s*(write|save|remember|note)\s+", "", text, flags=re.I).strip()
        if payload:
            return ("note", write_note(payload))

    # code writing
    if re.match(r"^\s*(write|make|generate)\s+(a |an )?(code|script|program)\b", t):
        return ("code_request", text)

    # screenshot
    if "screenshot" in t or "screen shot" in t or "capture" in t:
        return ("screenshot", screenshot())

    # read file
    if re.match(r"^\s*(read|open file|read file)\s+", t):
        fname = re.sub(r"^\s*(read|open file|read file)\s+", "", text, flags=re.I).strip()
        content = read_file(fname)
        if content:
            return ("read", "【File】 %s:\n%s" % (fname, content))

    # copy to clipboard
    if re.match(r"^\s*(copy|clipboard)\s+", t):
        payload = re.sub(r"^\s*(copy|clipboard)\s+", "", text, flags=re.I).strip()
        if payload:
            return ("copy", copy_to_clipboard(payload))

    # list apps
    if re.search(r"\b(list|show).*(apps|applications|programs)\b", t):
        return ("apps", "【Programs】 " + ", ".join(list_installed_apps()[:60]))

    # --- NEW: mouse / keyboard automation ------------------------------
    if re.search(r"\b(scroll|click|double.?click|right.?click|like|dislike|thumbs|"
                 r"new tab|close tab|refresh|reload|go back|back|forward|fullscreen|"
                 r"play|pause|mute|minimize|desktop|show desktop|close window|copy|paste|undo|"
                 r"select all|find|mouse)\b", t):
        res = route_mouse(t)
        if res:
            return ("mouse", res)

    # --- NEW: online search ---------------------------------------------
    if re.match(r"^\s*(search|find|look up|google|research)\s+", t):
        m_brow = re.search(r"\s+in\s+(chrome|firefox|edge|brave|opera|vivaldi)\s*$", t)
        browser = m_brow.group(1) if m_brow else None
        query = re.sub(r"^\s*(search|find|look up|google|research)\s+", "", text, flags=re.I).strip()
        query = re.sub(r"\s+in\s+(chrome|firefox|edge|brave|opera|vivaldi)\s*$", "", query, flags=re.I)
        if query:
            if sage_search.internet_available():
                results = sage_search.search_web(query, max_results=5)
                url, bname = sage_search.open_web_search(query, browser)
                if results:
                    lines = ["【Search Results】 " + query, ""]
                    for title, link, snippet in results:
                        lines.append("* " + title)
                        if snippet:
                            lines.append("  " + snippet)
                    lines.append("")
                    lines.append("Opened via %s: %s" % (bname, url))
                    return ("web", "\n".join(lines[:40]))
                return ("web", "【Opened】 Result for '%s' in %s" % (query, bname))
            hits = sage_search.search_files(query)
            if hits:
                lines = ["【Offline Results】 Found %d local files:" % len(hits)]
                for path, kind in hits[:10]:
                    lines.append("* %s (%s)" % (path, kind))
                return ("files", "\n".join(lines))
            return ("info", "【No Results】 Neither online nor local matches for '%s'." % query)

    if re.match(r"^\s*(search|find)[^:]*\b(offline|local|my files|my pc|computer)\b", t):
        query = re.sub(r"^\s*(search|find)[^:]*\b(offline|local|my files|my pc|computer)\b\s*",
                       "", text, flags=re.I).strip() or t
        hits = sage_search.search_files(query)
        if hits:
            lines = ["【Offline Results】 Found %d local files:" % len(hits)]
            for path, kind in hits[:12]:
                lines.append("* %s  (%s)" % (path, kind))
            return ("files", "\n".join(lines))
        return ("info", "【No Results】 No local files matched '%s'." % query)

    # --- NEW: YouTube / video --------------------------------------------
    if re.search(r"\b(open video|play video|open a video|youtube video|watch video)\b", t) or \
       re.match(r"^\s*(youtube|video)\s+", t):
        m_brow = re.search(r"\s+in\s+(chrome|firefox|edge|brave|opera|vivaldi)\s*$", t)
        browser = m_brow.group(1) if m_brow else None
        query = re.sub(r"^\s*(open|play|watch|show)\s+(a |the )?(video|youtube)?\s*",
                       "", text, flags=re.I).strip()
        query = re.sub(r"^\s*(youtube|video)\s+", "", query, flags=re.I)
        query = re.sub(r"\s+in\s+(chrome|firefox|edge|brave|opera|vivaldi)\s*$", "", query, flags=re.I)
        query = query.strip("\"'.?:")
        if query:
            best = sage_search.search_youtube_and_open(query, browser)
            return ("web", "【Video】 Searching YouTube for '%s'; opened top result: %s" % (query, best))
        url = "https://www.youtube.com/"
        webbrowser.open(url)
        return ("web", "【Opened】 YouTube home.")

    # --- NEW: learning mode ---------------------------------------------
    if re.match(r"^\s*(learn|teach me|study|teach me how)\b", t):
        topic = re.sub(r"^\s*(learn|teach me|study|teach me how|to learn)\s+", "", text, flags=re.I).strip()
        if topic:
            return ("learn", topic)

    if re.search(r"\b(test me|quiz|exam|grade me)\b", t):
        return ("quiz", "")

    # --- NEW: code review ------------------------------------------------
    if re.search(r"\b(review|check|fix|correct|inspect).*(my )?(code|script|program)\b", t):
        return ("code_review", text)

    # show code files
    if re.search(r"\b(show|list).*(code|scripts?|programs?)\b.*(files?|folder)", t):
        files = list_code_files()
        if files:
            return ("files", "【Code Files】\n" + "\n".join("* " + f for f in files[:20]))
        return ("info", "No generated code files yet. Say 'code' then a request.")

    return (None, None)


def sage_file(name):
    if not os.path.isabs(name):
        name = os.path.join(SAGE_FOLDER, name)
    return name


if __name__ == "__main__":
    import sys
    print(route(sys.argv[1]) if len(sys.argv) > 1 else route("calculate 45 * 3 + 2"))