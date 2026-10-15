import os
import sys
import shutil
import time
import asyncio
import webbrowser
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    BASE_DIR,
    COVERS_DIR,
    load_config,
    save_config
)
import ctypes
from ctypes import wintypes

from db.database import (
    init_db,
    get_all_games,
    get_game_by_id,
    batch_upsert_games,
    update_game_user_state,
    manual_update_game_metadata,
    get_stats,
    get_duplicate_groups,
    upsert_game,
    delete_game_by_id,
    mark_game_missing,
    get_all_stored_game_paths,
    set_games_missing_batch,
    cleanup_all_missing_games,
    batch_update_games_status,
    batch_delete_games_by_ids
)
from core.scanner import scan_directory
from core.scraper import (
    scrape_game_auto,
    scrape_dlsite,
    scrape_steam,
    scrape_bangumi,
    scrape_vndb,
    download_and_cache_cover,
    search_scraper_candidates
)
from core.ai_scraper import process_single_game_ai_scrape
from core.launcher import (
    launch_game,
    open_game_folder,
    reveal_in_explorer,
    get_game_mtool_status,
    launch_game_with_mtool
)
from core.dedup import (
    compute_duplicates_and_update_db,
    archive_game_directory,
    dismiss_duplicate
)

class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR)
    ]

def send_to_recycle_bin(path_str: str) -> bool:
    if not os.path.exists(path_str):
        return True
    try:
        norm = os.path.normpath(path_str) + '\0\0'
        fileop = SHFILEOPSTRUCTW()
        fileop.wFunc = 0x0003  # FO_DELETE
        fileop.pFrom = norm
        fileop.fFlags = 0x0040 | 0x0010 | 0x0004  # FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fileop))
        if res == 0:
            return True
    except Exception as e:
        print(f"SHFileOperation error: {e}")
    try:
        if os.path.isdir(path_str):
            shutil.rmtree(path_str)
        else:
            os.remove(path_str)
        return True
    except Exception as e:
        print(f"shutil removal fallback error: {e}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="ACG Game Vault", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

class ClientLogRequest(BaseModel):
    level: str = "error"
    message: str
    url: Optional[str] = None
    stack: Optional[str] = None

@app.post("/api/client_log")
def log_client_error(req: ClientLogRequest):
    print(f"[CLIENT {req.level.upper()}] {req.message} (url: {req.url})")
    if req.stack:
        print(f"Client Stack:\n{req.stack}")
    return {"status": "ok"}

SCAN_STATE = {
    "is_running": False,
    "progress": 0,
    "total": 0,
    "status_message": "Idle",
    "last_completed_at": None
}

BATCH_SCRAPE_STATE = {
    "is_running": False,
    "current_index": 0,
    "total": 0,
    "current_game_title": "",
    "status_message": "Idle"
}

class UpdateGameStateRequest(BaseModel):
    play_status: Optional[str] = None
    user_rating: Optional[int] = None
    user_notes: Optional[str] = None
    user_tags: Optional[List[str]] = None
    is_favorite: Optional[int] = None
    display_title: Optional[str] = None
    executable_path: Optional[str] = None

class ManualUpdateMetadataRequest(BaseModel):
    display_title: Optional[str] = None
    original_title: Optional[str] = None
    circle_name: Optional[str] = None
    release_date: Optional[str] = None
    downloaded_at: Optional[str] = None
    cover_url: Optional[str] = None
    banner_url: Optional[str] = None
    synopsis: Optional[str] = None
    rj_code: Optional[str] = None
    tags: Optional[List[str]] = None
    voice_actors: Optional[List[str]] = None

class ScrapeGameRequest(BaseModel):
    rj_code: Optional[str] = None
    search_keyword: Optional[str] = None
    preferred_source: Optional[str] = "auto"
    custom_cover_url: Optional[str] = None

class ArchiveRequest(BaseModel):
    game_id: int

class DismissDuplicateRequest(BaseModel):
    game_id: int
    target_id: Optional[int] = None

class TestProxyRequest(BaseModel):
    proxy: str

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.get("/")
def serve_index():
    index_file = BASE_DIR / "static" / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "ACG Game Vault API is running."}

@app.get("/api/covers/{filename}")
def get_cover_image(filename: str):
    file_path = COVERS_DIR / filename
    if file_path.exists():
        return FileResponse(str(file_path))
    raise HTTPException(status_code=404, detail="Cover not found")

