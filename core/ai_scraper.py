import re
import os
import time
import json
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from config import COVERS_DIR, load_config
from db.database import get_all_games, upsert_game
from core.scraper import (
    scrape_dlsite,
    scrape_bangumi,
    scrape_steam,
    scrape_vndb,
    download_and_cache_cover,
    get_http_client
)
from core.scanner import clean_title_from_folder, extract_rj_code


def translate_japanese_to_chinese(text: str, proxy: Optional[str] = None) -> str:
    """Fast single-pass Japanese to Simplified Chinese translation."""
    if not text or len(text.strip()) < 5:
        return text

    cleaned_text = text.strip()
    has_kana = bool(re.search(r"[\u3040-\u30ff]", cleaned_text))
    if not has_kana:
        return cleaned_text

    # 1. Try Google Translate
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "ja",
            "tl": "zh-CN",
            "dt": "t",
            "q": cleaned_text[:1500]
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        with get_http_client(proxy, timeout=2.5) as client:
            r = client.get(url, params=params, headers=headers)
            if r.status_code == 200:
                data = r.json()
                translated = "".join([part[0] for part in data[0] if part and part[0]])
                if translated and len(translated) > 5:
                    return translated
    except Exception:
        pass

    # 2. Try MyMemory API
    try:
        sample_text = cleaned_text[:400]
        enc = urllib.parse.quote(sample_text)
        mem_url = f"https://api.mymemory.translated.net/get?q={enc}&langpair=ja|zh-CN"
        with get_http_client(proxy, timeout=2.5) as client:
            r = client.get(mem_url)
            if r.status_code == 200:
                t_text = r.json().get("responseData", {}).get("translatedText")
                if t_text and not t_text.startswith("MYMEMORY WARNING"):
                    return t_text
    except Exception:
        pass

    return cleaned_text


def find_internal_clues(folder_path: str) -> Dict[str, Optional[str]]:
    """Inspects inner directory files for RJ codes, Steam AppIDs, or original titles."""
    clues = {"rj_code": None, "steam_appid": None, "original_title": None}
    if not folder_path or not os.path.exists(folder_path):
        return clues

    try:
        for root, dirs, files in os.walk(folder_path):
            rel_depth = len(os.path.relpath(root, folder_path).split(os.sep))
            if rel_depth > 2:
                dirs.clear()
                continue

            for f in files:
                m = re.search(r"\b([RBV]J\d{6,8})\b", f, re.I)
                if m and not clues["rj_code"]:
                    clues["rj_code"] = m.group(1).upper()

                f_low = f.lower()
                fp = os.path.join(root, f)

                if f_low == "steam_appid.txt" and not clues["steam_appid"]:
                    try:
                        with open(fp, "r", encoding="utf-8", errors="ignore") as fl:
                            appid_str = fl.read().strip()
                            if appid_str.isdigit():
                                clues["steam_appid"] = appid_str
                    except Exception:
                        pass

                elif f_low.endswith(".url"):
                    try:
                        with open(fp, "r", encoding="utf-8", errors="ignore") as fl:
                            content = fl.read()
                            m_url = re.search(r"product_id/([RBV]J\d{6,8})", content, re.I)
                            if m_url and not clues["rj_code"]:
                                clues["rj_code"] = m_url.group(1).upper()
                    except Exception:
                        pass

                elif f_low == "package.json" and not clues["original_title"]:
                    try:
                        with open(fp, "r", encoding="utf-8", errors="ignore") as fl:
                            data = json.load(fl)
                            t = data.get("window", {}).get("title") or data.get("name")
                            if t and len(t) > 1 and t.lower() not in ("game", "test", "app", "nw", "rpg"):
                                clues["original_title"] = t
                    except Exception:
                        pass
    except Exception:
        pass

    return clues


def search_dlsite_by_keyword(keyword: str, proxy: Optional[str] = None) -> Optional[str]:
    """Searches DLsite search engine for a game keyword and returns best matching RJ code."""
    if not keyword or len(keyword.strip()) < 2:
        return None

    kw_enc = urllib.parse.quote(keyword.strip())
    search_urls = [
        f"https://www.dlsite.com/maniax/fsr/=/language/jp/sex_category%5B0%5D/male/keyword/{kw_enc}",
        f"https://www.dlsite.com/home/fsr/=/language/jp/sex_category%5B0%5D/male/keyword/{kw_enc}"
    ]

    with get_http_client(proxy, timeout=3.5) as client:
        for url in search_urls:
            try:
                r = client.get(url)
                if r.status_code == 200:
                    m = re.search(r"/work/=/product_id/([RBV]J\d{6,8})\.html", r.text)
                    if m:
                        return m.group(1).upper()
            except Exception:
                continue
    return None


