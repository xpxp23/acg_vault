import re
import os
import json
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Optional, Dict, Any, List
from config import COVERS_DIR

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

def get_http_client(proxy: Optional[str] = None, timeout: float = 4.0) -> httpx.Client:
    proxies = proxy if proxy and proxy.strip() else None
    return httpx.Client(
        headers={"User-Agent": USER_AGENTS, "Accept-Language": "ja,zh-CN,zh,en-US;q=0.9"},
        cookies={"adultchecked": "1", "over18": "yes", "birthtime": "283993201", "lastagecheckage": "1-0-1980"},
        proxy=proxies,
        timeout=timeout,
        follow_redirects=True
    )

def download_and_cache_cover(img_url: str, filename_stem: str, proxy: Optional[str] = None) -> str:
    """Downloads remote image and saves locally to prevent broken hotlinks."""
    if not img_url:
        return ""
    try:
        ext = ".jpg"
        if ".png" in img_url.lower():
            ext = ".png"
        elif ".webp" in img_url.lower():
            ext = ".webp"
        
        # Clean invalid filename characters
        safe_stem = re.sub(r'[\\/*?:"<>|]', "_", str(filename_stem))
        target_name = f"{safe_stem}{ext}"
        target_path = COVERS_DIR / target_name
        
        if target_path.exists() and target_path.stat().st_size > 1024:
            return f"/api/covers/{target_name}"

        with get_http_client(proxy, timeout=6.0) as client:
            resp = client.get(img_url)
            if resp.status_code == 200 and len(resp.content) > 500:
                with open(target_path, "wb") as f:
                    f.write(resp.content)
                return f"/api/covers/{target_name}"
    except Exception as e:
        print(f"Failed to cache cover {img_url}: {e}")
    return img_url

