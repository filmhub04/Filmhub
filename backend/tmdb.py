import os
import threading
import time
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent.parent
_KEY_FILE = ROOT / "tmdb_key.txt"

BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/w500"
LOGO = "https://image.tmdb.org/t/p/w92"
YT = "https://www.youtube.com/watch?v="
_CACHE_TTL = 21600

_cache = {}
_cache_lock = threading.Lock()

_TIER_FR = {
    "free": "Gratuit",
    "ads": "Avec pub",
    "flatrate": "Abonnement",
    "buy": "Achat",
    "rent": "Location",
}

_PROVIDERS = {
    "netflix": "https://www.netflix.com/search?q={t}",
    "amazon prime video": "https://www.primevideo.com/search/ref=atv_nb_sr/?phrase={t}",
    "disney plus": "https://www.disneyplus.com/search/{t}",
    "apple tv": "https://tv.apple.com/search?term={t}",
    "canal+": "https://www.canalplus.com/recherche/{t}",
    "max": "https://www.max.com/search?q={t}",
    "hbo": "https://www.max.com/search?q={t}",
    "paramount": "https://www.paramountplus.com/search/?keyword={t}",
    "youtube": "https://www.youtube.com/results?search_query={t}",
    "google play": "https://play.google.com/store/search?q={t}&c=movies",
    "microsoft": "https://www.microsoft.com/en-gb/search/shop/movies?q={t}",
    "pluto": "https://pluto.tv/en/search?q={t}",
    "tubi": "https://tubitv.com/search/{t}",
    "plex": "https://www.plex.tv/search/?q={t}",
    "arte": "https://www.arte.tv/fr/videos/search/?q={t}",
    "filmo": "https://www.filmo.tv/recherche/{t}",
    "france tv": "https://www.france.tv/recherche/?q={t}",
    "molotov": "https://www.molotov.tv/recherche?q={t}",
}


class TMDBError(Exception):
    pass


def _region():
    return os.environ.get("TMDB_REGION", "FR").strip().upper() or "FR"


def _key_from_file():
    try:
        values = _KEY_FILE.read_text(encoding="utf-8").splitlines()
        for line in values:
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    except Exception:
        pass
    return ""


def key():
    value = os.environ.get("TMDB_API_KEY", "").strip()
    if value:
        return value
    return _key_from_file()


def _cached(kind, sig, ttl=_CACHE_TTL):
    path, params = sig
    ckey = (kind, path, tuple(sorted(params.items())))
    now = time.time()
    with _cache_lock:
        entry = _cache.get(ckey)
        if entry and entry[0] > now:
            return entry[1]
    api_key = key()
    if not api_key:
        raise TMDBError(
            "Clé TMDB manquante. Créez une clé API gratuite sur "
            "https://www.themoviedb.org/settings/api puis collez-la dans le fichier "
            "tmdb_key.txt (à côté de run.py) ou définissez la variable TMDB_API_KEY."
        )
    path, params = sig
    full = dict(params)
    full["api_key"] = api_key
    try:
        resp = requests.get(BASE + path, params=full, timeout=20)
    except requests.RequestException as exc:
        raise TMDBError("TMDB injoignable : " + type(exc).__name__)
    if resp.status_code == 401:
        raise TMDBError("Clé TMDB invalide. Vérifiez TMDB_API_KEY.")
    if resp.status_code != 200:
        raise TMDBError("TMDB a répondu " + str(resp.status_code))
    data = resp.json()
    with _cache_lock:
        _cache[ckey] = (now + ttl, data)
    return data


def search(query, page=1):
    data = _cached("search", ("/search/movie", {
        "query": query,
        "language": "fr-FR",
        "page": str(max(1, page)),
        "include_adult": "false",
    }), ttl=1800)
    items = []
    for m in data.get("results", []):
        title = m.get("title") or ""
        if not title:
            continue
        items.append({
            "tmdb_id": m.get("id"),
            "title": title,
            "year": (m.get("release_date") or "")[:4] or None,
            "poster": (IMG + m["poster_path"]) if m.get("poster_path") else "",
            "rating": round(float(m.get("vote_average") or 0), 1),
            "overview": m.get("overview") or "",
        })
    return {
        "items": items[:24],
        "page": max(1, page),
        "total": data.get("total_results") or 0,
        "region": _region(),
    }


def _provider_url(name, title, tmdb_id):
    t = quote(title)
    needle = (name or "").lower()
    for pat, url in _PROVIDERS.items():
        if pat in needle or needle in pat:
            return url.format(t=t)
    return f"https://www.themoviedb.org/movie/{tmdb_id}/watch?locale={_region()}&provider={quote(name or '')}"


def movie(tmdb_id):
    d = _cached("movie", (f"/movie/{tmdb_id}", {
        "language": "fr-FR",
        "append_to_response": "watch/providers,credits,videos",
    }))
    title = d.get("title") or d.get("name") or ""
    genres = [g.get("name") for g in (d.get("genres") or []) if g.get("name")]

    cast = []
    director = ""
    credits = d.get("credits") or {}
    for p in (credits.get("cast") or [])[:10]:
        if p.get("name"):
            cast.append(p["name"])
    for p in (credits.get("crew") or []):
        if (p.get("job") or "") == "Director" and p.get("name"):
            director = p["name"]
            break

    trailer = ""
    for v in ((d.get("videos") or {}).get("results") or []):
        if (v.get("site") or "") != "YouTube" or (v.get("key") or "") == "":
            continue
        if (v.get("type") or "").lower() in ("trailer", "teaser"):
            trailer = YT + v["key"]
            break

    region = _region()
    providers = []
    wp = ((d.get("watch/providers") or {}).get("results") or {}).get(region)
    if not wp:
        wp = ((d.get("watch/providers") or {}).get("results") or {}).get("US")
    if wp:
        for tier in ("free", "ads", "flatrate", "buy", "rent"):
            for pr in wp.get(tier) or []:
                pname = (pr.get("provider_name") or "").strip()
                if not pname:
                    continue
                providers.append({
                    "name": pname,
                    "logo": (LOGO + pr["logo_path"]) if pr.get("logo_path") else "",
                    "tier": _TIER_FR.get(tier, tier),
                    "url": _provider_url(pname, title, tmdb_id),
                })

    return {
        "tmdb_id": tmdb_id,
        "title": title,
        "year": (d.get("release_date") or "")[:4] or None,
        "runtime": d.get("runtime"),
        "rating": round(float(d.get("vote_average") or 0), 1),
        "overview": d.get("overview") or "",
        "tagline": d.get("tagline") or "",
        "genres": genres,
        "cast": cast,
        "director": director,
        "trailer": trailer,
        "poster": (IMG + d["poster_path"]) if d.get("poster_path") else "",
        "backdrop": (IMG + d["backdrop_path"]) if d.get("backdrop_path") else "",
        "imdb_id": d.get("imdb_id"),
        "region": region,
        "providers": providers,
    }