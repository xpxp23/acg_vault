import re
import os
import io
import json
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Optional, Dict, Any, List
from config import COVERS_DIR, THUMBS_DIR
from db.database import get_scrape_cache, set_scrape_cache, normalize_and_localize_tags

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

IMAGE_MAGIC_PREFIXES = (
    b"\xff\xd8\xff",      # JPEG
    b"\x89PNG\r\n\x1a\n", # PNG
    b"RIFF",              # WebP (RIFF....WEBP)
    b"GIF87a",            # GIF
    b"GIF89a",            # GIF
    b"BM"                 # BMP
)


def is_valid_image_bytes(data: bytes) -> bool:
    if not data or len(data) < 256:
        return False
    return any(data.startswith(prefix) for prefix in IMAGE_MAGIC_PREFIXES)


def generate_cover_thumbnail(source_path: Path, max_width: int = 420) -> Optional[Path]:
    """Generates a lightweight WebP/JPEG thumbnail in THUMBS_DIR for smooth 60fps grid scrolling."""
    if not HAS_PIL or not source_path.exists():
        return None
    try:
        thumb_path = THUMBS_DIR / f"{source_path.name}.webp"
        if thumb_path.exists() and thumb_path.stat().st_mtime >= source_path.stat().st_mtime:
            return thumb_path
        with Image.open(source_path) as im:
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            if im.width > max_width:
                ratio = max_width / float(im.width)
                new_h = max(1, int(im.height * ratio))
                resample = getattr(Image, "Resampling", Image).LANCZOS
                im = im.resize((max_width, new_h), resample)
            im.save(thumb_path, format="WEBP", quality=82, method=4)
        return thumb_path
    except Exception:
        return None


def get_http_client(proxy: Optional[str] = None, timeout: float = 4.5) -> httpx.Client:
    proxies = proxy.strip() if proxy and proxy.strip() else None
    return httpx.Client(
        headers={"User-Agent": USER_AGENTS, "Accept-Language": "ja,zh-CN,zh,en-US;q=0.9"},
        cookies={"adultchecked": "1", "over18": "yes", "birthtime": "283993201", "lastagecheckage": "1-0-1980"},
        proxy=proxies,
        timeout=timeout,
        follow_redirects=True
    )


def download_and_cache_cover(img_url: str, filename_stem: str, proxy: Optional[str] = None, force: bool = False) -> str:
    """Downloads remote image, validates magic bytes, saves locally, and generates a grid thumbnail."""
    if not img_url:
        return ""
    if img_url.startswith("/api/covers/"):
        return img_url
    if img_url.startswith("//"):
        img_url = "https:" + img_url
    try:
        ext = ".jpg"
        low_url = img_url.lower().split("?")[0]
        if low_url.endswith(".png"):
            ext = ".png"
        elif low_url.endswith(".webp"):
            ext = ".webp"
        elif low_url.endswith(".gif"):
            ext = ".gif"

        safe_stem = re.sub(r'[\\/*?:"<>|]', "_", str(filename_stem))
        target_name = f"{safe_stem}{ext}"
        target_path = COVERS_DIR / target_name

        if not force and target_path.exists() and target_path.stat().st_size > 1024:
            generate_cover_thumbnail(target_path)
            return f"/api/covers/{target_name}"

        with get_http_client(proxy, timeout=6.5) as client:
            resp = client.get(img_url)
            if resp.status_code == 200 and is_valid_image_bytes(resp.content):
                with open(target_path, "wb") as f:
                    f.write(resp.content)
                generate_cover_thumbnail(target_path)
                return f"/api/covers/{target_name}"
    except Exception as e:
        print(f"Failed to cache cover {img_url}: {e}")
    return ""


def download_and_cache_samples(
    sample_urls: List[str],
    prefix_stem: str,
    proxy: Optional[str] = None,
    force: bool = False,
    max_count: int = 4
) -> List[str]:
    """Downloads and caches up to max_count official store preview images (Sample CGs)."""
    cached_list: List[str] = []
    if not sample_urls:
        return cached_list
    seen = set()
    for raw_u in sample_urls:
        if not raw_u or len(cached_list) >= max_count:
            break
        u = raw_u.strip()
        if u.startswith("//"):
            u = "https:" + u
        if u in seen:
            continue
        seen.add(u)
        idx = len(cached_list) + 1
        local_url = download_and_cache_cover(u, f"sample_{prefix_stem}_{idx}", proxy=proxy, force=force)
        if local_url:
            cached_list.append(local_url)
    return cached_list


