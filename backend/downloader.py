import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from backend import db

DOWNLOADS_DIR = Path.home() / "Downloads" / "FILMS"
processes = {}

PROGRESS_RE = re.compile(r"(\d+\.?\d*\s?(?:[KMGT]i?B))/([^\(]+)\((\d+)%\)")
SPEED_RE = re.compile(r"DL:([\d.]+)([KMGT]?B)")
ETA_RE = re.compile(r"ETA:([^]]+)")
TRACKERS = (
    "udp://tracker.opentrackr.org:1337/announce,"
    "udp://open.demonii.com:1337/announce,"
    "udp://tracker.openbittorrent.com:80/announce"
)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_thread(download_id, proc, title, poster, genres=()):
    final_progress = 0.0
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            speed = None
            eta = ""
            m_speed = SPEED_RE.search(line)
            if m_speed:
                val = float(m_speed.group(1))
                unit = m_speed.group(2)
                speed = f"{val:.1f} {unit}/s"
            m_eta = ETA_RE.search(line)
            if m_eta:
                eta = m_eta.group(1).strip()
            match = PROGRESS_RE.search(line)
            if match:
                size = match.group(1).strip()
                final_progress = float(match.group(3))
                db.execute(
                    "UPDATE downloads SET progress=?, size=?, speed=?, eta=? WHERE id=?",
                    (final_progress, size, speed, eta, download_id),
                )
            elif speed or eta:
                db.execute(
                    "UPDATE downloads SET speed=?, eta=? WHERE id=?",
                    (speed, eta, download_id),
                )
    except Exception:
        pass
    rc = proc.wait()
    current = db.query("SELECT status FROM downloads WHERE id=?", (download_id,))
    current_status = current[0].get("status") if current else None
    if current_status in ("cancelled", "paused"):
        processes.pop(download_id, None)
        return
    if rc == 0:
        db.execute(
            "UPDATE downloads SET status='completed', progress=100.0, speed=?, eta=?, completed_at=? WHERE id=?",
            (None, None, _now(), download_id),
        )
    else:
        reason = "Process exited with code {}".format(rc)
        if proc.stdout is not None:
            try:
                last = list(proc.stdout) or []
                if last:
                    reason = last[-1].strip()[-200:]
            except Exception:
                pass
        db.execute(
            "UPDATE downloads SET status='error', progress=?, speed=?, eta=?, error=?, completed_at=? WHERE id=?",
            (final_progress, None, None, reason, _now(), download_id),
        )
    processes.pop(download_id, None)
    _save_meta(download_id, title, poster, genres)


def _resolve_poster(title):
    import re

    from backend import poster as _poster

    m = re.search(r"\b(?:19|20)\d{2}\b", title or "")
    year = int(m.group(0)) if m else None
    bases = [title or ""]
    for sep in (" (", " ["):
        if sep in (title or ""):
            bases.append((title or "").split(sep)[0])
    for base in bases:
        if not base:
            continue
        p = _poster.find_poster(base, year)
        if p:
            return p
    return ""


def _save_meta(download_id, title, poster, genres=()):
    try:
        row = db.query("SELECT * FROM downloads WHERE id=?", (download_id,))
        if not row:
            return
        row = row[0]
        if row.get("status") != "completed":
            return
        completed = row.get("completed_at") or _now()
        for child in DOWNLOADS_DIR.rglob("*"):
            if not child.is_file() or child.suffix.lower() not in (".mkv", ".mp4", ".avi", ".mov"):
                continue
            if child.stat().st_mtime <= 0:
                continue
            key = child.stem
            existing = db.query("SELECT value FROM meta WHERE key=?", (key,))
            if existing:
                continue
            db.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
                (key, child.stem),
            )
            db.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
                (child.stem + "::poster", poster or _resolve_poster(title)),
            )
            db.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
                (child.stem + "::genres", "|".join(genres or [])),
            )
            try:
                from backend import subtitles as _subtitles

                threading.Thread(
                    target=_subtitles.fetch_best,
                    args=(str(child), ["fra", "ara"]),
                    daemon=True,
                ).start()
            except Exception:
                pass
        db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
            ("dl::" + str(download_id), title),
        )
        db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
            ("poster::" + str(download_id), poster or _resolve_poster(title)),
        )
        db.execute(
            "UPDATE downloads SET poster=? WHERE id=?",
            (poster or _resolve_poster(title), download_id),
        )
    except Exception:
        pass


