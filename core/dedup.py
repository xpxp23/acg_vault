import re
import os
import shutil
import difflib
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

try:
    from rapidfuzz import fuzz
except ImportError:
    class _FallbackFuzz:
        @staticmethod
        def ratio(s1: str, s2: str) -> float:
            if not s1 and not s2:
                return 100.0
            if not s1 or not s2:
                return 0.0
            return difflib.SequenceMatcher(None, s1, s2).ratio() * 100.0

        @staticmethod
        def token_sort_ratio(s1: str, s2: str) -> float:
            t1 = " ".join(sorted(s1.split()))
            t2 = " ".join(sorted(s2.split()))
            return _FallbackFuzz.ratio(t1, t2)

    fuzz = _FallbackFuzz()

from db.database import (
    get_all_games,
    batch_update_duplicates,
    get_game_by_id,
    mark_archived,
    get_all_duplicate_ignores
)


def normalize_title_for_comparison(title: str) -> str:
    """Aggressively normalizes titles for fuzzy matching."""
    s = title.lower()
    # Remove version numbers v1.0, 1.292, ver1.0
    s = re.sub(r"(?:^|(?<=[\s_\-\.\[\(【（\u4e00-\u9fff\u3040-\u30ff]))v(?:er)?\.?\s*\d+(?:\.\d+)*[a-z]?", "", s)
    s = re.sub(r"\b\d+(?:\.\d+)+[a-z]?\b", "", s)
    # Remove common tags
    s = re.sub(r"(steam|pc|slg|rpg|adv|官中|汉化|步兵|无修|解码|精翻|硬盘版|内层|电脑|製品版|完整版|挂载)", "", s)
    # Keep alphanumeric, kanji/hanzi, kana, and full-width Roman numerals
    s = re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff\u2160-\u217f]", "", s)
    return s.strip()


ROMAN_SEQUEL_MAP = {
    'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10',
    'ⅰ': '1', 'ⅱ': '2', 'ⅲ': '3', 'ⅳ': '4', 'ⅴ': '5', 'ⅵ': '6', 'ⅶ': '7', 'ⅷ': '8', 'ⅸ': '9', 'ⅹ': '10',
    'Ⅰ': '1', 'Ⅱ': '2', 'Ⅲ': '3', 'Ⅳ': '4', 'Ⅴ': '5', 'Ⅵ': '6', 'Ⅶ': '7', 'Ⅷ': '8', 'Ⅸ': '9', 'Ⅹ': '10',
    '１': '1', '２': '2', '３': '3', '４': '4', '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
    '一': '1', '二': '2', '三': '3', '四': '4', '五': '5', '六': '6', '七': '7', '八': '8', '九': '9', '十': '10',
}


def extract_sequel_marker(s: str) -> Optional[str]:
    """
    Extracts sequel numbers accurately across English, Japanese, and Chinese titles
    (e.g., '状態異常Ⅲ', '黑兽2', 'Kuroinu II', 'Part 2') without false positives on normal English words.
    """
    if not s:
        return None
    # Strip out version strings first so 'Ver 2.0' or 'v1.02' is never mistaken for a sequel number
    cleaned = re.sub(r"(?:ver\.?|v)\s*\d+(?:\.\d+)*[a-z]?", " ", s, flags=re.I)
    cleaned = re.sub(r"\b\d+(?:\.\d+)+[a-z]?\b", " ", cleaned)
    cleaned = re.sub(r"[RVB]J\d{6,8}", " ", cleaned, flags=re.I)

    # 1. Check Unicode Roman numerals (Ⅰ..Ⅹ, ⅰ..ⅹ) anywhere in title
    m_uni_roman = re.findall(r"([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ])", cleaned)
    if m_uni_roman:
        raw = m_uni_roman[-1]
        return ROMAN_SEQUEL_MAP.get(raw, raw.lower())

    # 2. Check explicit '第X部/章/作/季' or 'Part/Season/Vol/Ep X'
    m_explicit = re.findall(
        r"(?:(?:part|season|vol|episode|ep|stage)\.?\s*([ivxIVX]+|\d+)|第([一二三四五六七八九十\d]+)[部章作季篇弹])",
        cleaned,
        flags=re.I
    )
    if m_explicit:
        token = (m_explicit[-1][0] or m_explicit[-1][1]).lower()
        return ROMAN_SEQUEL_MAP.get(token, token)

    # 3. Check multi-char ASCII Roman numerals (II, III, IV, VI, VII, VIII, IX) at word or CJK boundary
    m_ascii_roman = re.findall(
        r"(?:^|(?<=[\s_\-:\u4e00-\u9fff\u3040-\u30ff]))(viii|vii|iii|iv|vi|ix|ii)(?=$|[\s_\-:\(\[\【\（\u4e00-\u9fff\u3040-\u30ff])",
        cleaned,
        flags=re.I
    )
    if m_ascii_roman:
        raw = m_ascii_roman[-1].lower()
        return ROMAN_SEQUEL_MAP.get(raw, raw)

    # 4. Check standalone Arabic or full-width digits (1-20) attached to CJK or word boundaries
    m_digits = re.findall(
        r"(?:^|(?<=[\s_\-:\u4e00-\u9fff\u3040-\u30ffa-zA-Z]))([１２３４５６７８９]|\d{1,2})(?=$|[\s_\-:\(\[\【\（\u4e00-\u9fff\u3040-\u30ff])",
        cleaned
    )
    if m_digits:
        raw = m_digits[-1]
        return ROMAN_SEQUEL_MAP.get(raw, raw)

    return None


