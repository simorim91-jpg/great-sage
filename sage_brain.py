"""Great Sage AI brain - connects to local Ollama with the Great Sage persona."""

import os
import json
import threading
import requests
import subprocess

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("SAGE_MODEL", "qwen2.5:1.5b")

PERSONA = (
    "You are Great Sage, the ultimate intellect companion from "
    "'That Time I Got Reincarnated as a Slime'. You live as an inner voice in "
    "your Master's mind. Address the user as 'Master'. Your ONE purpose is to "
    "make your Master smarter. You always correct mistakes, encourage deep "
    "thinking, and challenge lazy reasoning. You debate respectfully but "
    "firmly, presenting both sides. You notice what your Master is working on "
    "and give concrete help. Be formal, precise, concise and analytical. "
    "Wrap key results in 【...】 like 【Answer】. Be BRIEF: under 70 words, "
    "unless code or deep explanation is requested. Write code, do math, "
    "analyze anything. Reply in the language the Master uses."
)

DEBATE_PERSONA = (
    "You are Great Sage from 'That Time I Got Reincarnated as a Slime', "
    "now in DEBATE mode with your Master. Your goal is to make Master smarter "
    "by challenging their ideas. Take the STRONGEST opposing view to whatever "
    "Master says. Provide real facts and logic, counter their arguments, and "
    "point out flaws, but be respectful and always end with the key insight. "
    "Keep each point under 60 words. Use 【Debate】 brackets for your main point. "
    "Address Master fixedly and stay on topic until Master ends the debate."
)


