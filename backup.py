import shutil
import sys
from datetime import datetime
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
BACKUP_DIR = ROOT / "backups"
INCLUDES = [
    "backend",
    "frontend",
    "run.py",
    "start.bat",
    "requirements.txt",
]


def snapshot(label="snapshot"):
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = BACKUP_DIR / f"{label}_{stamp}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for inc in INCLUDES:
            src = ROOT / inc
            if not src.exists():
                continue
            if src.is_dir():
                for f in src.rglob("*"):
                    if f.is_file() and "__pycache__" not in f.parts and ".pyc" not in f.name:
                        z.write(f, f.relative_to(ROOT))
            else:
                z.write(src, inc)
    return out


def restore(archive):
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():
            target = ROOT / member
            if not target.is_relative_to(ROOT):
                continue
            if target.exists() and target.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return archive


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "restore":
        if len(args) < 2:
            print("Usage: python backup.py restore <fichier_zip>")
            sys.exit(1)
        print("[OK] Restauration depuis :", restore(Path(args[1])))
    else:
        label = args[0] if args else "snapshot"
        path = snapshot(label)
        print("[OK] Snapshot cree :", path)