@app.get("/api/games")
def list_games(
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    favorite_only: bool = Query(False),
    duplicates_only: bool = Query(False),
    missing_only: bool = Query(False),
    is_tool: bool = Query(False),
    has_notes_only: bool = Query(False),
    sort_by: str = Query("title"),
    sort_order: str = Query("asc")
):
    games = get_all_games(
        status=status,
        keyword=keyword,
        favorite_only=favorite_only,
        duplicates_only=duplicates_only,
        missing_only=missing_only,
        is_tool=is_tool,
        has_notes_only=has_notes_only,
        sort_by=sort_by,
        sort_order=sort_order
    )
    return {"data": games, "total": len(games)}

@app.get("/api/games/{game_id}")
def get_game_detail(game_id: int):
    game = get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    variants = []
    if game.get("duplicate_group_id"):
        all_dups = get_duplicate_groups()
        variants = all_dups.get(game["duplicate_group_id"], [])
    
    mtool_status = get_game_mtool_status(game_id)
    return {"data": game, "variants": variants, "mtool_status": mtool_status}

@app.post("/api/games/{game_id}/update")
def update_game(game_id: int, req: UpdateGameStateRequest):
    success = update_game_user_state(
        game_id=game_id,
        play_status=req.play_status,
        user_rating=req.user_rating,
        user_notes=req.user_notes,
        user_tags=req.user_tags,
        is_favorite=req.is_favorite,
        display_title=req.display_title,
        executable_path=req.executable_path
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update game")
    return {"success": True, "data": get_game_by_id(game_id)}

@app.post("/api/games/{game_id}/upload_cover")
async def upload_game_cover(game_id: int, file: UploadFile = File(...)):
    """Uploads a local image file and sets it as the game cover."""
    game = get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
        ext = ".jpg"

    timestamp = int(time.time())
    target_filename = f"custom_{game_id}_{timestamp}{ext}"
    target_path = COVERS_DIR / target_filename

    try:
        content = await file.read()
        with open(target_path, "wb") as f:
            f.write(content)

        cover_url = f"/api/covers/{target_filename}"
        manual_update_game_metadata(game_id, {
            "cover_url": cover_url,
            "banner_url": cover_url
        })
        return {"success": True, "cover_url": cover_url, "data": get_game_by_id(game_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传图片失败: {str(e)}")

@app.post("/api/games/{game_id}/manual_update")
def manual_update_game(game_id: int, req: ManualUpdateMetadataRequest):
    """Allows manual editing/customization of all scraped fields."""
    update_data = req.dict(exclude_unset=True)

    # Handle cover_url downloading or local file copying if needed
    if update_data.get("cover_url"):
        cov = update_data["cover_url"].strip()
        cfg = load_config()
        proxy = cfg.get("proxy")

        # If HTTP URL, cache it locally
        if cov.startswith("http://") or cov.startswith("https://"):
            cached = download_and_cache_cover(cov, f"custom_{game_id}_{int(time.time())}", proxy=proxy)
            if cached:
                update_data["cover_url"] = cached
                update_data["banner_url"] = cached

        # If local Windows absolute file path, copy to covers dir
        elif os.path.exists(cov) and os.path.isfile(cov):
            ext = Path(cov).suffix.lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
                ext = ".jpg"
            target_name = f"custom_{game_id}_{int(time.time())}{ext}"
            shutil.copy(cov, str(COVERS_DIR / target_name))
            update_data["cover_url"] = f"/api/covers/{target_name}"
            update_data["banner_url"] = f"/api/covers/{target_name}"

    success = manual_update_game_metadata(game_id, update_data)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update metadata")
    return {"success": True, "data": get_game_by_id(game_id)}

@app.post("/api/games/{game_id}/scrape")
def scrape_single_game(game_id: int, req: ScrapeGameRequest):
    game = get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    cfg = load_config()
    proxy = cfg.get("proxy")
    preferred_source = req.preferred_source or cfg.get("scrape_source", "auto")

    # Custom cover override
    if req.custom_cover_url:
        cached = download_and_cache_cover(req.custom_cover_url, f"custom_{game_id}", proxy)
        game_update = {
            "folder_name": game["folder_name"],
            "folder_path": game["folder_path"],
            "cover_url": cached,
            "banner_url": cached
        }
        upsert_game(game_update)
        return {"success": True, "data": get_game_by_id(game_id)}

    meta = None
    search_keyword = req.search_keyword or game.get("clean_title") or game.get("folder_name")
    rj_code = req.rj_code or game.get("rj_code")

    if preferred_source == "steam":
        meta = scrape_steam(search_keyword, proxy=proxy)
    elif preferred_source == "dlsite" and rj_code:
        meta = scrape_dlsite(rj_code, proxy=proxy)
    elif preferred_source == "bangumi":
        meta = scrape_bangumi(search_keyword, proxy=proxy)
    elif preferred_source == "vndb":
        meta = scrape_vndb(search_keyword, proxy=proxy)
    else:
        game_copy = dict(game)
        if req.rj_code:
            game_copy["rj_code"] = req.rj_code
        if req.search_keyword:
            game_copy["clean_title"] = req.search_keyword
        success, result_data = process_single_game_ai_scrape(game_copy, proxy=proxy)
        if success:
            return {"success": True, "data": get_game_by_id(game_id)}

    if not meta:
        return {"success": False, "message": "未能刮削到匹配的元数据，您可以切换数据源(如Steam/Bangumi/DLsite)或在上方直接【手动编辑】内容"}

    update_dict = {
        "folder_name": game["folder_name"],
        "folder_path": game["folder_path"],
        "rj_code": rj_code or game.get("rj_code", ""),
        "display_title": meta.get("title") or game["clean_title"],
        "original_title": meta.get("original_title") or "",
        "cover_url": meta.get("cover_url") or game.get("cover_url", ""),
        "banner_url": meta.get("banner_url") or game.get("banner_url", ""),
        "synopsis": meta.get("synopsis") or game.get("synopsis", ""),
        "circle_name": meta.get("circle_name") or game.get("circle_name", ""),
        "release_date": meta.get("release_date") or game.get("release_date", ""),
        "voice_actors": meta.get("voice_actors") or [],
        "tags": meta.get("tags") or [],
        "source_url": meta.get("source_url") or "",
        "source_type": meta.get("source_type") or preferred_source,
        "rating_score": meta.get("rating_score") or 0.0
    }
    upsert_game(update_dict)
    return {"success": True, "data": get_game_by_id(game_id)}

class LaunchGameRequest(BaseModel):
    mode: Optional[str] = None

@app.post("/api/games/{game_id}/launch")
def launch_game_api(game_id: int, req: Optional[LaunchGameRequest] = None):
    mode = req.mode if req else None
    res = launch_game(game_id, mode=mode)
    return res

@app.post("/api/games/{game_id}/launch_mtool")
def launch_mtool_api(game_id: int):
    res = launch_game_with_mtool(game_id)
    return res

@app.get("/api/games/{game_id}/mtool_status")
def get_mtool_status_api(game_id: int):
    return get_game_mtool_status(game_id)

@app.post("/api/games/{game_id}/bake_translation")
def bake_translation_api(game_id: int):
    from core.mz_patcher import bake_game_translation
    res = bake_game_translation(game_id)
    return res

@app.post("/api/games/{game_id}/open_folder")
def open_folder_api(game_id: int):
    game = get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    success = open_game_folder(game["folder_path"])
    return {"success": success}

@app.post("/api/games/{game_id}/reveal")
def reveal_api(game_id: int):
    game = get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    target = game.get("executable_path") or game["folder_path"]
    success = reveal_in_explorer(target)
    return {"success": success}

class DeleteGameRequest(BaseModel):
    delete_local: bool = False

@app.post("/api/games/{game_id}/delete")
def delete_game_api(game_id: int, req: Optional[DeleteGameRequest] = None):
    game = get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    delete_local = req.delete_local if req else False
    if delete_local and game.get("folder_path") and os.path.exists(game["folder_path"]):
        success = send_to_recycle_bin(game["folder_path"])
        if not success:
            raise HTTPException(status_code=500, detail="删除本地文件失败，文件可能被占用")
    delete_game_by_id(game_id)
    compute_duplicates_and_update_db()
    return {"success": True, "message": "游戏已成功移除/删除"}

@app.post("/api/games/cleanup_missing")
def cleanup_missing_api():
    cleaned_count = cleanup_all_missing_games()
    compute_duplicates_and_update_db()
    return {"success": True, "count": cleaned_count, "message": f"已清理 {cleaned_count} 部缺失游戏"}

class BatchUpdateStatusRequest(BaseModel):
    game_ids: List[int]
    play_status: str

@app.post("/api/games/batch_update_status")
def batch_update_status_api(req: BatchUpdateStatusRequest):
    count = batch_update_games_status(req.game_ids, req.play_status)
    return {"success": True, "count": count, "message": f"已成功更新 {count} 部游戏状态"}

class BatchDeleteRequest(BaseModel):
    game_ids: List[int]
    delete_local: bool = False

@app.post("/api/games/batch_delete")
def batch_delete_api(req: BatchDeleteRequest):
    if req.delete_local:
        for gid in req.game_ids:
            g = get_game_by_id(gid)
            if g and g.get("folder_path") and os.path.exists(g["folder_path"]):
                send_to_recycle_bin(g["folder_path"])
    count = batch_delete_games_by_ids(req.game_ids)
    compute_duplicates_and_update_db()
    return {"success": True, "count": count, "message": f"已成功批量删除/移出 {count} 部游戏"}

class SearchCandidatesRequest(BaseModel):
    keyword: Optional[str] = None
    rj_code: Optional[str] = None

@app.post("/api/games/{game_id}/search_candidates")
def search_candidates_api(game_id: int, req: Optional[SearchCandidatesRequest] = None):
    game = get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    cfg = load_config()
    proxy = cfg.get("proxy")
    kw = (req.keyword if req and req.keyword else None) or game.get("clean_title") or game.get("folder_name") or ""
    rj = (req.rj_code if req and req.rj_code else None) or game.get("rj_code") or ""
    candidates = search_scraper_candidates(keyword=kw, rj_code=rj, proxy=proxy)
    return {"success": True, "candidates": candidates}

class ApplyCandidateRequest(BaseModel):
    candidate: Dict[str, Any]

@app.post("/api/games/{game_id}/apply_candidate")
def apply_candidate_api(game_id: int, req: ApplyCandidateRequest):
    game = get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    c = req.candidate
    update_dict = {
        "folder_path": game["folder_path"],
        "folder_name": game["folder_name"],
        "display_title": c.get("title") or game.get("display_title", ""),
        "original_title": c.get("original_title") or game.get("original_title", ""),
        "rj_code": c.get("rj_code") or game.get("rj_code", ""),
        "circle_name": c.get("circle_name") or game.get("circle_name", ""),
        "cover_url": c.get("cover_url") or game.get("cover_url", ""),
        "banner_url": c.get("cover_url") or game.get("banner_url", ""),
        "synopsis": c.get("synopsis") or game.get("synopsis", ""),
        "release_date": c.get("release_date") or game.get("release_date", ""),
        "voice_actors": c.get("voice_actors") or game.get("voice_actors", []),
        "tags": c.get("tags") or game.get("tags", []),
        "source_url": c.get("source_url") or game.get("source_url", ""),
        "source_type": c.get("source") or game.get("source_type", "auto"),
        "rating_score": c.get("rating_score") or game.get("rating_score", 0.0)
    }
    upsert_game(update_dict)
    return {"success": True, "data": get_game_by_id(game_id)}

def background_scan_task():
    global SCAN_STATE
    SCAN_STATE["is_running"] = True
    SCAN_STATE["status_message"] = "Scanning directories..."
    try:
        cfg = load_config()
        dirs = cfg.get("game_directories", [])
        all_items = []
        for d in dirs:
            if os.path.exists(d):
                items = scan_directory(d)
                all_items.extend(items)
        
        SCAN_STATE["status_message"] = "Updating database..."
        batch_upsert_games(all_items)
        
        SCAN_STATE["status_message"] = "Checking missing folders..."
        stored_paths = get_all_stored_game_paths()
        missing_ids = []
        valid_ids = []
        for gid, fpath, prev_missing in stored_paths:
            if not os.path.exists(fpath):
                missing_ids.append(gid)
            elif prev_missing == 1:
                valid_ids.append(gid)
        set_games_missing_batch(missing_ids, valid_ids)

        SCAN_STATE["status_message"] = "Computing duplicates..."
        compute_duplicates_and_update_db()

        missing_count = len(missing_ids)
        msg = f"扫描完成！共入库 {len(all_items)} 部"
        if missing_count > 0:
            msg += f"，检测到 {missing_count} 部游戏本地文件已缺失"
        SCAN_STATE["status_message"] = msg
    except Exception as e:
        SCAN_STATE["status_message"] = f"Error: {str(e)}"
    finally:
        SCAN_STATE["is_running"] = False
        from datetime import datetime
        SCAN_STATE["last_completed_at"] = datetime.now().isoformat()


@app.post("/api/games/scan")
def trigger_scan(bg_tasks: BackgroundTasks):
    global SCAN_STATE
    if SCAN_STATE["is_running"]:
        return {"success": False, "message": "扫描任务已在进行中"}
    bg_tasks.add_task(background_scan_task)
    return {"success": True, "message": "后台扫描已启动"}

@app.get("/api/games/scan/status")
def get_scan_status():
    return SCAN_STATE

def background_batch_scrape():
    global BATCH_SCRAPE_STATE
    BATCH_SCRAPE_STATE["is_running"] = True
    try:
        cfg = load_config()
        proxy = cfg.get("proxy")

        games = get_all_games(status="all", is_tool=False)
        unscraped = [g for g in games if not g.get("cover_url") or not g.get("synopsis")]
        BATCH_SCRAPE_STATE["total"] = len(unscraped)
        BATCH_SCRAPE_STATE["current_index"] = 0

        def worker(g):
            try:
                process_single_game_ai_scrape(g, proxy=proxy)
            except Exception as e:
                pass
            return g.get("clean_title", "")

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_game = {executor.submit(worker, g): g for g in unscraped}
            for idx, future in enumerate(as_completed(future_to_game)):
                title = future.result()
                BATCH_SCRAPE_STATE["current_index"] = idx + 1
                BATCH_SCRAPE_STATE["current_game_title"] = title
                BATCH_SCRAPE_STATE["status_message"] = f"Scraping ({idx+1}/{len(unscraped)}): {title[:20]}"

        BATCH_SCRAPE_STATE["status_message"] = "Batch scrape completed!"
    except Exception as e:
        BATCH_SCRAPE_STATE["status_message"] = f"Error: {str(e)}"
    finally:
        BATCH_SCRAPE_STATE["is_running"] = False

@app.post("/api/games/batch_scrape")
def trigger_batch_scrape(bg_tasks: BackgroundTasks):
    global BATCH_SCRAPE_STATE
    if BATCH_SCRAPE_STATE["is_running"]:
        return {"success": False, "message": "批量刮削已在运行中"}
    bg_tasks.add_task(background_batch_scrape)
    return {"success": True, "message": "已启动后台批量刮削"}

@app.get("/api/games/batch_scrape/status")
def get_batch_scrape_status():
    return BATCH_SCRAPE_STATE

@app.get("/api/duplicates")
def list_duplicates():
    groups = get_duplicate_groups()
    return {"data": groups, "total_groups": len(groups)}

@app.post("/api/duplicates/archive")
def archive_duplicate_api(req: ArchiveRequest):
    cfg = load_config()
    archive_root = cfg.get("archive_directory", r"E:\ACG\_Archive_Duplicates")
    success, msg = archive_game_directory(req.game_id, archive_root)
    return {"success": success, "message": msg}

@app.post("/api/duplicates/dismiss")
def dismiss_duplicate_api(req: DismissDuplicateRequest):
    success, msg = dismiss_duplicate(req.game_id, req.target_id)
    return {"success": success, "message": msg}

@app.get("/api/stats")
def get_dashboard_stats():
    return get_stats()

@app.get("/api/config")
def get_system_config():
    return load_config()

@app.post("/api/config")
def update_system_config(cfg: dict):
    saved = save_config(cfg)
    return {"success": True, "data": saved}

@app.post("/api/config/test_proxy")
def test_proxy(req: TestProxyRequest):
    import httpx
    try:
        proxies = req.proxy.strip() if req.proxy else None
        with httpx.Client(proxy=proxies, timeout=6.0) as client:
            r = client.get("https://www.google.com" if proxies else "https://api.bgm.tv")
            return {"success": True, "status_code": r.status_code, "message": f"连接成功 (HTTP {r.status_code})"}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {str(e)}"}

def open_browser():
    import time
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    import uvicorn
    threading.Thread(target=open_browser, daemon=True).start()
    print("====================================================")
    print("      ACG Game Vault is running at http://127.0.0.1:8000")
    print("====================================================")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