def process_single_game_ai_scrape(
    game: Dict[str, Any],
    proxy: Optional[str] = None,
    preferred_source: Optional[str] = None,
    force: bool = False
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Complete AI scraping & translation pipeline for a single game,
    supporting DLsite, Bangumi, Steam, and VNDB while respecting preferred_source.
    """
    cfg = load_config()
    pref = (preferred_source or cfg.get("scrape_source") or "auto").lower()

    fpath = game.get("folder_path")
    fname = game.get("folder_name", "")
    clean_t = game.get("clean_title") or clean_title_from_folder(fname)
    rj_code = game.get("rj_code") or extract_rj_code(fname)

    # 1. Discover internal clues
    clues = find_internal_clues(fpath) if fpath else {}
    if not rj_code and clues.get("rj_code"):
        rj_code = clues["rj_code"]

    candidate_titles = []
    if clues.get("original_title"):
        candidate_titles.append(clues["original_title"])
    if clean_t:
        candidate_titles.append(clean_t)
    if fname and fname not in candidate_titles:
        candidate_titles.append(fname)

    meta = None
    target_rj = rj_code

    # If user explicitly prefers Steam, Bangumi, or VNDB first (when no exact RJ code is forced)
    if pref == "steam":
        if clues.get("steam_appid"):
            meta = scrape_steam(clues["steam_appid"], proxy=proxy, force=force)
        if not meta:
            for t in candidate_titles:
                search_str = re.sub(r"[~_+\-=\[\]【】()（）]", " ", t).strip()
                if len(search_str) >= 2:
                    meta = scrape_steam(search_str, proxy=proxy, force=force)
                    if meta:
                        break
    elif pref == "bangumi":
        for t in candidate_titles:
            search_str = re.sub(r"[~_+\-=\[\]【】()（）]", " ", t).strip()
            if len(search_str) >= 2:
                meta = scrape_bangumi(search_str, proxy=proxy, force=force)
                if meta:
                    break
    elif pref == "vndb":
        for t in candidate_titles:
            search_str = re.sub(r"[~_+\-=\[\]【】()（）]", " ", t).strip()
            if len(search_str) >= 2:
                meta = scrape_vndb(search_str, proxy=proxy, force=force)
                if meta:
                    if meta.get("synopsis"):
                        meta["synopsis"] = translate_japanese_to_chinese(meta["synopsis"], proxy=proxy)
                    break

    # 2. DLsite lookup by RJ code or keyword search
    if not meta:
        if not target_rj and pref in ("auto", "dlsite"):
            for t in candidate_titles:
                search_str = re.sub(r"[~_+\-=\[\]【】()（）]", " ", t).strip()
                if len(search_str) >= 2:
                    found_rj = search_dlsite_by_keyword(search_str, proxy=proxy)
                    if found_rj:
                        target_rj = found_rj
                        break

        if target_rj:
            meta = scrape_dlsite(target_rj, proxy=proxy, force=force)
            if meta:
                jp_synopsis = meta.get("synopsis", "")
                if jp_synopsis:
                    zh_synopsis = translate_japanese_to_chinese(jp_synopsis, proxy=proxy)
                    meta["synopsis"] = zh_synopsis
                if clean_t and clean_t != meta["title"] and not re.search(r"[\u3040-\u30ff]", clean_t):
                    meta["display_title"] = clean_t

    # 3. Fallback across Bangumi -> Steam -> VNDB
    if not meta:
        if clues.get("steam_appid"):
            meta = scrape_steam(clues["steam_appid"], proxy=proxy, force=force)

    if not meta:
        for t in candidate_titles:
            search_str = re.sub(r"[~_+\-=\[\]【】()（）]", " ", t).strip()
            if len(search_str) >= 2:
                bgm_res = scrape_bangumi(search_str, proxy=proxy, force=force)
                if bgm_res:
                    meta = bgm_res
                    break
                steam_res = scrape_steam(search_str, proxy=proxy, force=force)
                if steam_res:
                    meta = steam_res
                    break
                vndb_res = scrape_vndb(search_str, proxy=proxy, force=force)
                if vndb_res:
                    meta = vndb_res
                    if meta.get("synopsis"):
                        meta["synopsis"] = translate_japanese_to_chinese(meta["synopsis"], proxy=proxy)
                    break

    if not meta:
        return False, None

    # 4. Persist to DB
    update_dict = {
        "folder_name": game["folder_name"],
        "folder_path": game["folder_path"],
        "rj_code": target_rj or meta.get("rj_code") or game.get("rj_code", ""),
        "display_title": meta.get("display_title") or meta.get("title") or clean_t or game["folder_name"],
        "original_title": meta.get("original_title") or "",
        "cover_url": meta.get("cover_url") or game.get("cover_url", ""),
        "banner_url": meta.get("banner_url") or game.get("banner_url", ""),
        "synopsis": meta.get("synopsis") or game.get("synopsis", ""),
        "circle_name": meta.get("circle_name") or game.get("circle_name", ""),
        "release_date": meta.get("release_date") or game.get("release_date", ""),
        "voice_actors": meta.get("voice_actors") or [],
        "tags": meta.get("tags") or [],
        "source_url": meta.get("source_url") or "",
        "source_type": meta.get("source_type") or "dlsite",
        "rating_score": meta.get("rating_score") or 0.0
    }
    upsert_game(update_dict)
    return True, update_dict
