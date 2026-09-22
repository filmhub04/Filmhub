import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

YTS_MIRRORS = ["https://yts.mx", "https://yts.rs", "https://yts.lt", "https://yts.do"]
X1337_MIRRORS = ["https://1337x.to", "https://1337x.st", "https://x1337x.ws", "https://x1337x.eu"]
EXCLUDE_PATTERNS = [r's\d{1,2}e\d{1,2}', r'season', r'ova', r'mp3', r'epub', r'pdf', r'mobi', r'soundtrack', r'psx', r'flac']
BAD_QUALITY_PATTERNS = [
    r'\bcam\b', r'hd[-\s]?cam', r'\btc\b', r'\bts\b(?=\s)', r'telesync',
    r'screener', r'\bscr\b', r'dvdscr', r'telecine', r'\bhdtc\b', r'\bsdtc\b',
    r'\bhq\b', r'\bhd-?ts\b', r'\bld\b', r'\bppv\b', r'\bbluray-?cam\b',
]
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
MAX_PER_SOURCE = 10
CACHE_TTL = 600

session = requests.Session()
session.headers.update(HEADERS)

_cache = {}
_cache_lock = threading.Lock()


def get_cached(query, year):
    with _cache_lock:
        entry = _cache.get((query, year))
        if entry and time.time() - entry[0] < CACHE_TTL:
            return entry[1]
        return None


def set_cache(query, year, results):
    with _cache_lock:
        _cache[(query, year)] = (time.time(), results)


def is_valid_item(title, query, target_year=None):
    title_lower = title.lower()
    if any(re.search(pat, title_lower) for pat in EXCLUDE_PATTERNS):
        return False
    if any(re.search(pat, title_lower) for pat in BAD_QUALITY_PATTERNS):
        return False
    if query.lower() not in title_lower:
        return False
    if target_year:
        year_str = str(target_year)
        detected_years = re.findall(r'\b(19\d\d|20[0-2]\d)\b', title)
        if detected_years and year_str not in detected_years:
            return False
    return True


def search_yts(query, target_year=None):
    results = []
    encoded_query = quote(query)
    for base_url in YTS_MIRRORS:
        url = f"{base_url}/api/v2/list_movies.json?query_term={encoded_query}"
        try:
            response = session.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                movies = data.get('data', {}).get('movies', [])
                for movie in movies:
                    title = movie.get('title')
                    year = movie.get('year')
                    if not is_valid_item(title, query, target_year):
                        continue
                    trailer_code = movie.get('yt_trailer_code') or ''
                    for torrent in movie.get('torrents', []):
                        quality = torrent.get('quality')
                        torrent_type = torrent.get('type')
                        hash_val = torrent.get('hash')
                        magnet = f"magnet:?xt=urn:btih:{hash_val}&dn={quote(title)}+{quality}&tr=udp://open.demonii.com:1337/announce&tr=udp://tracker.openbittorrent.com:80"
                        results.append({
                            'source': 'YTS',
                            'title': f"{title} ({year}) [{quality}] [{torrent_type}]",
                            'size': torrent.get('size'),
                            'seeders': int(torrent.get('seeds', 0)),
                            'poster': movie.get('medium_cover_image'),
                            'year': year,
                            'rating': movie.get('rating'),
                            'summary': (movie.get('summary') or '').strip(),
                            'genres': movie.get('genres') or [],
                            'runtime': movie.get('runtime'),
                            'trailer': f"https://www.youtube.com/watch?v={trailer_code}" if trailer_code else None,
                            'link': magnet
                        })
                if results:
                    break
        except requests.exceptions.RequestException:
            continue
    results.sort(key=lambda x: x.get('seeders') or 0, reverse=True)
    return results[:MAX_PER_SOURCE]


def search_tpb(query, target_year=None):
    results = []
    encoded_query = quote(query)
    url = f"https://apibay.org/q.php?q={encoded_query}"
    try:
        response = session.get(url, timeout=6)
        if response.status_code == 200:
            items = response.json()
            for item in items:
                if item.get('id') == '0' or item.get('name') == 'No results found':
                    continue
                title = item.get('name')
                if not is_valid_item(title, query, target_year):
                    continue
                size_bytes = int(item.get('size', 0))
                if size_bytes > 15 * 1024 ** 3:
                    continue
                size_gb = round(size_bytes / (1024 ** 3), 2)
                size_str = f"{size_gb} GB" if size_gb >= 1 else f"{round(size_bytes / (1024 ** 2), 1)} MB"
                info_hash = item.get('info_hash')
                magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={quote(title)}&tr=udp://tracker.coppersurfer.tk:6969/announce&tr=udp://open.demonii.com:1337/announce"
                results.append({
                    'source': 'PirateBay',
                    'title': title,
                    'size': size_str,
                    'seeders': int(item.get('seeders', 0)),
                    'poster': None,
                    'year': None,
                    'rating': None,
                    'summary': None,
                    'genres': [],
                    'runtime': None,
                    'trailer': None,
                    'link': magnet
                })
    except Exception:
        pass
    results.sort(key=lambda x: x.get('seeders') or 0, reverse=True)
    return results[:MAX_PER_SOURCE]


def fetch_1337x_magnet(base_url, detail_path):
    try:
        res = session.get(f"{base_url}{detail_path}", timeout=4)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            magnet_elem = soup.select_one('a[href^="magnet:"]')
            return magnet_elem['href'] if magnet_elem else None
    except requests.exceptions.RequestException:
        pass
    return None


def search_1337x(query, target_year=None):
    results = []
    encoded_query = quote(query)
    for base_url in X1337_MIRRORS:
        url = f"{base_url}/search/{encoded_query}/1/"
        try:
            response = session.get(url, timeout=5)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                rows = soup.select('table.table-list tbody tr')
                for row in rows[:8]:
                    name_elem = row.select_one('td.coll-1 a:nth-of-type(2)')
                    seeders_elem = row.select_one('td.coll-2')
                    size_elem = row.select_one('td.coll-4')
                    if name_elem and seeders_elem and size_elem:
                        title = name_elem.text.strip()
                        if not is_valid_item(title, query, target_year):
                            continue
                        seeders = int(seeders_elem.text.strip().replace(',', ''))
                        size = size_elem.contents[0].strip() if size_elem.contents else "N/A"
                        magnet_link = fetch_1337x_magnet(base_url, name_elem['href'])
                        if magnet_link:
                            results.append({
                                'source': '1337x',
                                'title': title,
                                'size': size,
                                'seeders': seeders,
                                'poster': None,
                                'year': None,
                                'rating': None,
                                'summary': None,
                                'genres': [],
                                'runtime': None,
                                'trailer': None,
                                'link': magnet_link
                            })
                if results:
                    break
        except requests.exceptions.RequestException:
            continue
    results.sort(key=lambda x: x.get('seeders') or 0, reverse=True)
    return results[:MAX_PER_SOURCE]


def search_all(query, year=None, quality=None):
    cached = get_cached(query, year)
    if cached is not None:
        results = cached
    else:
        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(search_yts, query, year): 'YTS',
                executor.submit(search_tpb, query, year): 'TPB',
                executor.submit(search_1337x, query, year): '1337x',
            }
            for future in as_completed(futures):
                try:
                    results.extend(future.result())
                except Exception:
                    continue
        results.sort(key=lambda x: x.get('seeders') or 0, reverse=True)
        set_cache(query, year, results)
    if quality:
        quality_lower = str(quality).lower()
        results = [r for r in results if quality_lower in str(r.get('title', '')).lower()]
    return results