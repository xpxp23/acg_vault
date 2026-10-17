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
    APP_VERSION,
    BASE_DIR,
    COVERS_DIR,
    load_config,
    save_config
)
import ctypes

from db.database import (
    init_db,
    get_all_games,
    get_filtered_status_counts,
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
    search_scraper_candidates,
    is_valid_image_bytes
)
from core.ai_scraper import (
    process_single_game_ai_scrape,
    search_dlsite_by_keyword,
    translate_japanese_to_chinese
)
from core.launcher import (
    launch_game,
    open_game_folder,
    reveal_in_explorer,
    get_game_mtool_status,
    launch_game_with_mtool,
    launch_game_with_le,
    get_game_save_status,
    open_game_save_folder,
    open_save_backup_folder,
    backup_game_saves,
    restore_game_saves,
    delete_game_save_backup,
    get_running_games_info
)
from core.dedup import (
    compute_duplicates_and_update_db,
    archive_game_directory,
    dismiss_duplicate
)

if sys.platform == "win32":
    from ctypes import wintypes

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
    """
    Moves folder/file to Windows Recycle Bin using SHFileOperationW.
    Never falls back to shutil.rmtree silent permanent deletion!
    """
    if not os.path.exists(path_str):
        return True
    if sys.platform != "win32":
        return False
    try:
        # Must use absolute normalized path without trailing slash for SHFileOperationW
        abs_norm = os.path.abspath(os.path.normpath(path_str)).rstrip("\\/") + "\0\0"
        fileop = SHFILEOPSTRUCTW()
        fileop.wFunc = 0x0003  # FO_DELETE
        fileop.pFrom = abs_norm
        fileop.fFlags = 0x0040 | 0x0010 | 0x0004  # FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fileop))
        if res == 0 and not bool(fileop.fAnyOperationsAborted):
            return True
        print(f"SHFileOperationW returned error code: {res}")
        return False
    except Exception as e:
        print(f"SHFileOperation error: {e}")
        return False


def cleanup_old_custom_covers(game_id: int, keep_filename: Optional[str] = None):
    """Deletes old custom uploaded covers for a game to prevent disk bloat."""
    try:
        for old_file in COVERS_DIR.glob(f"custom_{game_id}_*"):
            if keep_filename and old_file.name == keep_filename:
                continue
            try:
                old_file.unlink()
            except Exception:
                pass
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ACG Game Vault", version=APP_VERSION, lifespan=lifespan)

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
    "current_folder": "",
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
    executable_path: Optional[str] = None
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


class SaveBackupActionRequest(BaseModel):
    filename: Optional[str] = None
    label: Optional[str] = None


class PickPathRequest(BaseModel):
    mode: str = "folder"  # "folder" or "file"
    title: Optional[str] = None
    initial_dir: Optional[str] = None
    filetypes: Optional[str] = None  # "exe" or "image"


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/")
def serve_index():
    index_file = BASE_DIR / "static" / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": f"ACG Game Vault v{APP_VERSION} API is running."}


@app.get("/api/covers/{filename}")
def get_cover_image(filename: str):
    safe_name = Path(filename).name
    file_path = COVERS_DIR / safe_name
    if file_path.exists() and file_path.is_file():
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
    engine_filter: Optional[str] = Query(None),
    trans_filter: Optional[str] = Query(None),
    unscraped_only: bool = Query(False),
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
        engine_filter=engine_filter,
        trans_filter=trans_filter,
        unscraped_only=unscraped_only,
        sort_by=sort_by,
        sort_order=sort_order
    )
    status_counts = get_filtered_status_counts(
        keyword=keyword,
        favorite_only=favorite_only,
        duplicates_only=duplicates_only,
        missing_only=missing_only,
        is_tool=is_tool,
        has_notes_only=has_notes_only,
        engine_filter=engine_filter,
        trans_filter=trans_filter,
        unscraped_only=unscraped_only
    )
    running_map = get_running_games_info()
    return {
        "data": games,
        "total": len(games),
        "status_counts": status_counts,
        "running_games": running_map
    }


