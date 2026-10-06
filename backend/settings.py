import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "filmhub_settings.json"
SUBDIR = "FILMS"


def _home_media():
    candidates = [
        Path.home() / "Videos",
        Path.home() / "Movies",
        Path.home() / "Vidéos",
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path.home() / "Downloads"


def default_downloads_dir():
    return _home_media() / SUBDIR


def _load():
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(data):
    try:
        SETTINGS_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def downloads_dir():
    env = os.environ.get("FILMHUB_DOWNLOADS")
    if env and env.strip():
        return Path(env.strip()).expanduser()
    data = _load()
    val = data.get("downloads_dir")
    if val:
        return Path(val).expanduser()
    return default_downloads_dir()


def set_downloads_dir(path, create=True):
    p = Path(str(path or "").strip()).expanduser()
    if not str(p).strip():
        raise ValueError("Chemin vide")
    if create:
        p.mkdir(parents=True, exist_ok=True)
    if not p.is_dir():
        raise ValueError("Ce chemin n'est pas un dossier")
    if not os.access(str(p), os.W_OK):
        raise ValueError("Dossier non accessible en écriture")
    data = _load()
    data["downloads_dir"] = str(p)
    _save(data)
    return str(p)


def suggested():
    out = []
    default = default_downloads_dir()
    home = Path.home()
    for candidate in (
        default,
        Path.home() / "Downloads" / SUBDIR,
        Path.home(),
    ):
        s = str(candidate)
        if s not in out:
            out.append(s)
    return out


def info():
    d = downloads_dir()
    return {
        "downloads_dir": str(d),
        "default_dir": str(default_downloads_dir()),
        "suggested": suggested(),
        "home": str(Path.home()),
    }


DEFAULT_SYNC_URL = "https://moh-films.onrender.com"


def sync_url():
    url = os.environ.get("FILMHUB_SYNC_URL") or ""
    if not url.strip():
        url = (_load().get("sync_url") or "").strip()
    return (url or DEFAULT_SYNC_URL).rstrip("/")


def auto_sync_enabled():
    env = os.environ.get("FILMHUB_AUTO_SYNC", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    return bool(_load().get("auto_sync", True))


def sync_interval():
    try:
        return max(60, int(_load().get("sync_interval", 900)))
    except Exception:
        return 900


def set_sync(value, active=None, interval=None, url=None):
    data = _load()
    if active is not None:
        data["auto_sync"] = bool(active)
    if interval is not None:
        data["sync_interval"] = max(60, int(interval))
    if url is not None:
        data["sync_url"] = (str(url) or "").strip().rstrip("/")
    _save(data)
    return True