def _build_args(link):
    return [
        "aria2c",
        f"--dir={DOWNLOADS_DIR}",
        "--enable-dht=true",
        "--continue=true",
        "--bt-save-metadata=true",
        "--seed-time=0",
        "--summary-interval=1",
        f"--bt-tracker={TRACKERS}",
        link,
    ]


def _launch(download_id, link, title, poster, genres):
    existing = processes.get(download_id)
    if existing is not None and existing.poll() is None:
        return False
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    args = _build_args(link)
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
        processes[download_id] = proc
        threading.Thread(
            target=_read_thread,
            args=(download_id, proc, title, poster, genres),
            daemon=True,
        ).start()
        return True
    except Exception as exc:
        db.execute(
            "UPDATE downloads SET status='error', progress=0, error=?, completed_at=? WHERE id=?",
            (str(exc), _now(), download_id),
        )
        return False


def start_download(link, title, poster="", genres=()):
    download_id = db.execute(
        "INSERT INTO downloads (title, link, poster, genres, status, progress, size, speed, eta, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (title, link, poster, "|".join(genres or []), 'downloading', 0.0, '', None, '', _now()),
    )
    if download_id is None:
        return None
    _launch(download_id, link, title, poster, genres)
    return download_id


def pause_download(download_id):
    db.execute(
        "UPDATE downloads SET status='paused', speed=?, eta=? WHERE id=? AND status IN ('downloading','active','pending')",
        (None, None, download_id),
    )
    proc = processes.get(download_id)
    if proc:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        processes.pop(download_id, None)
    return True


def resume_download(download_id):
    row = db.query("SELECT * FROM downloads WHERE id=?", (download_id,))
    if not row:
        return False
    row = row[0]
    if row.get("status") not in ("paused", "error", "cancelled"):
        return False
    link = row.get("link") or ""
    if not link:
        return False
    genres = [g for g in (row.get("genres") or "").split("|") if g]
    db.execute(
        "UPDATE downloads SET status='downloading', error=?, speed=?, eta=? WHERE id=?",
        (None, None, None, download_id),
    )
    return _launch(download_id, link, row.get("title") or "Reprise", row.get("poster") or "", genres)


def kill_stale_aria2():
    try:
        subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='aria2c.exe'\" | "
                "Where-Object { $_.CommandLine -like '*Downloads\\FILMS*' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }",
            ],
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass


def _norm_title(title):
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def resume_pending():
    kill_stale_aria2()
    rows = db.query(
        "SELECT * FROM downloads WHERE status IN ('downloading','active','pending') ORDER BY id"
    ) or []
    best = {}
    for row in rows:
        key = _norm_title(row.get("title"))
        if not key:
            continue
        current = best.get(key)
        if current is None or (row.get("progress") or 0) > (current.get("progress") or 0):
            best[key] = row
    keep_ids = {row["id"] for row in best.values()}
    for row in rows:
        if row["id"] not in keep_ids:
            db.execute("DELETE FROM downloads WHERE id=?", (row["id"],))
    for row in best.values():
        link = row.get("link") or ""
        if not link:
            continue
        genres = [g for g in (row.get("genres") or "").split("|") if g]
        _launch(
            row["id"],
            link,
            row.get("title") or "Reprise",
            row.get("poster") or "",
            genres,
        )


def delete_download(download_id):
    try:
        cancel_download(download_id)
    except Exception:
        pass
    db.execute("DELETE FROM downloads WHERE id=?", (download_id,))
    return True


def cancel_download(download_id):
    db.execute(
        "UPDATE downloads SET status='cancelled' WHERE id=? AND status IN ('downloading','pending')",
        (download_id,),
    )
    proc = processes.get(download_id)
    if proc:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        processes.pop(download_id, None)
    return True


def list_downloads():
    rows = db.query("SELECT * FROM downloads ORDER BY created_at DESC")
    return rows or []