@app.get("/api/games/running")
def get_running_games_api():
    return {"running_games": get_running_games_info()}


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
    save_status = get_game_save_status(game_id)
    running_map = get_running_games_info()
    return {
        "data": game,
        "variants": variants,
        "mtool_status": mtool_status,
        "save_status": save_status,
        "running_info": running_map.get(game_id)
    }


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
        if not is_valid_image_bytes(content):
            raise HTTPException(status_code=400, detail="上传的文件不是有效的图片格式")
        with open(target_path, "wb") as f:
            f.write(content)

        cleanup_old_custom_covers(game_id, keep_filename=target_filename)
        cover_url = f"/api/covers/{target_filename}"
        manual_update_game_metadata(game_id, {
            "cover_url": cover_url,
            "banner_url": cover_url
        })
        return {"success": True, "cover_url": cover_url, "data": get_game_by_id(game_id)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传图片失败: {str(e)}")


@app.post("/api/games/{game_id}/manual_update")
def manual_update_game(game_id: int, req: ManualUpdateMetadataRequest):
    """Allows manual editing/customization of all scraped fields, including clearing cover_url & banner_url."""
    update_data = req.model_dump(exclude_unset=True)

    if "cover_url" in update_data:
        cov = (update_data["cover_url"] or "").strip()
        cfg = load_config()
        proxy = cfg.get("proxy")

        if not cov:
            cleanup_old_custom_covers(game_id)
            update_data["cover_url"] = ""
            update_data["banner_url"] = ""
        elif cov.startswith("http://") or cov.startswith("https://"):
            stem = f"custom_{game_id}_{int(time.time())}"
            cached = download_and_cache_cover(cov, stem, proxy=proxy, force=True)
            if cached:
                cleanup_old_custom_covers(game_id, keep_filename=Path(cached).name)
                update_data["cover_url"] = cached
                update_data["banner_url"] = cached
            else:
                raise HTTPException(status_code=400, detail="无法下载指定的网络封面图片，请检查链接或代理设置")
        elif cov.startswith("/api/covers/"):
            update_data["banner_url"] = cov
        elif os.path.exists(cov) and os.path.isfile(cov):
            ext = Path(cov).suffix.lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
                raise HTTPException(status_code=400, detail="本地封面仅支持 JPG/PNG/WebP/BMP/GIF 图片格式")
            with open(cov, "rb") as f:
                head_bytes = f.read(512)
            if not is_valid_image_bytes(head_bytes):
                raise HTTPException(status_code=400, detail="指定的本地文件不是合法的图片文件")
            target_name = f"custom_{game_id}_{int(time.time())}{ext}"
            shutil.copy(cov, str(COVERS_DIR / target_name))
            cleanup_old_custom_covers(game_id, keep_filename=target_name)
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
    preferred_source = (req.preferred_source or cfg.get("scrape_source", "auto")).lower()

    if req.custom_cover_url:
        cached = download_and_cache_cover(req.custom_cover_url, f"custom_{game_id}_{int(time.time())}", proxy, force=True)
        if not cached:
            return {"success": False, "message": "无法下载自定义封面图片，请检查网络或代理"}
        game_update = {
            "folder_name": game["folder_name"],
            "folder_path": game["folder_path"],
            "cover_url": cached,
            "banner_url": cached
        }
        upsert_game(game_update)
        return {"success": True, "data": get_game_by_id(game_id)}

    meta = None
    search_keyword = (req.search_keyword or game.get("clean_title") or game.get("folder_name") or "").strip()
    rj_code = (req.rj_code or game.get("rj_code") or "").strip()

    if preferred_source == "steam":
        meta = scrape_steam(rj_code if rj_code.isdigit() else search_keyword, proxy=proxy, force=True)
    elif preferred_source == "dlsite":
        target_rj = rj_code
        if not target_rj and search_keyword:
            target_rj = search_dlsite_by_keyword(search_keyword, proxy=proxy) or ""
        if target_rj:
            meta = scrape_dlsite(target_rj, proxy=proxy, force=True)
            if meta and meta.get("synopsis"):
                meta["synopsis"] = translate_japanese_to_chinese(meta["synopsis"], proxy=proxy)
    elif preferred_source == "bangumi":
        meta = scrape_bangumi(search_keyword, proxy=proxy, force=True)
    elif preferred_source == "vndb":
        meta = scrape_vndb(search_keyword, proxy=proxy, force=True)
        if meta and meta.get("synopsis"):
            meta["synopsis"] = translate_japanese_to_chinese(meta["synopsis"], proxy=proxy)
    else:
        game_copy = dict(game)
        if req.rj_code:
            game_copy["rj_code"] = req.rj_code
        if req.search_keyword:
            game_copy["clean_title"] = req.search_keyword
        success, result_data = process_single_game_ai_scrape(
            game_copy,
            proxy=proxy,
            preferred_source=preferred_source,
            force=True
        )
        if success:
            return {"success": True, "data": get_game_by_id(game_id)}

    if not meta:
        return {"success": False, "message": "未能刮削到匹配的元数据，您可以切换数据源(如Steam/Bangumi/DLsite)或点击【多源预览候选】"}

    update_dict = {
        "folder_name": game["folder_name"],
        "folder_path": game["folder_path"],
        "rj_code": meta.get("rj_code") or rj_code or game.get("rj_code", ""),
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
    return launch_game(game_id, mode=mode)


@app.post("/api/games/{game_id}/launch_mtool")
def launch_mtool_api(game_id: int):
    return launch_game_with_mtool(game_id)


@app.post("/api/games/{game_id}/launch_le")
def launch_le_api(game_id: int):
    return launch_game_with_le(game_id)


@app.get("/api/games/{game_id}/mtool_status")
def get_mtool_status_api(game_id: int):
    return get_game_mtool_status(game_id)


@app.get("/api/games/{game_id}/save_status")
def get_save_status_api(game_id: int):
    return get_game_save_status(game_id)


@app.post("/api/games/{game_id}/open_save")
def open_save_api(game_id: int):
    return open_game_save_folder(game_id)


@app.post("/api/games/{game_id}/open_save_backups")
def open_save_backups_api(game_id: int):
    return open_save_backup_folder(game_id)


@app.post("/api/games/{game_id}/backup_save")
def backup_save_api(game_id: int, req: Optional[SaveBackupActionRequest] = None):
    label = req.label if req and req.label else ""
    return backup_game_saves(game_id, label=label)


@app.post("/api/games/{game_id}/restore_save")
def restore_save_api(game_id: int, req: SaveBackupActionRequest):
    if not req.filename:
        raise HTTPException(status_code=400, detail="缺少要还原的备份文件名")
    return restore_game_saves(game_id, req.filename)


@app.post("/api/games/{game_id}/delete_save_backup")
def delete_save_backup_api(game_id: int, req: SaveBackupActionRequest):
    if not req.filename:
        raise HTTPException(status_code=400, detail="缺少要删除的备份文件名")
    return delete_game_save_backup(game_id, req.filename)


@app.post("/api/games/{game_id}/bake_translation")
def bake_translation_api(game_id: int):
    from core.mz_patcher import bake_game_translation
    return bake_game_translation(game_id)


@app.post("/api/games/{game_id}/unbake_translation")
def unbake_translation_api(game_id: int):
    from core.mz_patcher import unbake_game_translation
    return unbake_game_translation(game_id)


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
            raise HTTPException(status_code=500, detail="移入系统回收站失败，文件可能正被游戏进程或资源管理器占用")
    cleanup_old_custom_covers(game_id)
    delete_game_by_id(game_id)
    compute_duplicates_and_update_db()
    return {"success": True, "message": "游戏已成功移入回收站并从库中移除" if delete_local else "游戏已从库中移出（本地文件已保留）"}


@app.post("/api/games/cleanup_missing")
def cleanup_missing_api():
    cleaned_count = cleanup_all_missing_games()
    compute_duplicates_and_update_db()
    return {"success": True, "count": cleaned_count, "message": f"已清理 {cleaned_count} 部缺失游戏记录"}


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
    failed_paths = []
    deletable_ids = []
    for gid in req.game_ids:
        if req.delete_local:
            g = get_game_by_id(gid)
            if g and g.get("folder_path") and os.path.exists(g["folder_path"]):
                if not send_to_recycle_bin(g["folder_path"]):
                    failed_paths.append(g.get("folder_name") or str(gid))
                    continue
        cleanup_old_custom_covers(gid)
        deletable_ids.append(gid)

    count = batch_delete_games_by_ids(deletable_ids)
    compute_duplicates_and_update_db()
    if failed_paths:
        return {
            "success": count > 0,
            "count": count,
            "message": f"已处理 {count} 部游戏，但有 {len(failed_paths)} 部因文件占用未能移入回收站: {', '.join(failed_paths[:3])}"
        }
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
    cfg = load_config()
    proxy = cfg.get("proxy")

    raw_cover = c.get("cover_url") or c.get("cover_image") or game.get("cover_url", "")
    if raw_cover and (raw_cover.startswith("http://") or raw_cover.startswith("https://")):
        cached = download_and_cache_cover(raw_cover, f"cand_{game_id}_{int(time.time())}", proxy=proxy, force=True)
        raw_cover = cached or game.get("cover_url", "")

    circle_val = c.get("circle_name") or c.get("circle") or game.get("circle_name", "")

    update_dict = {
        "folder_path": game["folder_path"],
        "folder_name": game["folder_name"],
        "display_title": c.get("title") or game.get("display_title", ""),
        "original_title": c.get("original_title") or game.get("original_title", ""),
        "rj_code": c.get("rj_code") or game.get("rj_code", ""),
        "circle_name": circle_val,
        "cover_url": raw_cover,
        "banner_url": raw_cover or game.get("banner_url", ""),
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
    SCAN_STATE["progress"] = 0
    SCAN_STATE["total"] = 0
    SCAN_STATE["current_folder"] = ""
    SCAN_STATE["status_message"] = "正在准备扫描游戏目录..."
    try:
        cfg = load_config()
        dirs = cfg.get("game_directories", [])
        all_items = []

        def on_scan_progress(idx: int, total: int, folder_name: str):
            SCAN_STATE["progress"] = idx
            SCAN_STATE["total"] = total
            SCAN_STATE["current_folder"] = folder_name
            SCAN_STATE["status_message"] = f"正在扫描 ({idx}/{total}): {folder_name[:28]}"

        for d in dirs:
            if d and os.path.exists(d):
                items = scan_directory(d, progress_callback=on_scan_progress)
                all_items.extend(items)

        SCAN_STATE["status_message"] = "正在同步数据库..."
        batch_upsert_games(all_items)

        SCAN_STATE["status_message"] = "正在校验缺失目录..."
        stored_paths = get_all_stored_game_paths()
        missing_ids = []
        valid_ids = []
        for gid, fpath, prev_missing in stored_paths:
            if not os.path.exists(fpath):
                missing_ids.append(gid)
            elif prev_missing == 1:
                valid_ids.append(gid)
        set_games_missing_batch(missing_ids, valid_ids)

        SCAN_STATE["status_message"] = "正在计算重复游戏分组..."
        compute_duplicates_and_update_db()

        missing_count = len(missing_ids)
        msg = f"扫描完成！共同步 {len(all_items)} 部作品"
        if missing_count > 0:
            msg += f"，发现 {missing_count} 部作品本地目录缺失"
        SCAN_STATE["status_message"] = msg

        if cfg.get("auto_scrape", False) and not BATCH_SCRAPE_STATE["is_running"]:
            unscraped_games = get_all_games(status="all", is_tool=False, unscraped_only=True)
            if unscraped_games:
                threading.Thread(target=background_batch_scrape, daemon=True).start()
    except Exception as e:
        SCAN_STATE["status_message"] = f"扫描异常: {str(e)}"
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
    if BATCH_SCRAPE_STATE["is_running"]:
        return
    BATCH_SCRAPE_STATE["is_running"] = True
    try:
        cfg = load_config()
        proxy = cfg.get("proxy")
        preferred_source = cfg.get("scrape_source", "auto")

        unscraped = get_all_games(status="all", is_tool=False, unscraped_only=True)
        BATCH_SCRAPE_STATE["total"] = len(unscraped)
        BATCH_SCRAPE_STATE["current_index"] = 0

        if not unscraped:
            BATCH_SCRAPE_STATE["status_message"] = "所有游戏元数据均已完整，无需刮削！"
            return

        def worker(g):
            try:
                process_single_game_ai_scrape(g, proxy=proxy, preferred_source=preferred_source)
            except Exception:
                pass
            return g.get("clean_title", "")

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_game = {executor.submit(worker, g): g for g in unscraped}
            for idx, future in enumerate(as_completed(future_to_game)):
                title = future.result()
                BATCH_SCRAPE_STATE["current_index"] = idx + 1
                BATCH_SCRAPE_STATE["current_game_title"] = title
                BATCH_SCRAPE_STATE["status_message"] = f"正在刮削 ({idx+1}/{len(unscraped)}): {title[:24]}"

        BATCH_SCRAPE_STATE["status_message"] = "批量刮削已完成！"
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
    st = get_stats()
    st["running_games"] = get_running_games_info()
    return st


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
            r = client.get("https://www.dlsite.com" if proxies else "https://api.bgm.tv")
            return {"success": True, "status_code": r.status_code, "message": f"连接成功 (HTTP {r.status_code})"}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {str(e)}"}


@app.post("/api/system/pick_path")
def pick_local_path(req: PickPathRequest):
    """Opens a native desktop folder/file selector dialog on the local machine."""
    result: Dict[str, Any] = {"success": False, "path": "", "message": ""}

    def _open_tk_dialog():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass
            init_dir = req.initial_dir if (req.initial_dir and os.path.exists(req.initial_dir)) else None
            if req.mode == "file":
                ftypes = [("所有文件", "*.*")]
                if req.filetypes == "exe":
                    ftypes = [("可执行程序 (*.exe)", "*.exe"), ("所有文件", "*.*")]
                elif req.filetypes == "image":
                    ftypes = [("图片文件", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"), ("所有文件", "*.*")]
                chosen = filedialog.askopenfilename(
                    title=req.title or "选择文件",
                    initialdir=init_dir,
                    filetypes=ftypes
                )
            else:
                chosen = filedialog.askdirectory(
                    title=req.title or "选择文件夹",
                    initialdir=init_dir
                )
            root.destroy()
            if chosen:
                result["success"] = True
                result["path"] = os.path.normpath(chosen)
            else:
                result["message"] = "已取消选择"
        except Exception as e:
            result["message"] = f"当前环境不支持原生图形选择器，请手动输入路径 ({str(e)})"

    t = threading.Thread(target=_open_tk_dialog)
    t.start()
    t.join(timeout=60.0)
    return result


def open_browser(port: int):
    time.sleep(1.2)
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    app_port = int(cfg.get("port", 8000))
    threading.Thread(target=open_browser, args=(app_port,), daemon=True).start()
    print("====================================================")
    print(f"      ACG Game Vault v{APP_VERSION} is running at http://127.0.0.1:{app_port}")
    print("====================================================")
    uvicorn.run(app, host="127.0.0.1", port=app_port, log_level="info")
