import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import cleaner, db, dlna, downloader, library, poster, search, subtitles

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    downloader.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    try:
        downloader.resume_pending()
    except Exception:
        pass
    try:
        dlna.start()
    except Exception:
        pass
    yield
    try:
        dlna.stop()
    except Exception:
        pass


app = FastAPI(lifespan=lifespan, title="FILMS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dlna.router)


@app.get("/api/health")
def health():
    try:
        return {"status": "ok"}
    except Exception:
        return {"status": "ok"}


class SearchQuery(BaseModel):
    q: str = ""
    year: int | None = None


@app.get("/api/search")
def api_search(q: str = "", year: int | None = None, quality: str | None = None):
    try:
        results = search.search_all(q, year, quality)
        return {"results": results}
    except Exception:
        return {"results": []}


class DownloadBody(BaseModel):
    link: str
    title: str = ""
    poster: str = ""
    genres: list[str] = []


@app.post("/api/download")
def api_download(body: DownloadBody):
    try:
        dl_id = downloader.start_download(body.link, body.title, body.poster, body.genres)
        if dl_id is None:
            return {"id": None, "status": "error"}
        return {"id": dl_id, "status": "downloading"}
    except Exception:
        return {"id": None, "status": "error"}


@app.get("/api/downloads")
def api_downloads():
    try:
        return {"downloads": downloader.list_downloads()}
    except Exception:
        return {"downloads": []}


@app.post("/api/downloads/{download_id}/cancel")
def api_cancel(download_id: int):
    try:
        downloader.cancel_download(download_id)
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


@app.post("/api/downloads/{download_id}/pause")
def api_pause(download_id: int):
    try:
        downloader.pause_download(download_id)
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


@app.post("/api/downloads/{download_id}/resume")
def api_resume(download_id: int):
    try:
        ok = downloader.resume_download(download_id)
        return {"status": "ok" if ok else "error"}
    except Exception:
        return {"status": "error"}


@app.delete("/api/downloads/{download_id}")
def api_delete_download(download_id: int):
    try:
        downloader.delete_download(download_id)
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


class PosterBody(BaseModel):
    title: str
    year: int | None = None


@app.post("/api/poster")
def api_poster(body: PosterBody):
    try:
        if not body.title:
            return {"poster": None}
        return {"poster": poster.find_poster(body.title, body.year)}
    except Exception:
        return {"poster": None}


class LibraryPosterBody(BaseModel):
    poster: str = ""


@app.post("/api/library/{item_id}/poster")
def api_library_poster(item_id: int, body: LibraryPosterBody):
    try:
        video = library.find_file_by_id(item_id)
        if video is None or not body.poster:
            return {"status": "error"}
        db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
            (video.stem + "::poster", body.poster),
        )
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


@app.post("/api/library/{item_id}/favorite")
def api_library_favorite(item_id: int):
    try:
        fav = library.toggle_favorite(item_id)
        if fav is None:
            return {"status": "error"}
        return {"status": "ok", "favorite": fav}
    except Exception:
        return {"status": "error"}


@app.get("/api/cleanup")
def api_cleanup_scan():
    try:
        return {
            "aria2": cleaner.scan_aria2(),
            "duplicates": cleaner.scan_duplicates(),
        }
    except Exception:
        return {"aria2": [], "duplicates": []}


class CleanupBody(BaseModel):
    aria2: list[str] = []
    download_ids: list[int] = []


@app.post("/api/cleanup")
def api_cleanup_run(body: CleanupBody):
    try:
        files = cleaner.delete_aria2(body.aria2)
        rows = cleaner.delete_downloads(body.download_ids)
        return {"status": "ok", "deleted_files": files, "deleted_downloads": rows}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@app.get("/api/library")
def api_library():
    try:
        return {"items": library.scan_library()}
    except Exception:
        return {"items": []}


@app.delete("/api/library/{item_id}")
def api_delete_library(item_id: int):
    try:
        ok = library.delete_item(item_id)
        return {"status": "ok" if ok else "error"}
    except Exception:
        return {"status": "error"}