def scrape_dlsite(rj_code: str, proxy: Optional[str] = None, force: bool = False) -> Optional[Dict[str, Any]]:
    """Scrapes DLsite product page by RJ/VJ/BJ code, including work_outline tags, CVs, and sample previews."""
    if not rj_code:
        return None

    code = rj_code.strip().upper()
    if not force:
        cached_meta = get_scrape_cache(code, "dlsite")
        if cached_meta and cached_meta.get("cover_url"):
            cached_meta["tags"] = normalize_and_localize_tags(cached_meta.get("tags", []), localize=True)
            return cached_meta

    subdomains = ["maniax", "home", "pro"]
    html_content = ""
    target_url = ""

    with get_http_client(proxy, timeout=4.5) as client:
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

    # Cover Image & Sample Slider Previews
    cover_url = ""
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        cover_url = og_img["content"]

    raw_sample_urls: List[str] = []
    slider_data = soup.find("div", class_="product-slider-data")
    if slider_data:
        for div_el in slider_data.find_all("div"):
            src = div_el.get("data-src") or div_el.get("data-thumb")
            if src:
                raw_sample_urls.append(src)

    if not raw_sample_urls:
        for img_el in soup.select(".work_slider img, .slider_items img, #work_left img"):
            src = img_el.get("src") or img_el.get("data-src")
            if src and ("_img_smp" in src or "_img_main" in src):
                raw_sample_urls.append(src)

    if not cover_url and raw_sample_urls:
        cover_url = raw_sample_urls[0]

    if cover_url.startswith("//"):
        cover_url = "https:" + cover_url

    # Inspect both #work_outline (where release date, CV, and genre tags live) and #work_maker
    tables = [t for t in (soup.find("table", id="work_outline"), soup.find("table", id="work_maker")) if t]
    release_date = ""
    voice_actors: List[str] = []
    tags: List[str] = []

    for table in tables:
        for tr in table.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if not th or not td:
                continue
            header_text = th.get_text(strip=True)
            val_text = td.get_text(strip=True)

            if "販売日" in header_text or "配信開始日" in header_text:
                m_date = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", val_text)
                if m_date:
                    release_date = f"{m_date.group(1)}-{int(m_date.group(2)):02d}-{int(m_date.group(3)):02d}"
                else:
                    release_date = re.sub(r"[^\d年-月日]", "", val_text).strip()
            elif "声優" in header_text:
                vas = [a.get_text(strip=True) for a in td.find_all("a") if a.get_text(strip=True)]
                voice_actors.extend(vas if vas else [v.strip() for v in re.split(r"[/／、,]+", val_text) if v.strip()])
            elif "ジャンル" in header_text or "作品形式" in header_text:
                tag_list = [a.get_text(strip=True) for a in td.find_all("a") if a.get_text(strip=True)]
                tags.extend(tag_list if tag_list else [t.strip() for t in val_text.split("/") if t.strip()])

    # Fallback genre div check
    if not tags:
        genre_div = soup.find("div", class_="main_genre")
        if genre_div:
            tags.extend([a.get_text(strip=True) for a in genre_div.find_all("a") if a.get_text(strip=True)])

    outline_el = (
        soup.find("div", class_="work_parts_area")
        or soup.find("div", class_="work_parts_multitype")
        or soup.find("div", class_="work_intro")
        or soup.find("div", itemprop="description")
    )
    synopsis = ""
    if outline_el:
        synopsis = outline_el.get_text(separator="\n", strip=True)

    cached_cover = download_and_cache_cover(cover_url, code, proxy, force=force)
    # Exclude the primary cover from sample_urls if identical, then cache up to 4 sample previews
    filtered_samples = [u for u in raw_sample_urls if u and not u.endswith(Path(cover_url).name)]
    if not filtered_samples and len(raw_sample_urls) > 1:
        filtered_samples = raw_sample_urls[1:]
    cached_samples = download_and_cache_samples(filtered_samples, code, proxy=proxy, force=force, max_count=4)
    banner_url = cached_samples[0] if cached_samples else cached_cover

    localized_tags = normalize_and_localize_tags(tags, localize=True)
    clean_vas = list(dict.fromkeys([v for v in voice_actors if v]))

    result = {
        "title": title,
        "original_title": title,
        "circle_name": maker,
        "release_date": release_date,
        "cover_url": cached_cover,
        "banner_url": banner_url or cached_cover,
        "sample_images": cached_samples,
        "synopsis": synopsis,
        "voice_actors": clean_vas,
        "tags": localized_tags,
        "source_url": target_url,
        "source_type": "dlsite",
        "rj_code": code,
        "rating_score": 0.0
    }
    set_scrape_cache(code, "dlsite", result)
    return result


