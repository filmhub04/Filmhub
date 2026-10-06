import os
import re
import threading
import time
from datetime import datetime

import requests

from backend import db, library, settings

_state = {
    "running": False,
    "last_run": None,
    "last_summary": "",
    "current_item": None,
    "current_done": 0,
    "current_total": 0,
    "pulled": [],
    "skipped": [],
    "errors": [],
}

_lock = threading.Lock()
_worker_thread = None
_stop = threading.Event()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def render_library():
    url = settings.sync_url() + "/api/library"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data.get("items") or []


def _local_files():
    seen = {}
    for root in library._scan_roots():
        try:
            if not root.exists():
                continue
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in library.VIDEO_EXTS:
                    seen.setdefault(p.name.lower(), p)
        except Exception:
            continue
    return seen


def _probe_total(url):
    r = requests.get(url, headers={"Range": "bytes=0-0"}, timeout=60, stream=True)
    try:
        if r.status_code in (200, 206):
            cr = r.headers.get("content-range")
            if cr and "/" in cr:
                try:
                    return int(cr.split("/")[1])
                except Exception:
                    pass
            try:
                return int(r.headers.get("content-length") or 0)
            except Exception:
                return 0
        raise IOError("HTTP " + str(r.status_code))
    finally:
        r.close()


def pull_resumable(url, dest, total):
    done = os.path.getsize(dest) if os.path.exists(dest) else 0
    if total and done >= total:
        return total
    with open(dest, "ab") as f:
        while True:
            headers = {"Range": "bytes=%d-" % done} if done else {}
            try:
                with requests.get(url, headers=headers, timeout=120, stream=True) as r:
                    if r.status_code not in (200, 206):
                        raise IOError("HTTP " + str(r.status_code))
                    cr = r.headers.get("content-range")
                    if cr and "/" in cr:
                        try:
                            total = int(cr.split("/")[1])
                        except Exception:
                            pass
                    chunks = 0
                    for chunk in r.iter_content(4 << 20):
                        if not chunk:
                            continue
                        f.write(chunk)
                        f.flush()
                        done += len(chunk)
                        chunks += 1
                        _state["current_done"] = done
                        _state["current_total"] = total
                    if total and done >= total:
                        break
                    if chunks == 0:
                        raise IOError("no data")
            except Exception:
                time.sleep(3)
                continue
    return done


def _force_safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (name or "").strip())
    return name or "film.mp4"


def _register_meta(filename, title, poster, genres):
    stem = os.path.splitext(filename)[0]
    db.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
        (stem, title or stem),
    )
    db.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
        (stem + "::poster", poster or ""),
    )
    db.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
        (stem + "::genres", "|".join(genres or [])),
    )


def sync_once():
    with _lock:
        if _state["running"]:
            return {"status": "busy"}
        _state["running"] = True
        results = {"pulled": [], "skipped": [], "errors": []}
        try:
            _state["current_item"] = None
            items = render_library()
            local = _local_files()
            base = settings.downloads_dir()
            base.mkdir(parents=True, exist_ok=True)
            for item in items:
                title = item.get("title") or ""
                filename = _force_safe_name(item.get("filename") or item.get("title") or "film")
                if not os.path.splitext(filename)[1]:
                    filename += ".mp4"
                dest = base / filename
                _state["current_item"] = title or filename
                if dest.exists() or filename.lower() in local:
                    results["skipped"].append(title or filename)
                    continue
                url = settings.sync_url() + "/api/file/%s/download" % item.get("id")
                try:
                    total = _probe_total(url)
                    if total <= 0:
                        raise IOError("taille inconnue")
                    part = dest.with_name(dest.name + ".syncpart")
                    done = pull_resumable(url, str(part), total)
                    if done < total:
                        raise IOError("transfert incomplet %d/%d" % (done, total))
                    os.replace(str(part), str(dest))
                    _register_meta(filename, title, item.get("poster") or "", item.get("genres") or [])
                    results["pulled"].append(title or filename)
                except Exception as exc:
                    results["errors"].append(title or filename + " : " + str(exc))
                finally:
                    part = base / (filename + ".syncpart")
                    part2 = dest.with_name(dest.name + ".syncpart")
                    try:
                        if part.exists():
                            part.unlink()
                        if part2.exists():
                            part2.unlink()
                    except Exception:
                        pass
            _state["last_run"] = _now()
            _state["last_summary"] = (
                "%d rapatrié(s), %d déjà présent(s), %d erreur(s)"
                % (len(results["pulled"]), len(results["skipped"]), len(results["errors"]))
            )
            _state["pulled"] = results["pulled"]
            _state["skipped"] = results["skipped"]
            _state["errors"] = results["errors"]
            return {"status": "ok", **results}
        except Exception as exc:
            _state["last_run"] = _now()
            _state["last_summary"] = "Erreur : " + str(exc)
            _state["errors"] = [str(exc)]
            return {"status": "error", "error": str(exc)}
        finally:
            _state["running"] = False
            _state["current_item"] = None
            _state["current_done"] = 0
            _state["current_total"] = 0


def worker():
    interval = settings.sync_interval()
    while not _stop.wait(interval):
        try:
            sync_once()
        except Exception:
            pass
        interval = settings.sync_interval()


def start():
    global _worker_thread
    stop()
    if not settings.auto_sync_enabled():
        return
    _stop.clear()
    _worker_thread = threading.Thread(target=worker, daemon=True)
    _worker_thread.start()


def stop():
    global _worker_thread
    _stop.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=2)
        _worker_thread = None


def status():
    s = dict(_state)
    s["enabled"] = bool(settings.auto_sync_enabled())
    s["interval"] = settings.sync_interval()
    s["sync_url"] = settings.sync_url()
    try:
        items = render_library()
        local = _local_files()
        name = lambda it: (it.get("filename") or it.get("title") or "").lower()
        s["render_count"] = len(items)
        s["missing_count"] = sum(
            1 for it in items if name(it) and name(it) not in local
        )
    except Exception:
        s["render_count"] = 0
        s["missing_count"] = 0
    return s