@app.get("/api/stream/{item_id}")
def api_stream(item_id: int):
    try:
        path = library.find_file_by_id(item_id)
        if path is None or not path.exists():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(str(path))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Server error")


class SubtitlesBody(BaseModel):
    languages: list[str] = ["fra", "ara"]


@app.post("/api/library/{item_id}/subtitles")
def api_fetch_subtitles(item_id: int, body: SubtitlesBody):
    try:
        path = library.find_file_by_id(item_id)
        if path is None or not path.exists():
            return {"status": "error", "error": "file not found"}
        languages = body.languages or ["fra", "ara"]

        def _run():
            subtitles.fetch_best(str(path), languages)
            library.scan_library()

        threading.Thread(target=_run, daemon=True).start()
        return {"status": "started"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@app.get("/api/library/{item_id}/subtitle/{lang}")
def api_subtitle(item_id: int, lang: str):
    try:
        path = library.find_file_by_id(item_id)
        if path is None or not path.exists():
            return JSONResponse({"error": "video not found"}, status_code=404)
        srt_path = library.srt_path_for(path, lang)
        if srt_path is None:
            return JSONResponse({"error": "subtitle not found"}, status_code=404)
        vtt = library.srt_to_vtt(srt_path.read_text(encoding="utf-8", errors="replace"))
        return PlainTextResponse(vtt, media_type="text/vtt")
    except HTTPException:
        raise
    except Exception:
        return JSONResponse({"error": "subtitle error"}, status_code=500)


@app.post("/api/subtitles/all")
def api_subtitles_all():
    try:
        def _run():
            items = library.scan_library()
            for item in items:
                path = library.find_file_by_id(item["id"])
                if path is None or not path.exists():
                    continue
                langs = {s.get("lang") for s in (item.get("subtitles") or [])}
                need_fra = "fra" not in langs
                need_ara = "ara" not in langs
                if not need_fra and not need_ara:
                    continue
                try:
                    if need_ara:
                        subtitles.fetch_arabic_by_title(str(path))
                except Exception:
                    pass
                try:
                    if need_fra:
                        subtitles.fetch_subtitles(str(path), ["fra"])
                except Exception:
                    pass
            library.scan_library()

        threading.Thread(target=_run, daemon=True).start()
        return {"status": "started"}
    except Exception:
        return {"status": "error"}


@app.get("/api/watchlist")
def api_watchlist():
    try:
        rows = db.query("SELECT * FROM watchlist ORDER BY created_at DESC")
        return {"items": rows or []}
    except Exception:
        return {"items": []}


class WatchlistBody(BaseModel):
    title: str
    poster: str = ""
    note: str = ""


@app.post("/api/watchlist")
def api_watchlist_add(body: WatchlistBody):
    try:
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        wid = db.execute(
            "INSERT INTO watchlist (title, poster, note, created_at) VALUES (?,?,?,?)",
            (body.title, body.poster, body.note, now),
        )
        return {"id": wid, "status": "ok"}
    except Exception:
        return {"id": None, "status": "error"}


@app.delete("/api/watchlist/{item_id}")
def api_watchlist_delete(item_id: int):
    try:
        db.execute("DELETE FROM watchlist WHERE id=?", (item_id,))
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


@app.get("/api/history")
def api_history():
    try:
        rows = db.query("SELECT * FROM history ORDER BY updated_at DESC")
        return {"items": rows or []}
    except Exception:
        return {"items": []}


class HistoryBody(BaseModel):
    library_id: int | None = None
    title: str = ""
    poster: str = ""
    position: float = 0.0
    duration: float = 0.0


@app.post("/api/history")
def api_history_add(body: HistoryBody):
    try:
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing = db.query("SELECT id FROM history WHERE title=?", (body.title,))
        if existing:
            db.execute(
                "UPDATE history SET poster=?, position=?, duration=?, updated_at=? WHERE title=?",
                (body.poster, body.position, body.duration, now, body.title),
            )
        else:
            db.execute(
                "INSERT INTO history (title, poster, position, duration, updated_at) VALUES (?,?,?,?,?)",
                (body.title, body.poster, body.position, body.duration, now),
            )
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


(app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static"))