def scrape_steam(keyword_or_appid: str, proxy: Optional[str] = None, force: bool = False) -> Optional[Dict[str, Any]]:
    """
    Scrapes Steam Store metadata for PC games by title search or Steam AppID.
    Separates vertical 2:3 Library Capsule (cover_url), horizontal Header Image (banner_url), and 4 sample screenshots.
    """
    if not keyword_or_appid or len(keyword_or_appid.strip()) < 1:
        return None

    query = keyword_or_appid.strip()
    if not force:
        cached_meta = get_scrape_cache(query, "steam")
        if cached_meta and cached_meta.get("cover_url"):
            cached_meta["tags"] = normalize_and_localize_tags(cached_meta.get("tags", []), localize=True)
            return cached_meta

    appid = None

    if query.isdigit():
        appid = int(query)
    else:
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
            cached_banner = download_and_cache_cover(header_img, f"steam_{appid}_banner", proxy, force=force)

            vertical_urls = [
                f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900_2x.jpg",
                f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900.jpg"
            ]
            cached_cover = ""
            for v_url in vertical_urls:
                cached_cover = download_and_cache_cover(v_url, f"steam_{appid}_cover", proxy, force=force)
                if cached_cover:
                    break
            if not cached_cover:
                cached_cover = cached_banner

            raw_shots = [
                s.get("path_thumbnail") or s.get("path_full")
                for s in (data.get("screenshots") or [])[:4]
                if isinstance(s, dict) and (s.get("path_thumbnail") or s.get("path_full"))
            ]
            cached_samples = download_and_cache_samples(raw_shots, f"steam_{appid}", proxy=proxy, force=force, max_count=4)

            synopsis_raw = data.get("short_description") or data.get("detailed_description") or data.get("about_the_game") or ""
            synopsis_clean = re.sub(r"<[^>]+>", "", synopsis_raw).strip()

            tags = []
            for g in data.get("genres", []):
                if g.get("description"):
                    tags.append(g["description"])
            for c in data.get("categories", []):
                if c.get("description") and len(tags) < 12:
                    tags.append(c["description"])

            localized_tags = normalize_and_localize_tags(tags, localize=True)

            result = {
                "title": name,
                "original_title": name,
                "circle_name": circle,
                "release_date": release_date,
                "cover_url": cached_cover,
                "banner_url": cached_banner or cached_cover,
                "sample_images": cached_samples,
                "synopsis": synopsis_clean,
                "voice_actors": [],
                "tags": localized_tags,
                "source_url": f"https://store.steampowered.com/app/{appid}",
                "source_type": "steam",
                "rating_score": 0.0
            }
            set_scrape_cache(query, "steam", result)
            return result
        except Exception as e:
            print(f"Steam appdetails error for {appid}: {e}")
            return None


def scrape_bangumi(keyword: str, proxy: Optional[str] = None, force: bool = False) -> Optional[Dict[str, Any]]:
    """Scrapes Bangumi API for Galgames/Visual Novels."""
    if not keyword or len(keyword.strip()) < 2:
        return None

    cleaned_kw = keyword.strip()
    if not force:
        cached_meta = get_scrape_cache(cleaned_kw, "bangumi")
        if cached_meta and cached_meta.get("cover_url"):
            cached_meta["tags"] = normalize_and_localize_tags(cached_meta.get("tags", []), localize=True)
            return cached_meta

    with get_http_client(proxy, timeout=5.0) as client:
        try:
            url = f"https://api.bgm.tv/search/subject/{urllib.parse.quote(cleaned_kw)}?type=4&responseGroup=large"
            r = client.get(url)
            items = []
            if r.status_code == 200:
                try:
                    data = r.json()
                    items = data.get("list", [])
                except Exception:
                    items = []
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

            cached_cover = download_and_cache_cover(cover_url, f"bgm_{sub_id}", proxy, force=force)
            localized_tags = normalize_and_localize_tags(tags[:12], localize=True)

            result = {
                "title": name_cn or name_jp,
                "original_title": name_jp,
                "circle_name": "",
                "release_date": release_date,
                "cover_url": cached_cover,
                "banner_url": cached_cover,
                "sample_images": [],
                "synopsis": summary,
                "voice_actors": [],
                "tags": localized_tags[:10],
                "source_url": f"https://bgm.tv/subject/{sub_id}",
                "source_type": "bangumi",
                "rating_score": float(rating) if rating else 0.0
            }
            set_scrape_cache(cleaned_kw, "bangumi", result)
            return result
        except Exception as e:
            print(f"Bangumi scrape error for '{cleaned_kw}': {e}")
            return None