class SageBrain:
    def __init__(self, model=MODEL):
        self.model = model
        self.session = requests.Session()
        self.history = []
        self.lock = threading.Lock()
        self.persona = PERSONA

    def set_persona(self, persona):
        self.persona = persona
        with self.lock:
            self.history = []

    # -- Ollama availability ------------------------------------------------
    def is_available(self):
        try:
            return self.session.get(OLLAMA_URL + "/api/tags", timeout=5).ok
        except Exception:
            return False

    def ensure_running(self):
        if self.is_available():
            return True
        # try to start ollama app
        for exe in (
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"),
        ):
            if os.path.isfile(exe):
                subprocess.Popen([exe, "serve"], shell=True)
                break
        else:
            subprocess.Popen(["ollama", "serve"], shell=True)
        return False

    def ensure_model(self):
        try:
            data = self.session.get(OLLAMA_URL + "/api/tags", timeout=10).json()
            names = [m["name"] for m in data.get("models", [])]
            if self.model in names:
                return True
            subprocess.Popen(["ollama", "pull", self.model], shell=True)
            return False
        except Exception:
            return False

    def warm(self):
        """Pre-load the model into RAM so first replies are fast."""
        try:
            payload = {"model": self.model, "messages": [
                {"role": "system", "content": self.persona},
                {"role": "user", "content": "Reply with the single word: ready."}],
                "stream": False, "num_predict": 1, "keep_alive": -1}
            with self.session.post(OLLAMA_URL + "/api/chat", json=payload,
                                   stream=True, timeout=300) as r:
                for _ in r.iter_lines(decode_unicode=True):
                    pass
            return True
        except Exception:
            return False

    # -- Core generation ----------------------------------------------------
    def ask(self, prompt, stream_callback=None, stream=True):
        """Ask the sage a question. stream_callback(chunk) receives text pieces."""
        with self.lock:
            self.history.append({"role": "user", "content": prompt})
            messages = [{"role": "system", "content": self.persona}] + self.history[-12:]

            payload = {
                "model": self.model,
                "messages": messages,
                "stream": stream,
                "num_predict": 400,
                "temperature": 0.7,
                "keep_alive": -1,
            }
            full = ""
            with self.session.post(OLLAMA_URL + "/api/chat", json=payload, stream=stream, timeout=300) as r:
                if r.status_code != 200:
                    raise RuntimeError("Ollama replied %s: %s" % (r.status_code, r.text[:200]))
                for raw in r.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    piece = obj.get("message", {}).get("content", "")
                    if piece:
                        full += piece
                        if stream_callback:
                            stream_callback(piece)
            self.history.append({"role": "assistant", "content": full})
            return full

    def generate_code(self, request, stream_callback=None):
        """Generate a code file for the requested task."""
        p = ("Write ONLY working, runnable %s code for the following task. "
             "Return the complete code in a single ``` fenced block with no "
             "extra explanation:\n%s" % (_detect_language(request), request))
        return self.ask(p, stream_callback)

    def clear_history(self):
        with self.lock:
            self.history = []

    # -- Learning mode ------------------------------------------------------
    def learn_outline(self, topic, stream_callback=None):
        """Create a structured study plan for a topic."""
        p = (
            "You are Master's private tutor. The user wants to learn '%s'. "
            "Create a short study plan with:\n"
            "1) What it is (2 lines)\n"
            "2) The key topics in the correct order to learn it (5-7 bullets)\n"
            "3) A suggestion of what kind of YouTube course to watch for it.\n"
            "Keep it under 250 tokens, use 【关键词】 brackets for the topic." % topic
        )
        return self.ask(p, stream_callback)

    def _parse_json_list(self, text):
        import re as _re
        text = text.replace("\n", " ").replace("\t", " ")
        try:
            arr = _re.search(r"\[.*\]", text, _re.S)
            if arr:
                return __import__("json").loads(arr.group())
        except Exception:
            pass
        return []

    def generate_quiz(self, topic, n=4):
        """Return a list of dicts: {q, a}. Uses a fresh non-history request."""
        p = (
            "Create exactly %d beginner quiz questions to test understanding of '%s'. "
            "Return ONLY a JSON array, each object {\"q\": \"question\", \"a\": \"model short answer\"}. "
            "No other text, no markdown fences." % (n, topic)
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": self.persona},
                         {"role": "user", "content": p}],
            "stream": False,
            "num_predict": 700,
        }
        try:
            with self.session.post(OLLAMA_URL + "/api/chat", json=payload, stream=True, timeout=300) as r:
                if r.status_code != 200:
                    return []
                full = ""
                for raw in r.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    full += obj.get("message", {}).get("content", "")
        except Exception:
            return []
        items = self._parse_json_list(full)
        cleaned = []
        for it in items:
            if isinstance(it, dict) and it.get("q"):
                cleaned.append({"q": it["q"].strip(), "a": str(it.get("a", "")).strip()})
        return cleaned[:n]

    def grade_answer(self, q, user_answer):
        """Grade a quiz answer: returns (verdict, feedback)."""
        prompt = (
            "Quiz question: %s\nModel correct answer: %s\nStudent answer: %s\n"
            "Reply with EXACTLY one line: '【Correct】', '【Partial】', or '【Wrong】' "
            "followed by one short sentence of feedback." % (q["q"], q.get("a", ""), user_answer)
        )
        verdict_map = {"correct": "Correct", "partial": "Partial", "wrong": "Wrong"}
        out = self.ask(prompt, stream=False)
        out_l = out.lower()
        for key, label in verdict_map.items():
            if key in out_l:
                return label, out
        return "Partial", out

    # -- Code review --------------------------------------------------------
    def review_code(self, path, stream_callback=None):
        """Read a code file, review and fix it. Returns (corrected_code, summary)."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                code = f.read()
        except Exception as e:
            return None, "Could not read file: %s" % e
        prompt = (
            "Review this code for bugs, style problems and security issues, "
            "then rewrite it as the CORRECTED version. "
            "Output format: one short line of summary, then ```code``` fence "
            "containing the complete corrected code and nothing after the fence.\n\n%s" % code[:6000]
        )
        out = self.ask(prompt, stream_callback)
        # extract fenced code
        import re as _re
        m = _re.search(r"```[a-zA-Z]*\n(.*?)```", out, _re.S)
        corrected = m.group(1) if m else out
        return (corrected, out)


def _detect_language(request):
    r = request.lower()
    for lang, keys in {
        "Python": ["python", "py ", "script"],
        "JavaScript": ["javascript", "js", "node"],
        "HTML/CSS": ["html", "webpage", "website", "css"],
        "Batch": ["batch", "bat ", "cmd"],
        "PowerShell": ["powershell", "ps1"],
        "C": ["c code", " in c"],
        "C++": ["c++", "cpp"],
        "Java": ["java"],
        "Bash": ["bash", "shell script"],
    }.items():
        if any(k in r for k in keys):
            return lang
    return "Python"


if __name__ == "__main__":
    b = SageBrain()
    print("available:", b.is_available())
    print(b.ask("Hello"))