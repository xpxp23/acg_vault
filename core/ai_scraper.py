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
from db.database import (
    get_all_games,
    upsert_game,
    manual_update_game_metadata,
    normalize_and_localize_tags,
    resolve_best_display_title
)
from core.scraper import (
    scrape_dlsite,
    scrape_bangumi,
    scrape_steam,
    scrape_vndb,
    download_and_cache_cover,
    get_http_client
)
from core.scanner import clean_title_from_folder, extract_rj_code


def call_llm_chat(
    messages: List[Dict[str, str]],
    cfg: Optional[Dict[str, Any]] = None,
    temperature: Optional[float] = None,
    max_tokens: int = 2200,
    timeout: float = 28.0
) -> Optional[str]:
    """Calls an OpenAI-compatible /v1/chat/completions endpoint."""
    if cfg is None:
        cfg = load_config()

    api_base = (cfg.get("llm_api_base") or "https://api.deepseek.com/v1").strip().rstrip("/")
    api_key = (cfg.get("llm_api_key") or "").strip()
    model = (cfg.get("llm_model") or "deepseek-chat").strip()
    temp = temperature if temperature is not None else float(cfg.get("llm_temperature", 0.3))
    proxy = (cfg.get("proxy") or "").strip() or None

    is_local_ollama = "127.0.0.1" in api_base or "localhost" in api_base
    if not api_key and not is_local_ollama:
        return None

    url = api_base if api_base.endswith("/chat/completions") else f"{api_base}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temp,
        "max_tokens": max_tokens,
        "stream": False
    }

    try:
        client_proxy = None if is_local_ollama else proxy
        with httpx.Client(proxy=client_proxy, timeout=timeout, follow_redirects=True) as client:
            r = client.post(url, headers=headers, json=payload)
            if r.status_code == 200:
                data = r.json()
                choices = data.get("choices") or []
                if choices:
                    content = (choices[0].get("message") or {}).get("content", "")
                    if content:
                        content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
                        return content
            else:
                print(f"[LLM] HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[LLM] Request failed: {e}")
    return None


def test_llm_connection(custom_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Verifies connectivity and model response for the configured LLM API."""
    cfg = load_config()
    if custom_cfg:
        cfg.update(custom_cfg)

    api_base = (cfg.get("llm_api_base") or "").strip()
    api_key = (cfg.get("llm_api_key") or "").strip()
    model = (cfg.get("llm_model") or "").strip()
    is_local = "127.0.0.1" in api_base or "localhost" in api_base

    if not api_base or not model:
        return {"success": False, "message": "请填写完整的 API Base URL 与模型名称 (Model)"}
    if not api_key and not is_local:
        return {"success": False, "message": "云端大模型需填写 API Key（本地 Ollama 可留空）"}

    t0 = time.time()
    reply = call_llm_chat(
        messages=[
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": "请回复“ACG Vault AI 引擎连接成功”这几个字。"}
        ],
        cfg=cfg,
        max_tokens=60,
        timeout=12.0
    )
    elapsed_ms = int((time.time() - t0) * 1000)
    if reply:
        return {
            "success": True,
            "latency_ms": elapsed_ms,
            "reply": reply[:80],
            "message": f"LLM 连接成功 ({elapsed_ms}ms) · 模型响应: {reply[:40]}"
        }
    return {
        "success": False,
        "message": "无法连接至 LLM 接口，请检查 API Base URL、Key、模型名或网络代理"
    }


def llm_parse_folder_metadata(folder_name: str, clues: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Uses LLM (with deterministic regex fallback) to extract structured metadata from messy
    folk-translated folder names.
    """
    clues = clues or {}
    fallback = _regex_parse_folder_metadata(folder_name, clues)

    cfg = load_config()
    if not cfg.get("llm_enabled"):
        return fallback

    prompt = (
        "你是一个专业的 ACG / Galgame / 同人游戏元数据提取器。请从下面的本地游戏文件夹名称和内部线索中，"
        "提取出纯净的游戏标题、日文原名（若有）、社团/开发商名、RJ/VJ号、版本号、汉化组/语言标签。只输出合法 JSON 对象，不要包含 Markdown 代码块之外的解释：\n"
        f"文件夹名: {folder_name}\n"
        f"内部线索: {json.dumps(clues, ensure_ascii=False)}\n"
        "JSON 字段格式:\n"
        '{"clean_title": "纯净主标题", "original_title": "日文或英文原名(不确定则留空)", "circle_name": "社团名(无则留空)", '
        '"rj_code": "RJ/VJ编号(无则留空)", "version": "如 v1.02", "translator_group": "汉化组名", "tags": ["标签1", "标签2"]}'
    )
    reply = call_llm_chat(
        messages=[
            {"role": "system", "content": "Only return valid JSON matching the requested schema."},
            {"role": "user", "content": prompt}
        ],
        cfg=cfg,
        temperature=0.1,
        max_tokens=400,
        timeout=12.0
    )
    if reply:
        try:
            m = re.search(r"\{.*\}", reply, flags=re.S)
            if m:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, dict) and parsed.get("clean_title"):
                    merged = fallback.copy()
                    for k in ("clean_title", "original_title", "circle_name", "rj_code", "version", "translator_group"):
                        if parsed.get(k):
                            merged[k] = str(parsed[k]).strip()
                    if isinstance(parsed.get("tags"), list) and parsed["tags"]:
                        merged["tags"] = normalize_and_localize_tags(
                            fallback.get("tags", []) + [str(t).strip() for t in parsed["tags"] if str(t).strip()],
                            localize=True
                        )
                    merged["used_llm"] = True
                    return merged
        except Exception:
            pass
    return fallback