def scrape_vndb(keyword: str, proxy: Optional[str] = None, force: bool = False) -> Optional[Dict[str, Any]]:
    """Scrapes VNDB Kana API for Visual Novels, including localized tags and up to 4 sample screenshots."""
    if not keyword or len(keyword.strip()) < 2:
        return None

    cleaned_kw = keyword.strip()
    if not force:
        cached_meta = get_scrape_cache(cleaned_kw, "vndb")
        if cached_meta and cached_meta.get("cover_url"):
            cached_meta["tags"] = normalize_and_localize_tags(cached_meta.get("tags", []), localize=True)
            return cached_meta

    with get_http_client(proxy, timeout=5.0) as client:
        try:
            url = "https://api.vndb.org/kana/vn"
            payload = {
                "filters": ["search", "=", cleaned_kw],
                "fields": "title, alttitle, description, image.url, screenshots.url, rating, released, developers.name, tags.name"
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
            raw_tags = [t.get("name") for t in best.get("tags", []) if t.get("name")][:14]
            localized_tags = normalize_and_localize_tags(raw_tags, localize=True)[:10]

            img_obj = best.get("image") or {}
            cover_url = img_obj.get("url") or ""
            cached_cover = download_and_cache_cover(cover_url, f"vndb_{vn_id}", proxy, force=force)

            raw_shots = [
                s.get("url")
                for s in (best.get("screenshots") or [])[:4]
                if isinstance(s, dict) and s.get("url")
            ]
            cached_samples = download_and_cache_samples(raw_shots, f"vndb_{vn_id}", proxy=proxy, force=force, max_count=4)
            banner_url = cached_samples[0] if cached_samples else cached_cover

            result = {
                "title": alttitle or title,
                "original_title": alttitle or title,
                "circle_name": ", ".join(devs),
                "release_date": released,
                "cover_url": cached_cover,
                "banner_url": banner_url or cached_cover,
                "sample_images": cached_samples,
                "synopsis": desc,
                "voice_actors": [],
                "tags": localized_tags,
                "source_url": f"https://vndb.org/{vn_id}",
                "source_type": "vndb",
                "rating_score": float(rating)
            }
            set_scrape_cache(cleaned_kw, "vndb", result)
            return result
        except Exception as e:
            print(f"VNDB scrape error for '{keyword}': {e}")
            return None


def scrape_game_auto(
    rj_code: Optional[str] = None,
    clean_title: Optional[str] = None,
    folder_name: Optional[str] = None,
    proxy: Optional[str] = None,
    preferred_source: str = "auto",
    force: bool = False
) -> Optional[Dict[str, Any]]:
    """Aggregated automatic scraper pipeline."""
    if preferred_source == "steam" and (clean_title or folder_name):
        res = scrape_steam(clean_title or folder_name, proxy=proxy, force=force)
        if res:
            return res

    if preferred_source == "dlsite" and rj_code:
        res = scrape_dlsite(rj_code.strip(), proxy=proxy, force=force)
        if res:
            return res

    if rj_code and rj_code.strip():
        res = scrape_dlsite(rj_code.strip(), proxy=proxy, force=force)
        if res:
            return res

    search_query = clean_title or folder_name or ""
    if search_query:
        if preferred_source in ("auto", "bangumi"):
            bgm_res = scrape_bangumi(search_query, proxy=proxy, force=force)
            if bgm_res:
                return bgm_res

        steam_res = scrape_steam(search_query, proxy=proxy, force=force)
        if steam_res:
            return steam_res

        vndb_res = scrape_vndb(search_query, proxy=proxy, force=force)
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
    Includes localized tags and sample_images.
    """
    candidates: List[Dict[str, Any]] = []

    if rj_code and rj_code.strip():
        try:
            dl_res = scrape_dlsite(rj_code.strip(), proxy=proxy)
            if dl_res:
                cov = dl_res.get("cover_url", "")
                cir = dl_res.get("circle_name", "")
                candidates.append({
                    "source": "dlsite",
                    "source_name": "DLsite (精确编号)",
                    "source_url": dl_res.get("source_url", ""),
                    "title": dl_res.get("title", ""),
                    "original_title": dl_res.get("original_title", ""),
                    "circle_name": cir,
                    "circle": cir,
                    "release_date": dl_res.get("release_date", ""),
                    "cover_url": cov,
                    "banner_url": dl_res.get("banner_url", cov),
                    "sample_images": dl_res.get("sample_images", []),
                    "cover_image": cov,
                    "synopsis": dl_res.get("synopsis", ""),
                    "tags": normalize_and_localize_tags(dl_res.get("tags", []), localize=True),
                    "voice_actors": dl_res.get("voice_actors", []),
                    "rj_code": rj_code.strip().upper(),
                    "rating_score": dl_res.get("rating_score", 0.0)
                })
        except Exception as e:
            print(f"Candidate DLsite error: {e}")

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
                        final_cov = cached_cover
                        tags = normalize_and_localize_tags([t.get("name") for t in item.get("tags", []) if t.get("name")][:10], localize=True)
                        candidates.append({
                            "source": "bangumi",
                            "source_name": "Bangumi (番组计划)",
                            "source_url": f"https://bgm.tv/subject/{sub_id}",
                            "title": name_cn or name_jp,
                            "original_title": name_jp,
                            "circle_name": "",
                            "circle": "",
                            "release_date": item.get("air_date") or item.get("date") or "",
                            "cover_url": final_cov,
                            "banner_url": final_cov,
                            "sample_images": [],
                            "cover_image": final_cov,
                            "synopsis": summary,
                            "tags": tags,
                            "voice_actors": [],
                            "rj_code": "",
                            "rating_score": float(item.get("rating", {}).get("score", 0.0) or 0.0)
                        })
        except Exception as e:
            print(f"Candidate Bangumi error: {e}")

    if kw and len(kw) >= 2:
        try:
            with get_http_client(proxy, timeout=5.0) as client:
                url = f"https://store.steampowered.com/api/storesearch/?term={urllib.parse.quote(kw)}&l=schinese&cc=CN"
                r = client.get(url)
                if r.status_code == 200:
                    items = r.json().get("items", [])[:2]
                    for item in items:
                        appid = item.get("id")
                        steam_detail = scrape_steam(str(appid), proxy=proxy) if appid else None
                        if steam_detail:
                            cov = steam_detail.get("cover_url") or ""
                            cir = steam_detail.get("circle_name", "")
                            candidates.append({
                                "source": "steam",
                                "source_name": "Steam 商店",
                                "source_url": steam_detail.get("source_url", f"https://store.steampowered.com/app/{appid}"),
                                "title": steam_detail.get("title", item.get("name", "")),
                                "original_title": steam_detail.get("original_title", item.get("name", "")),
                                "circle_name": cir,
                                "circle": cir,
                                "release_date": steam_detail.get("release_date", ""),
                                "cover_url": cov,
                                "banner_url": steam_detail.get("banner_url", cov),
                                "sample_images": steam_detail.get("sample_images", []),
                                "cover_image": cov,
                                "synopsis": steam_detail.get("synopsis", ""),
                                "tags": normalize_and_localize_tags(steam_detail.get("tags", []), localize=True),
                                "voice_actors": [],
                                "rj_code": "",
                                "rating_score": 0.0
                            })
        except Exception as e:
            print(f"Candidate Steam error: {e}")

    if kw and len(candidates) < 4:
        try:
            with get_http_client(proxy, timeout=5.0) as client:
                payload = {
                    "filters": ["search", "=", kw],
                    "fields": "title, alttitle, released, rating, image.url, description, developers.name, tags.name"
                }
                r = client.post("https://api.vndb.org/kana/vn", json=payload)
                if r.status_code == 200:
                    vn_items = r.json().get("results", [])[:2]
                    for item in vn_items:
                        vn_id = item.get("id")
                        raw_img = (item.get("image") or {}).get("url") or ""
                        cached_cover = download_and_cache_cover(raw_img, f"vndb_{vn_id}", proxy) if raw_img else ""
                        final_cov = cached_cover
                        cir = ", ".join([d.get("name", "") for d in item.get("developers", []) if d.get("name")])
                        desc = re.sub(r"\[/?\w+.*?\]", "", item.get("description") or "")
                        raw_tags = [t.get("name") for t in item.get("tags", []) if t.get("name")][:10]
                        candidates.append({
                            "source": "vndb",
                            "source_name": "VNDB (视觉小说数据库)",
                            "source_url": f"https://vndb.org/{vn_id}",
                            "title": item.get("alttitle") or item.get("title") or "",
                            "original_title": item.get("alttitle") or item.get("title") or "",
                            "circle_name": cir,
                            "circle": cir,
                            "release_date": item.get("released") or "",
                            "cover_url": final_cov,
                            "banner_url": final_cov,
                            "sample_images": [],
                            "cover_image": final_cov,
                            "synopsis": desc,
                            "tags": normalize_and_localize_tags(raw_tags, localize=True),
                            "voice_actors": [],
                            "rj_code": "",
                            "rating_score": round((float(item.get("rating") or 0.0)) / 10.0, 1)
                        })
        except Exception as e:
            print(f"Candidate VNDB error: {e}")

    return candidates