def has_different_sequel_number(t1: str, t2: str) -> bool:
    """Prevents grouping sequels like Game 1 and Game 2 / Base Game vs Game 2 / Game II / 状態異常Ⅲ."""
    m1 = extract_sequel_marker(t1)
    m2 = extract_sequel_marker(t2)
    if m1 is not None and m2 is not None and m1 != m2:
        return True
    if (m1 is not None and m1 not in ('1', '0')) and m2 is None:
        return True
    if (m2 is not None and m2 not in ('1', '0')) and m1 is None:
        return True
    return False


def compute_duplicates_and_update_db() -> int:
    """
    Analyzes all active games in database, clusters duplicates, and updates duplicate_group_id.
    Respects user duplicate_ignores.
    Returns total count of duplicate items found.
    """
    games = get_all_games(status="all", is_tool=False)
    if not games:
        return 0

    ignores = get_all_duplicate_ignores()

    n = len(games)
    parent = list(range(n))

    def find(i: int) -> int:
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i: int, j: int):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    # Pairwise comparison
    for i in range(n):
        g1 = games[i]
        id1 = g1["id"]
        rj1 = g1.get("rj_code", "").strip().upper()
        t1 = g1.get("clean_title") or g1.get("folder_name")
        norm1 = normalize_title_for_comparison(t1)

        for j in range(i + 1, n):
            g2 = games[j]
            id2 = g2["id"]

            pair = (min(id1, id2), max(id1, id2))
            if pair in ignores:
                continue

            rj2 = g2.get("rj_code", "").strip().upper()
            t2 = g2.get("clean_title") or g2.get("folder_name")
            norm2 = normalize_title_for_comparison(t2)

            # Match 1: Exact RJ Code (both non-empty)
            if rj1 and rj2 and rj1 == rj2:
                if norm1 and norm2 and len(norm1) >= 2 and len(norm2) >= 2:
                    ratio = fuzz.ratio(norm1, norm2)
                    token_ratio = fuzz.token_sort_ratio(norm1, norm2)
                    if max(ratio, token_ratio) < 25:
                        continue
                union(i, j)
                continue

            # Check sequel difference
            if has_different_sequel_number(t1, t2):
                continue

            # Match 2: Exact Normalized Title
            if norm1 and norm2 and len(norm1) >= 2 and norm1 == norm2:
                union(i, j)
                continue

            # Match 3: High similarity fuzzy match (e.g. 88+)
            if norm1 and norm2 and len(norm1) >= 4 and len(norm2) >= 4:
                ratio = fuzz.ratio(norm1, norm2)
                token_ratio = fuzz.token_sort_ratio(norm1, norm2)
                if max(ratio, token_ratio) >= 88:
                    union(i, j)
                    continue

    # Group into clusters
    clusters: Dict[int, List[Dict[str, Any]]] = {}
    for i in range(n):
        root = find(i)
        if root not in clusters:
            clusters[root] = []
        clusters[root].append(games[i])

    total_duplicates = 0
    dup_updates: List[Tuple[Optional[str], int, int]] = []

    for root, group in clusters.items():
        if len(group) > 1:
            min_id = min(g["id"] for g in group)
            group_id = f"dup_{min_id}"
            dup_count = len(group) - 1
            total_duplicates += len(group)
            for g in group:
                dup_updates.append((group_id, dup_count, g["id"]))
        else:
            dup_updates.append((None, 0, group[0]["id"]))

    batch_update_duplicates(dup_updates)
    return total_duplicates


def archive_game_directory(game_id: int, archive_root: str) -> Tuple[bool, str]:
    """
    Safely moves duplicate game directory to archive directory.
    Marks game as archived in DB.
    """
    game = get_game_by_id(game_id)
    if not game:
        return False, "游戏不存在"

    src_path = Path(game["folder_path"])
    if not src_path.exists():
        mark_archived(game_id)
        compute_duplicates_and_update_db()
        return True, "源目录已不存在，已从游戏库标记归档"

    dest_root = Path(archive_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    dest_dir = dest_root / src_path.name
    if dest_dir.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_dir = dest_root / f"{src_path.name}_{timestamp}"

    try:
        shutil.move(str(src_path), str(dest_dir))
        mark_archived(game_id)
        compute_duplicates_and_update_db()
        return True, f"成功归档至 {dest_dir}"
    except Exception as e:
        return False, f"归档失败: {str(e)}"


def dismiss_duplicate(game_id: int, target_id: Optional[int] = None) -> Tuple[bool, str]:
    """
    Unlinks a game from duplicate grouping and persists ignore pairs.
    Immediately recalculates duplicates in DB.
    """
    from db.database import dismiss_game_from_duplicates
    dismiss_game_from_duplicates(game_id, target_id)
    compute_duplicates_and_update_db()
    return True, "已成功取消重复版本标记（判定为独立非重复游戏）"