def _regex_parse_folder_metadata(folder_name: str, clues: Dict[str, Any]) -> Dict[str, Any]:
    rj = clues.get("rj_code") or extract_rj_code(folder_name) or ""
    circle = ""
    tags = []
    translator = ""
    version = ""

    m_ver = re.search(r"\b(v(?:er)?\.?\s*\d+(?:\.\d+)*[a-zA-Z]?)\b", folder_name, re.I)
    if m_ver:
        version = m_ver.group(1).strip()

    brackets = re.findall(r"[\[\【\(（]([^\]\】\)）]+)[\]\】\)）]", folder_name)
    for b in brackets:
        b_clean = b.strip()
        if re.match(r"^[RVB]J\d{6,8}$", b_clean, re.I):
            if not rj:
                rj = b_clean.upper()
        elif re.match(r"^\d{6,8}$", b_clean):
            continue
        elif any(k in b_clean for k in ("汉化", "精翻", "官中", "中文", "巴比伦", "御光", "狐狸", "SSTM", "同人", "个人", "机翻", "润色")):
            translator = b_clean
            tags.append("汉化")
        elif any(k in b_clean.upper() for k in ("RPG", "SLG", "ADV", "ACT", "AVG", "NTR", "3D", "PC", "CV", "步兵", "动态")):
            for sub in re.split(r"[/\s\+、·]+", b_clean):
                if sub and len(sub) <= 10:
                    tags.append(sub)
        elif not circle and len(b_clean) >= 2 and b_clean.lower() not in ("pc", "内层", "完整版", "製品版"):
            circle = b_clean

    if not translator:
        m_trans = re.search(
            r"(巴比伦(?:汉化)?(?:组|版)?|御光(?:盟国)?(?:汉化)?(?:组|版)?|狐狸(?:汉化)?(?:组|版)?|SSTM(?:汉化)?|神乐(?:代理|官中)?|[\u4e00-\u9fa5A-Za-z0-9]{2,8}汉化(?:组|版)?|精翻汉化(?:版)?|官方中文(?:版)?|官中(?:版)?|AI精翻(?:版)?|个人汉化(?:版)?)",
            folder_name,
            re.I
        )
        if m_trans:
            translator = m_trans.group(1).strip()
            if "汉化" not in tags:
                tags.append("汉化")

    clean_t = clean_title_from_folder(folder_name)
    orig_t = clues.get("original_title") or (clean_t if re.search(r"[\u3040-\u30ff]", clean_t) else "")

    return {
        "clean_title": clean_t,
        "original_title": orig_t,
        "circle_name": circle,
        "rj_code": rj,
        "version": version,
        "translator_group": translator,
        "tags": normalize_and_localize_tags(tags, localize=True),
        "used_llm": False
    }


def _split_text_chunks(text: str, max_len: int = 1100) -> List[str]:
    """Splits long synopsis text along paragraph/sentence boundaries so translation never truncates."""
    paragraphs = text.split("\n")
    chunks: List[str] = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 1 <= max_len:
            current = f"{current}\n{p}" if current else p
        else:
            if current:
                chunks.append(current)
            if len(p) <= max_len:
                current = p
            else:
                for i in range(0, len(p), max_len):
                    chunks.append(p[i:i + max_len])
                current = ""
    if current:
        chunks.append(current)
    return chunks


