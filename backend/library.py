import re
import urllib.parse
import zlib
from pathlib import Path

from backend import db
from backend.downloader import DOWNLOADS_DIR

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov")
LANG_ALPHA3 = {
    "eng": "eng", "en": "eng", "fra": "fra", "fr": "fra",
    "ara": "ara", "ar": "ara", "spa": "spa", "es": "spa",
    "deu": "deu", "de": "deu", "ita": "ita", "it": "ita",
    "por": "por", "pt": "por", "rus": "rus", "ru": "rus",
    "tur": "tur", "tr": "tur", "hin": "hin", "hi": "hin",
    "zho": "zho", "chi": "zho", "jpn": "jpn", "ja": "jpn",
    "kor": "kor", "ko": "kor",
    "pol": "pol", "pl": "pol", "nld": "nld", "nl": "nld",
    "swe": "swe", "sv": "swe", "heb": "heb", "he": "heb",
    "vie": "vie", "vi": "vie", "ind": "ind", "id": "ind",
}


def _alpha3(code):
    code = (code or "").lower()
    return LANG_ALPHA3.get(code, code[:3])


def _stable_id(path):
    digest = zlib.crc32(str(path).encode("utf-8")) & 0xFFFFFFFF
    return digest


def _extract_year(text):
    m = re.search(r"\b(19|20)\d{2}\b", text or "")
    return int(m.group(0)) if m else 0


def _find_subtitles(video):
    subtitles = []
    basename = video.stem.lower()
    for child in sorted(video.parent.glob("*")):
        if not child.is_file() or child.suffix.lower() not in (".srt", ".vtt"):
            continue
        m = re.match(r"^" + re.escape(video.stem) + r"\.([a-z]{2,3})\.srt$", child.name, re.IGNORECASE)
        if not m:
            if child.stem.lower() == basename and child.suffix.lower() == ".srt":
                lang = "eng"
            else:
                continue
        else:
            lang = m.group(1)
        code3 = _alpha3(lang)
        fid = _stable_id(video)
        subtitles.append({
            "lang": code3,
            "alpha3": code3,
            "url": f"/api/library/{fid}/subtitle/{code3}",
        })
    return subtitles


def scan_library():
    items = []
    if not DOWNLOADS_DIR.exists():
        return items
    try:
        files = []
        for p in DOWNLOADS_DIR.rglob("*"):
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                files.append(p)
        files.sort(key=lambda p: p.stat().st_mtime or 0, reverse=True)
    except Exception:
        return items
    meta = {r["key"]: r.get("value", "") for r in db.query("SELECT key, value FROM meta")}
    registered = {k for k, v in meta.items() if "::" not in k and v}
    for video in files:
        stem = video.stem
        if stem not in registered:
            continue
        title = meta.get(stem) or stem
        poster = meta.get(stem + "::poster") or ""
        size = 0
        try:
            size = video.stat().st_size
        except Exception:
            pass
        fid = _stable_id(video)
        genres = (meta.get(stem + "::genres") or "").split("|")
        try:
            added = int(video.stat().st_mtime)
        except Exception:
            added = 0
        items.append({
            "id": fid,
            "title": title,
            "filename": video.name,
            "size": size,
            "poster": poster,
            "genres": [g for g in genres if g],
            "year": _extract_year(title) or _extract_year(video.name),
            "favorite": meta.get(stem + "::fav") == "1",
            "added": added,
            "subtitles": _find_subtitles(video),
            "stream_url": f"/api/stream/{fid}",
        })
    return items


def toggle_favorite(fid):
    path = find_file_by_id(fid)
    if path is None:
        return None
    key = path.stem + "::fav"
    rows = db.query("SELECT value FROM meta WHERE key=?", (key,))
    current = bool(rows) and (rows[0].get("value") or "") == "1"
    db.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
        (key, "0" if current else "1"),
    )
    return not current


def find_file_by_id(fid):
    if not DOWNLOADS_DIR.exists():
        return None
    for p in DOWNLOADS_DIR.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            if _stable_id(p) == fid:
                return p
    return None


def find_item_by_id(fid):
    for item in scan_library():
        if item["id"] == fid:
            return item
    return None


_ALPHA2 = {
    "fra": "fr", "eng": "en", "ara": "ar", "spa": "es", "deu": "de",
    "ita": "it", "por": "pt", "rus": "ru", "tur": "tr", "hin": "hi",
    "zho": "zh", "jpn": "ja", "kor": "ko", "pol": "pl", "nld": "nl",
    "swe": "sv", "heb": "he", "vie": "vi", "ind": "id",
}


def srt_path_for(video_path, lang):
    video = Path(video_path)
    variants = {lang, _ALPHA2.get(lang, lang)}
    candidates = []
    for code in sorted(variants):
        candidates += [
            video.parent / f"{video.stem}.{code}.srt",
            video.parent / f"{video.stem}.{code}.vtt",
        ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if _alpha3(lang) in ("eng", "en"):
        generic = video.parent / f"{video.stem}.srt"
        if generic.exists():
            return generic
    return None


def delete_item(fid):
    path = find_file_by_id(fid)
    if path is None:
        return False
    try:
        root = DOWNLOADS_DIR.resolve()
        parent = path.parent.resolve()
        if parent != root and root not in parent.parents:
            return False
        stem = path.stem
        for sibling in list(parent.glob(f"{stem}*")):
            if sibling.is_file():
                try:
                    sibling.unlink()
                except OSError:
                    pass
        for key in (stem, stem + "::poster"):
            db.execute("DELETE FROM meta WHERE key=?", (key,))
        return True
    except Exception:
        return False


def srt_to_vtt(srt_text):
    vtt = "WEBVTT\n\n"
    for raw in srt_text.replace("\r\n", "\n").split("\n"):
        raw = raw.replace("\ufeff", "")
        if "-->" in raw:
            raw = re.sub(r"(\d+:\d+:\d+),(\d+)", r"\1.\2", raw)
            vtt += raw + "\n"
        elif raw.strip():
            vtt += raw + "\n"
        else:
            vtt += "\n"
    return vtt