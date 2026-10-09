"""Search - online (web + YouTube) and offline (local files)."""

import os
import re
import glob
import webbrowser
import urllib.request, urllib.parse, urllib.error

import requests
from bs4 import BeautifulSoup
from sage_utils import open_url

SAGE_FOLDER = os.path.join(os.path.expanduser("~"), "Documents", "GreatSage")
SEARCH_FOLDERS = [
    os.path.join(os.path.expanduser("~"), "Documents"),
    os.path.join(os.path.expanduser("~"), "Desktop"),
    os.path.join(os.path.expanduser("~"), "Downloads"),
    SAGE_FOLDER,
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _fetch(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def internet_available():
    try:
        urllib.request.urlopen("https://www.google.com", timeout=4)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Online search
# ---------------------------------------------------------------------------
def search_web(query, max_results=6):
    """Return list of (title, url, snippet). Tries Google then DuckDuckGo."""
    results = _search_google(query, max_results)
    if results:
        return results
    results = _search_duckduckgo(query, max_results)
    return results or []


def _search_google(query, max_results):
    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
    try:
        page = _fetch(url, timeout=6)
    except Exception:
        return []
    soup = BeautifulSoup(page, "html.parser")
    results = []
    for node in soup.select("a")[:200]:
        h3 = node.select_one("h3")
        if not h3 or len(results) >= max_results:
            continue
        title = h3.get_text(strip=True)
        href = node.get("href", "")
        m = re.search(r"/url\?q=([^&]+)", href)
        link = urllib.parse.unquote(m.group(1)) if m else href
        if not link.startswith("http"):
            continue
        parent = node
        snippet = ""
        sib = node.find_next_sibling()
        if sib:
            sn = sib.select_one(".VwiC3b") or sib
            snippet = sn.get_text(strip=True)[:180]
        results.append((title, link, snippet))
    # de-dup
    seen, uniq = set(), []
    for t, l, s in results:
        if l in seen:
            continue
        seen.add(l)
        uniq.append((t, l, s))
    return uniq[:max_results]


def _search_bing(query, max_results):
    url = "https://www.bing.com/search?q=" + urllib.parse.quote(query)
    try:
        page = _fetch(url, timeout=12)
    except Exception:
        return []
    soup = BeautifulSoup(page, "html.parser")
    results = []
    for li in soup.select("li.b_algo")[:max_results]:
        a = li.select_one("h2 a")
        if not a:
            continue
        title = a.get_text(strip=True)
        link = a.get("href", "")
        snippet = ""
        p = li.select_one(".b_caption p") or li.select_one("p")
        if p:
            snippet = p.get_text(strip=True)[:180]
        if title and link.startswith("http"):
            results.append((title, link, snippet))
    return results


def _search_duckduckgo(query, max_results):
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        page = _fetch(url, timeout=6)
    except Exception:
        return []
    soup = BeautifulSoup(page, "html.parser")
    results = []
    for a in soup.select("a.result__a")[:max_results]:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        m = re.search(r"uddg=([^&]+)", href)
        link = urllib.parse.unquote(m.group(1)) if m else href
        parent = a.find_parent("div", class_="result")
        snippet = ""
        if parent:
            sn = parent.select_one(".result__snippet")
            if sn:
                snippet = sn.get_text(strip=True)[:180]
        results.append((title, link, snippet))
    return results


def open_web_search(query, browser=None):
    """Open the search engine in the browser of choice."""
    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
    name = open_url(url, browser)
    return url, name


def search_youtube(query, max_results=6, browser=None):
    """Open YouTube search results and return a few titles/links."""
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    open_url(url, browser)
    try:
        page = _fetch(url)
        titles = re.findall(r'"title":\{"runs":\[\{"text":"(.*?)"\}', page)
        videos = re.findall(r'"videoId":"([A-Za-z0-9_\-]{11})"', page)
        seen, links = set(), []
        for title, vid in zip(titles, videos):
            if vid in seen:
                continue
            seen.add(vid)
            links.append(("https://www.youtube.com/watch?v=" + vid, title))
            if len(links) >= max_results:
                break
        return links or []
    except Exception:
        return []


def search_youtube_and_open(query, browser=None):
    results = search_youtube(query, browser)
    if not results:
        open_url("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query), browser)
        return "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    return results[0][0]


# ---------------------------------------------------------------------------
# Offline file search
# ---------------------------------------------------------------------------
_TEXT_EXTS = {".txt", ".md", ".py", ".js", ".ts", ".html", ".css", ".json",
              ".csv", ".log", ".bat", ".ps1", ".c", ".cpp", ".java", ".sh",
              ".ini", ".cfg", ".yml", ".yaml"}


def search_files(query, folders=None, max_results=15, content=True):
    """Search local files by name and optionally by content. Offline."""
    folders = folders or SEARCH_FOLDERS
    query = query.lower()
    hits = []
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for root, _, files in os.walk(folder):
            for name in files:
                if len(hits) >= max_results:
                    break
                path = os.path.join(root, name)
                try:
                    if query in name.lower():
                        hits.append((path, "filename"))
                        continue
                    if content and os.path.splitext(name)[1].lower() in _TEXT_EXTS:
                        if os.path.getsize(path) > 2_000_000:
                            continue
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            if query in f.read(200_000).lower():
                                hits.append((path, "content"))
                except Exception:
                    continue
            if len(hits) >= max_results:
                break
    return hits


def open_path(path):
    os.startfile(path)
    return "Opened " + path


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "python"
    r = search_web(q, 3)
    print(r or "no result")