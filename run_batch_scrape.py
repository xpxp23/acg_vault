import sys
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import init_db, get_all_games, get_stats
from config import load_config
from core.ai_scraper import process_single_game_ai_scrape

def run_full_scrape():
    init_db()
    cfg = load_config()
    proxy = cfg.get("proxy")

    games = get_all_games(status="all", is_tool=False)
    unscraped = [g for g in games if not g.get("cover_url") or not g.get("synopsis")]
    total = len(unscraped)

    print(f"====================================================")
    print(f"   ACG Game Vault AI 批量刮削与中文翻译引擎")
    print(f"   待刮削游戏总数: {total} 款")
    print(f"====================================================\n", flush=True)

    if total == 0:
        print("所有游戏已完成刮削！", flush=True)
        return

    success_count = 0
    fail_count = 0
    start_time = time.time()

    def worker(g):
        try:
            ok, meta = process_single_game_ai_scrape(g, proxy=proxy)
            return ok, g, meta
        except Exception as e:
            return False, g, str(e)

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_game = {executor.submit(worker, g): g for g in unscraped}
        for idx, future in enumerate(as_completed(future_to_game)):
            ok, g, meta = future.result()
            progress = idx + 1
            if ok:
                success_count += 1
                disp_title = meta.get("display_title") or g["folder_name"]
                rj = meta.get("rj_code") or "-"
                source = meta.get("source_type", "auto").upper()
                print(f"[{progress:3d}/{total:3d}] ✅ [{source}] {disp_title[:30]:30s} (RJ: {rj})", flush=True)
            else:
                fail_count += 1
                print(f"[{progress:3d}/{total:3d}] ⚠️ [跳过] {g['clean_title'][:30]:30s} (未匹配到DLsite/Bangumi)", flush=True)

    elapsed = time.time() - start_time
    print(f"\n====================================================")
    print(f"   刮削完成! 成功: {success_count} 款 | 未匹配: {fail_count} 款 | 耗时: {elapsed:.1f} 秒")
    print(f"====================================================", flush=True)

if __name__ == "__main__":
    run_full_scrape()
