from pathlib import Path

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov")

EXTRA_DIRS = {
    "featurettes",
    "featurette",
    "extras",
    "extra",
    "bonus",
    "bonus features",
    "specials",
    "special features",
    "behind the scenes",
    "interviews",
    "interview",
    "deleted scenes",
    "additional scenes",
    "sample",
    "samples",
    "trailers",
    "trailer",
    "short films",
    "subs",
    "subtitles",
    "other",
}

EXTRA_WORDS = (
    "behind the scenes",
    "featurette",
    "deleted scene",
    "additional scenes",
    "additional material",
    "making of",
    "interview",
    "interviews",
    "introduction by",
    "gallery",
    "trailer",
    "teaser",
    "screen test",
    "acclaim & response",
    "short film",
    "red carpet",
    "the filmmakers",
    "home movies",
    "chronology",
    "comparisons",
)

BIG_MOVIE_BYTES = 800 * 1024 * 1024
SMALL_EXTRA_BYTES = 150 * 1024 * 1024


def _norm_stem(path):
    return Path(path).stem.lower().replace("_", " ").replace(".", " ")


def is_extra(path):
    p = Path(path)
    dirs = [str(part).strip().lower() for part in p.parts[:-1]]
    if any(d in EXTRA_DIRS for d in dirs):
        return True
    stem = _norm_stem(p)
    return any(word in stem for word in EXTRA_WORDS)


def _size(path):
    try:
        return Path(path).stat().st_size
    except Exception:
        return 0


def filter_videos(paths):
    by_dir = {}
    for p in paths:
        by_dir.setdefault(str(Path(p).parent), []).append(p)
    keep = []
    for items in by_dir.values():
        sizes = {p: _size(p) for p in items}
        biggest = max(sizes.values()) if sizes else 0
        for p in items:
            if is_extra(p):
                continue
            if biggest >= BIG_MOVIE_BYTES and sizes[p] < SMALL_EXTRA_BYTES:
                continue
            keep.append(p)
    return keep


def list_videos(root):
    root = Path(root)
    if not root.exists():
        return []
    found = []
    for p in root.rglob("*"):
        try:
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                found.append(p)
        except Exception:
            continue
    return filter_videos(found)
