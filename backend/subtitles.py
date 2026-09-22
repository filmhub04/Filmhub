from babelfish import Language
from subliminal import download_best_subtitles, save_subtitles, scan_video

import re as _re

_ARABIC = _re.compile(r"[\u0600-\u06FF]")


def _lang_list(languages):
    langs = set()
    for code in languages:
        try:
            langs.add(Language(code))
        except Exception:
            pass
    if not langs:
        try:
            langs.add(Language("fra"))
        except Exception:
            pass
    return list(langs)


def _arabic_score(text):
    if not text:
        return 0.0
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    return len(_ARABIC.findall(text)) / len(letters)


def fetch_arabic_by_title(video_path):
    try:
        from subliminal.providers.opensubtitles import OpenSubtitlesProvider

        video = scan_video(video_path)
        if video is None:
            return {"status": "error", "error": "video introuvable"}
        wanted = Language("ara")

        candidates = []
        with OpenSubtitlesProvider() as provider:
            provider.initialize()
            try:
                candidates += provider.query(
                    languages={wanted}, moviehash=video.hashes.get("opensubtitles")
                )
            except Exception:
                pass
            try:
                candidates += provider.query(languages={wanted}, query=video.title)
            except Exception:
                pass
        best = None
        best_score = 0.0
        for sub in candidates or []:
            try:
                sub.download()
                text = sub.content.decode(sub.encoding or "utf-8", errors="replace")
                score = _arabic_score(text)
                if score > best_score:
                    best_score, best = score, sub
            except Exception:
                continue
        if best is None or best_score < 0.5:
            return {"status": "ok", "downloaded": 0, "reason": "aucun titre arabe fiable"}
        count = save_subtitles(video, [best])
        return {"status": "ok", "downloaded": count, "score": round(best_score, 2)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def fetch_best(video_path, languages=("fra", "ara")):
    results = {}
    for code in {str(c) for c in languages}:
        try:
            if code == "ara":
                results[code] = fetch_arabic_by_title(video_path)
            else:
                results[code] = fetch_subtitles(video_path, [code])
        except Exception as exc:
            results[code] = {"status": "error", "error": str(exc)}
    return results


def fetch_subtitles(video_path, languages=('fra', 'ara')):
    try:
        video = scan_video(video_path)
        if video is None:
            return {"status": "error", "error": "video not found"}
        lang_list = _lang_list(languages)
        subtitles = download_best_subtitles({video}, set(lang_list))
        if video in subtitles and subtitles[video]:
            count = save_subtitles(video, subtitles[video])
            return {"status": "ok", "downloaded": count}
        return {"status": "ok", "downloaded": 0}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}