def scrape_dlsite(rj_code: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Scrapes DLsite product page by RJ/VJ/BJ code."""
    if not rj_code:
        return None

    code = rj_code.upper()
    subdomains = ["maniax", "home", "pro"]
    html_content = ""
    target_url = ""

    with get_http_client(proxy, timeout=4.0) as client:
        for branch in subdomains:
            url = f"https://www.dlsite.com/{branch}/work/=/product_id/{code}.html"
            try:
                r = client.get(url)
                if r.status_code == 200 and ("work_name" in r.text or "work_buy" in r.text):
                    html_content = r.text
                    target_url = url
                    break
            except Exception:
                continue

    if not html_content:
        return None

    soup = BeautifulSoup(html_content, "html.parser")
    
    # Title
    title_el = soup.find("h1", id="work_name")
    title = title_el.get_text(strip=True) if title_el else ""

    # Maker / Circle
    maker_el = soup.find("span", class_="maker_name") or soup.find("a", class_="maker_name")
    maker = maker_el.get_text(strip=True) if maker_el else ""

    # Cover Image
    cover_url = ""
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        cover_url = og_img["content"]
    if not cover_url:
        img_el = soup.find("img", class_="slider_image") or soup.find("div", class_="work_left")
        if img_el:
            found_img = img_el.find("img") if hasattr(img_el, "find") else img_el
            if found_img and found_img.get("src"):
                cover_url = found_img["src"]

    if cover_url.startswith("//"):
        cover_url = "https:" + cover_url

    # Table Info
    table = soup.find("table", id="work_maker")
    release_date = ""
    voice_actors = []
    tags = []
    
    if table:
        for tr in table.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if not th or not td:
                continue
            header_text = th.get_text(strip=True)
            val_text = td.get_text(strip=True)
            
            if "販売日" in header_text or "配信開始日" in header_text:
                release_date = re.sub(r"[^\d年-月日]", "", val_text).strip()
            elif "声優" in header_text:
                vas = [a.get_text(strip=True) for a in td.find_all("a")]
                voice_actors.extend(vas if vas else [val_text])
            elif "ジャンル" in header_text or "ジャンル" in th.text:
                tag_list = [a.get_text(strip=True) for a in td.find_all("a")]
                tags.extend(tag_list if tag_list else [t.strip() for t in val_text.split("/")])

    outline_el = (
        soup.find("div", class_="work_parts_area")
        or soup.find("div", class_="work_parts_multitype")
        or soup.find("div", class_="work_intro")
        or soup.find("div", itemprop="description")
    )
    synopsis = ""
    if outline_el:
        synopsis = outline_el.get_text(separator="\n", strip=True)

    cached_cover = download_and_cache_cover(cover_url, code, proxy)

    return {
        "title": title,
        "original_title": title,
        "circle_name": maker,
        "release_date": release_date,
        "cover_url": cached_cover,
        "banner_url": cached_cover,
        "synopsis": synopsis,
        "voice_actors": voice_actors,
        "tags": list(dict.fromkeys(tags)),
        "source_url": target_url,
        "source_type": "dlsite",
        "rating_score": 0.0
    }

def scrape_steam(keyword_or_appid: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Scrapes Steam Store metadata for PC games by title search or Steam AppID."""
    if not keyword_or_appid or len(keyword_or_appid.strip()) < 1:
        return None

    query = keyword_or_appid.strip()
    appid = None

    # If already an appid
    if query.isdigit():
        appid = int(query)
    else:
        # Search via Steam suggest API
        with get_http_client(proxy, timeout=5.0) as client:
            try:
                url_suggest = f"https://store.steampowered.com/search/suggest?term={urllib.parse.quote(query)}&f=games&cc=US&l=schinese"
                r = client.get(url_suggest)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    match = soup.find("a", class_="match")
                    if match and match.get("data-ds-appid"):
                        appid = int(match["data-ds-appid"])
            except Exception as e:
                print(f"Steam search error for '{query}': {e}")

    if not appid:
        return None

    # Fetch appdetails from Steam Store API in Simplified Chinese
    with get_http_client(proxy, timeout=5.0) as client:
        try:
            url_details = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=schinese"
            r = client.get(url_details)
            if r.status_code != 200:
                return None
            res_json = r.json().get(str(appid), {})
            if not res_json.get("success"):
                return None
            data = res_json.get("data", {})

            name = data.get("name", "")
            devs = data.get("developers", [])
            publishers = data.get("publishers", [])
            circle = ", ".join(devs if devs else publishers)
            release_date = data.get("release_date", {}).get("date", "")
            
            header_img = data.get("header_image") or ""
            cached_cover = download_and_cache_cover(header_img, f"steam_{appid}", proxy)

            # Synopsis: clean html tags from short_description or detailed_description
            synopsis_raw = data.get("short_description") or data.get("detailed_description") or data.get("about_the_game") or ""
            synopsis_clean = re.sub(r"<[^>]+>", "", synopsis_raw).strip()

            tags = []
            for g in data.get("genres", []):
                if g.get("description"):
                    tags.append(g["description"])
            for c in data.get("categories", []):
                if c.get("description") and len(tags) < 10:
                    tags.append(c["description"])

            return {
                "title": name,
                "original_title": name,
                "circle_name": circle,
                "release_date": release_date,
                "cover_url": cached_cover,
                "banner_url": header_img,
                "synopsis": synopsis_clean,
                "voice_actors": [],
                "tags": list(dict.fromkeys(tags)),
                "source_url": f"https://store.steampowered.com/app/{appid}",
                "source_type": "steam",
                "rating_score": 0.0
            }
        except Exception as e:
            print(f"Steam appdetails error for {appid}: {e}")
            return None

def scrape_bangumi(keyword: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Scrapes Bangumi API for Galgames/Visual Novels."""
    if not keyword or len(keyword.strip()) < 2:
        return None

    cleaned_kw = keyword.strip()
    with get_http_client(proxy, timeout=5.0) as client:
        try:
            url = f"https://api.bgm.tv/search/subject/{cleaned_kw}?type=4&responseGroup=large"
            r = client.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
            items = data.get("list", [])
            if not items:
                v0_url = "https://api.bgm.tv/v0/search/subjects"
                r2 = client.post(v0_url, json={"keyword": cleaned_kw, "filter": {"type": [4]}})
                if r2.status_code == 200:
                    v0_items = r2.json().get("data", [])
                    if v0_items:
                        items = v0_items
                    else:
                        return None
                else:
                    return None

            best = items[0]
            sub_id = best.get("id")
            name_cn = best.get("name_cn") or best.get("name") or ""
            name_jp = best.get("name") or ""
            summary = best.get("summary") or ""
            rating = best.get("rating", {}).get("score", 0.0)
            
            imgs = best.get("images") or {}
            cover_url = imgs.get("large") or imgs.get("common") or imgs.get("medium") or ""
            
            tags = [t.get("name") for t in best.get("tags", []) if t.get("name")]
            release_date = best.get("air_date") or best.get("date") or ""

            cached_cover = download_and_cache_cover(cover_url, f"bgm_{sub_id}", proxy)

            return {
                "title": name_cn or name_jp,
                "original_title": name_jp,
                "circle_name": "",
                "release_date": release_date,
                "cover_url": cached_cover,
                "banner_url": cached_cover,
                "synopsis": summary,
                "voice_actors": [],
                "tags": tags[:10],
                "source_url": f"https://bgm.tv/subject/{sub_id}",
                "source_type": "bangumi",
                "rating_score": float(rating) if rating else 0.0
            }
        except Exception as e:
            print(f"Bangumi scrape error for '{cleaned_kw}': {e}")
            return None

def scrape_vndb(keyword: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Scrapes VNDB Kana API for Visual Novels."""
    if not keyword or len(keyword.strip()) < 2:
        return None

    with get_http_client(proxy, timeout=5.0) as client:
        try:
            url = "https://api.vndb.org/kana/vn"
            payload = {
                "filters": ["search", "=", keyword.strip()],
                "fields": "title, alttitle, description, image.url, rating, released, developers.name, tags.name"
            }
            r = client.post(url, json=payload)
            if r.status_code != 200:
                return None
            results = r.json().get("results", [])
            if not results:
                return None

            best = results[0]
            vn_id = best.get("id")
            title = best.get("title") or ""
            alttitle = best.get("alttitle") or ""
            desc = best.get("description") or ""
            desc = re.sub(r"\[/?\w+.*?\]", "", desc)

            rating = (best.get("rating") or 0) / 10.0
            released = best.get("released") or ""
            devs = [d.get("name") for d in best.get("developers", []) if d.get("name")]
            tags = [t.get("name") for t in best.get("tags", []) if t.get("name")][:10]
            
            img_obj = best.get("image") or {}
            cover_url = img_obj.get("url") or ""
            cached_cover = download_and_cache_cover(cover_url, f"vndb_{vn_id}", proxy)

            return {
                "title": title,
                "original_title": alttitle or title,
                "circle_name": ", ".join(devs),
                "release_date": released,
                "cover_url": cached_cover,
                "banner_url": cached_cover,
                "synopsis": desc,
                "voice_actors": [],
                "tags": tags,
                "source_url": f"https://vndb.org/{vn_id}",
                "source_type": "vndb",
                "rating_score": float(rating)
            }
        except Exception as e:
            print(f"VNDB scrape error for '{keyword}': {e}")
            return None

def scrape_game_auto(
    rj_code: Optional[str] = None,
    clean_title: Optional[str] = None,
    folder_name: Optional[str] = None,
    proxy: Optional[str] = None,
    preferred_source: str = "auto"
) -> Optional[Dict[str, Any]]:
    """Aggregated automatic scraper pipeline."""
    # 1. Preferred source direct check
    if preferred_source == "steam" and (clean_title or folder_name):
        res = scrape_steam(clean_title or folder_name, proxy=proxy)
        if res:
            return res

    if preferred_source == "dlsite" and rj_code:
        res = scrape_dlsite(rj_code.strip(), proxy=proxy)
        if res:
            return res

    # 2. Auto pipeline: DLsite -> Bangumi -> Steam -> VNDB
    if rj_code and rj_code.strip():
        res = scrape_dlsite(rj_code.strip(), proxy=proxy)
        if res:
            return res

    search_query = clean_title or folder_name or ""
    if search_query:
        if preferred_source in ("auto", "bangumi"):
            bgm_res = scrape_bangumi(search_query, proxy=proxy)
            if bgm_res:
                return bgm_res

        # Try Steam
        steam_res = scrape_steam(search_query, proxy=proxy)
        if steam_res:
            return steam_res

        # Try VNDB
        vndb_res = scrape_vndb(search_query, proxy=proxy)
        if vndb_res:
            return vndb_res

    return None

def search_scraper_candidates(
    keyword: str,
    rj_code: Optional[str] = None,
    proxy: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Searches multiple sources (DLsite, Bangumi, Steam, VNDB) and returns candidate matches for user selection.
    """
    candidates: List[Dict[str, Any]] = []

    # 1. DLsite via RJ code
    if rj_code and rj_code.strip():
        try:
            dl_res = scrape_dlsite(rj_code.strip(), proxy=proxy)
            if dl_res:
                candidates.append({
                    "source": "dlsite",
                    "source_name": "DLsite (精确编号)",
                    "source_url": dl_res.get("source_url", ""),
                    "title": dl_res.get("title", ""),
                    "original_title": dl_res.get("original_title", ""),
                    "circle_name": dl_res.get("circle_name", ""),
                    "release_date": dl_res.get("release_date", ""),
                    "cover_url": dl_res.get("cover_url", ""),
                    "synopsis": dl_res.get("synopsis", ""),
                    "tags": dl_res.get("tags", []),
                    "voice_actors": dl_res.get("voice_actors", []),
                    "rj_code": rj_code.strip().upper(),
                    "rating_score": dl_res.get("rating_score", 0.0)
                })
        except Exception as e:
            print(f"Candidate DLsite error: {e}")

    # 2. Bangumi Search (up to 4 items)
    kw = (keyword or "").strip()
    if kw and len(kw) >= 2:
        try:
            with get_http_client(proxy, timeout=5.0) as client:
                url = f"https://api.bgm.tv/search/subject/{urllib.parse.quote(kw)}?type=4&responseGroup=large"
                r = client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    items = data.get("list", [])[:4]
                    for item in items:
                        sub_id = item.get("id")
                        name_cn = item.get("name_cn") or item.get("name") or ""
                        name_jp = item.get("name") or ""
                        summary = item.get("summary") or ""
                        imgs = item.get("images") or {}
                        raw_cover = imgs.get("large") or imgs.get("common") or imgs.get("medium") or ""
                        cached_cover = download_and_cache_cover(raw_cover, f"bgm_{sub_id}", proxy) if raw_cover else ""
                        tags = [t.get("name") for t in item.get("tags", []) if t.get("name")][:8]
                        candidates.append({
                            "source": "bangumi",
                            "source_name": "Bangumi (番组计划)",
                            "source_url": f"https://bgm.tv/subject/{sub_id}",
                            "title": name_cn or name_jp,
                            "original_title": name_jp,
                            "circle_name": "",
                            "release_date": item.get("air_date") or item.get("date") or "",
                            "cover_url": cached_cover or raw_cover,
                            "synopsis": summary,
                            "tags": tags,
                            "voice_actors": [],
                            "rj_code": "",
                            "rating_score": float(item.get("rating", {}).get("score", 0.0) or 0.0)
                        })
        except Exception as e:
            print(f"Candidate Bangumi error: {e}")

    # 3. Steam Search (up to 2 items)
    if kw and len(kw) >= 2:
        try:
            with get_http_client(proxy, timeout=5.0) as client:
                url = f"https://store.steampowered.com/api/storesearch/?term={urllib.parse.quote(kw)}&l=schinese&cc=CN"
                r = client.get(url)
                if r.status_code == 200:
                    items = r.json().get("items", [])[:2]
                    for item in items:
                        appid = item.get("id")
                        steam_detail = scrape_steam(kw, proxy=proxy) if appid else None
                        if steam_detail and steam_detail.get("source_url") and str(appid) in steam_detail["source_url"]:
                            candidates.append({
                                "source": "steam",
                                "source_name": "Steam 商店",
                                "source_url": steam_detail.get("source_url", ""),
                                "title": steam_detail.get("title", item.get("name", "")),
                                "original_title": steam_detail.get("original_title", item.get("name", "")),
                                "circle_name": steam_detail.get("circle_name", ""),
                                "release_date": steam_detail.get("release_date", ""),
                                "cover_url": steam_detail.get("cover_url", item.get("tiny_image", "")),
                                "synopsis": steam_detail.get("synopsis", ""),
                                "tags": steam_detail.get("tags", []),
                                "voice_actors": [],
                                "rj_code": "",
                                "rating_score": 0.0
                            })
                        else:
                            candidates.append({
                                "source": "steam",
                                "source_name": "Steam 商店",
                                "source_url": f"https://store.steampowered.com/app/{appid}",
                                "title": item.get("name", ""),
                                "original_title": item.get("name", ""),
                                "circle_name": "",
                                "release_date": "",
                                "cover_url": item.get("tiny_image", ""),
                                "synopsis": "",
                                "tags": [],
                                "voice_actors": [],
                                "rj_code": "",
                                "rating_score": 0.0
                            })
        except Exception as e:
            print(f"Candidate Steam error: {e}")

    # 4. VNDB Search (if we have fewer than 3 candidates)
    if kw and len(candidates) < 3:
        try:
            with get_http_client(proxy, timeout=5.0) as client:
                payload = {
                    "user": "acg_vault",
                    "filters": ["search", "=", kw],
                    "fields": "title, alttitle, released, rating, image.url, description, developers.name"
                }
                r = client.post("https://api.vndb.org/kana/vn", json=payload)
                if r.status_code == 200:
                    vn_items = r.json().get("results", [])[:2]
                    for item in vn_items:
                        vn_id = item.get("id")
                        raw_img = (item.get("image") or {}).get("url") or ""
                        cached_cover = download_and_cache_cover(raw_img, f"vndb_{vn_id}", proxy) if raw_img else ""
                        candidates.append({
                            "source": "vndb",
                            "source_name": "VNDB (视觉小说数据库)",
                            "source_url": f"https://vndb.org/{vn_id}",
                            "title": item.get("title") or "",
                            "original_title": item.get("alttitle") or item.get("title") or "",
                            "circle_name": ", ".join([d.get("name", "") for d in item.get("developers", []) if d.get("name")]),
                            "release_date": item.get("released") or "",
                            "cover_url": cached_cover or raw_img,
                            "synopsis": item.get("description") or "",
                            "tags": [],
                            "voice_actors": [],
                            "rj_code": "",
                            "rating_score": float(item.get("rating") or 0.0)
                        })
        except Exception as e:
            print(f"Candidate VNDB error: {e}")

    return candidates