def translate_japanese_to_chinese(text: str, proxy: Optional[str] = None) -> str:
    """Translates Japanese or English game synopses into Simplified Chinese."""
    if not text or len(text.strip()) < 5:
        return text

    cleaned_text = text.strip()
    has_kana = bool(re.search(r"[\u3040-\u30ff]", cleaned_text))
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", cleaned_text))
    ascii_letters = len(re.findall(r"[a-zA-Z]", cleaned_text))
    if not has_kana and cjk_count > 10 and ascii_letters < cjk_count * 2:
        return cleaned_text

    cfg = load_config()
    if cfg.get("llm_enabled") and cfg.get("llm_auto_translate", True):
        llm_res = call_llm_chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是一位资深的日本 ACG / 视觉小说 / 同人游戏本地化译者。请将用户提供的游戏简介准确、流畅、地道地翻译为简体中文，保留原有的分段与列表结构，不要输出任何额外解释。"
                },
                {"role": "user", "content": cleaned_text[:4500]}
            ],
            cfg=cfg,
            temperature=0.25,
            max_tokens=2000,
            timeout=18.0
        )
        if llm_res and len(llm_res) > 5:
            return llm_res

    source_lang = "ja" if has_kana else "auto"
    chunks = _split_text_chunks(cleaned_text, max_len=1100)
    translated_chunks: List[str] = []

    try:
        url = "https://translate.googleapis.com/translate_a/single"
        headers = {"User-Agent": "Mozilla/5.0"}
        with get_http_client(proxy, timeout=3.5) as client:
            for chunk in chunks:
                params = {
                    "client": "gtx",
                    "sl": source_lang,
                    "tl": "zh-CN",
                    "dt": "t",
                    "q": chunk
                }
                r = client.get(url, params=params, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    part_str = "".join([part[0] for part in data[0] if part and part[0]])
                    if part_str:
                        translated_chunks.append(part_str)
                    else:
                        translated_chunks.append(chunk)
                else:
                    translated_chunks.append(chunk)
        joined = "\n".join(translated_chunks).strip()
        if joined and joined != cleaned_text:
            return joined
    except Exception:
        pass

    try:
        sample_text = cleaned_text[:480]
        enc = urllib.parse.quote(sample_text)
        lang_pair = "ja|zh-CN" if has_kana else "en|zh-CN"
        mem_url = f"https://api.mymemory.translated.net/get?q={enc}&langpair={lang_pair}"
        with get_http_client(proxy, timeout=3.0) as client:
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
    force: bool = False,
    explicit_keyword: Optional[str] = None,
    explicit_rj: Optional[str] = None
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Complete AI scraping & translation pipeline for a single game,
    supporting DLsite, Bangumi, Steam, and VNDB while respecting preferred_source and user-customized titles.
    """
    cfg = load_config()
    pref = (preferred_source or cfg.get("scrape_source") or "auto").lower()

    fpath = game.get("folder_path")
    fname = game.get("folder_name", "")
    clean_t = game.get("clean_title") or clean_title_from_folder(fname)
    rj_code = (explicit_rj or game.get("rj_code") or extract_rj_code(fname) or "").strip()

    clues = find_internal_clues(fpath) if fpath else {}
    if not rj_code and clues.get("rj_code"):
        rj_code = clues["rj_code"]

    parsed_info = llm_parse_folder_metadata(fname, clues) if cfg.get("llm_enabled") else {}
    if not rj_code and parsed_info.get("rj_code"):
        rj_code = parsed_info["rj_code"]

    candidate_titles = []
    if explicit_keyword and explicit_keyword.strip():
        candidate_titles.append(explicit_keyword.strip())
    if parsed_info.get("original_title"):
        candidate_titles.append(parsed_info["original_title"])
    if parsed_info.get("clean_title") and parsed_info["clean_title"] not in candidate_titles:
        candidate_titles.append(parsed_info["clean_title"])
    if clues.get("original_title") and clues["original_title"] not in candidate_titles:
        candidate_titles.append(clues["original_title"])
    if clean_t and clean_t not in candidate_titles:
        candidate_titles.append(clean_t)
    if fname and fname not in candidate_titles:
        candidate_titles.append(fname)

    meta = None
    target_rj = rj_code

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

    merged_tags = normalize_and_localize_tags((meta.get("tags") or []) + (parsed_info.get("tags") or []), localize=True)
    if not merged_tags and game.get("tags"):
        merged_tags = normalize_and_localize_tags(game["tags"], localize=True)

    scraped_disp = meta.get("display_title") or meta.get("title") or clean_t or game["folder_name"]
    final_display_title = resolve_best_display_title(game, scraped_disp, fallback_title=clean_t or game["folder_name"])

    update_dict = {
        "folder_name": game["folder_name"],
        "folder_path": game["folder_path"],
        "rj_code": target_rj or meta.get("rj_code") or game.get("rj_code", ""),
        "display_title": final_display_title,
        "original_title": meta.get("original_title") or parsed_info.get("original_title") or game.get("original_title", ""),
        "cover_url": meta.get("cover_url") or game.get("cover_url", ""),
        "banner_url": meta.get("banner_url") or meta.get("cover_url") or game.get("banner_url", ""),
        "sample_images": meta.get("sample_images") or game.get("sample_images") or [],
        "synopsis": meta.get("synopsis") or game.get("synopsis", ""),
        "circle_name": meta.get("circle_name") or parsed_info.get("circle_name") or game.get("circle_name", ""),
        "release_date": meta.get("release_date") or game.get("release_date", ""),
        "voice_actors": meta.get("voice_actors") or game.get("voice_actors") or [],
        "tags": merged_tags,
        "source_url": meta.get("source_url") or game.get("source_url", ""),
        "source_type": meta.get("source_type") or "dlsite",
        "rating_score": meta.get("rating_score") or game.get("rating_score") or 0.0
    }
    upsert_game(update_dict)
    return True, update_dict
