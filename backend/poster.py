import re
import threading

from backend import search
from backend.search import session

_cache = {}
_cache_lock = threading.Lock()

ART_CACHE_TTL = 12 * 3600

_NOISE = re.compile(
    r"\(\d{4}\)|\[[^\]]*\]|\.(19\d\d|20\d\d)|\((19\d\d|20\d\d)\)|"
    r"\b(720p|1080p|2160p|4k|x264|x265|hevc|bluray|blu-ray|hdtv|web-?dl|webrip|brrip|h264|dts|ac3|"
    r"yify|yts\.?ag|extratorrent|ettv|rar|0sec|proper|repack|french|multi|vf|vff|trufrench)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(19\d\d|20[0-2]\d)\b")


def clean_title(title):
    t = str(title or "")
    t = _NOISE.sub(" ", t)
    t = _YEAR.sub(" ", t)
    t = re.sub(r"[._]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^[\W_]+|[\W_]+$", "", t)
    return t[:90] or str(title or "")


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def find_poster(title, year=None):
    key = clean_title(title)
    with _cache_lock:
        entry = _cache.get(key)
        if entry:
            return entry[1]
    term = f"{key} {year}" if year else key
    art = None
    try:
        response = session.get(
            "https://itunes.apple.com/search",
            params={"term": term, "limit": 8},
            timeout=6,
        )
        if response.status_code == 200:
            movies = [
                x
                for x in (response.json().get("results") or [])
                if str(x.get("kind") or "").lower() in ("movie", "feature-movie")
            ]
            key_norm = _norm(key)

            def sort_key(x):
                name_norm = _norm(x.get("trackName"))
                if name_norm == key_norm:
                    return 0
                if key_norm in name_norm or name_norm in key_norm:
                    return 1
                return 2

            movies.sort(key=sort_key)
            for item in movies:
                candidate = (item.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
                if "Music" in candidate:
                    continue
                if candidate:
                    art = candidate
                    break
    except Exception:
        pass
    if not art:
        try:
            yts_results = search.search_yts(key, year)
            if yts_results:
                art = yts_results[0].get("poster") or None
        except Exception:
            pass
    with _cache_lock:
        _cache[key] = (None, art)
    return art