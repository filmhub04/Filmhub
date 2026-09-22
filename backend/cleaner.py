import re
from pathlib import Path

from backend import db, downloader

ACTIVE = ("downloading", "active", "pending")


def _normalize(title):
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def scan_aria2():
    root = downloader.DOWNLOADS_DIR
    out = []
    if not root.exists():
        return out
    try:
        files = list(root.rglob("*.aria2"))
    except Exception:
        return out
    for ctrl in files:
        if not ctrl.is_file():
            continue
        target = Path(str(ctrl)[: -len(".aria2")])
        if target.exists():
            continue
        try:
            size = ctrl.stat().st_size
        except Exception:
            size = 0
        out.append({"path": str(ctrl.relative_to(root)), "size": size})
    return out


def scan_duplicates():
    rows = db.query(
        "SELECT id, title, status, progress, created_at FROM downloads"
    ) or []
    groups = {}
    for row in rows:
        key = _normalize(row.get("title"))
        if not key:
            continue
        groups.setdefault(key, []).append(row)
    dups = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        ordered = sorted(
            members,
            key=lambda r: (
                1 if r.get("status") == "completed" else 0,
                r.get("progress") or 0,
                r.get("id") or 0,
            ),
            reverse=True,
        )
        keep = ordered[0]
        for row in ordered[1:]:
            dups.append({
                "id": row.get("id"),
                "title": row.get("title"),
                "status": row.get("status"),
                "progress": row.get("progress") or 0,
                "keep_id": keep.get("id"),
                "keep_status": keep.get("status"),
            })
    return dups


def delete_aria2(rel_paths):
    root = downloader.DOWNLOADS_DIR
    root_res = root.resolve()
    deleted = 0
    for rel in rel_paths or []:
        try:
            candidate = (root / rel).resolve()
        except Exception:
            continue
        if candidate.parent != root_res and root_res not in candidate.parents:
            continue
        if candidate.suffix != ".aria2" or not candidate.is_file():
            continue
        target = Path(str(candidate)[: -len(".aria2")])
        if target.exists():
            continue
        try:
            candidate.unlink()
            deleted += 1
        except OSError:
            pass
    return deleted


def delete_downloads(ids):
    deleted = 0
    for did in ids or []:
        try:
            downloader.cancel_download(int(did))
        except Exception:
            pass
        try:
            db.execute("DELETE FROM downloads WHERE id=?", (int(did),))
            deleted += 1
        except Exception:
            pass
    return deleted
