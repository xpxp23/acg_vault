import sqlite3
import json
import os
from contextlib import contextmanager
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from config import DB_PATH

TRANSLATED_SQL_COND = (
    "(has_translation = 1 "
    "OR folder_name LIKE '%汉化%' OR folder_name LIKE '%官中%' OR folder_name LIKE '%中文%' OR folder_name LIKE '%精翻%' "
    "OR display_title LIKE '%汉化%' OR display_title LIKE '%官中%' OR display_title LIKE '%中文%' "
    "OR tags LIKE '%汉化%' OR tags LIKE '%官中%' OR tags LIKE '%中文%' "
    "OR user_tags LIKE '%汉化%' OR user_tags LIKE '%官中%' OR user_tags LIKE '%中文%')"
)

HAS_NOTES_SQL_COND = (
    "(user_notes IS NOT NULL AND TRIM(REPLACE(REPLACE(REPLACE(user_notes, CHAR(10), ''), CHAR(13), ''), '　', '')) != '')"
)

TRANSLATION_KEYWORDS = ("汉化", "官中", "中文", "精翻", "chs", "zh-cn", "zh_cn")

LIGHTWEIGHT_GAME_COLUMNS = f"""
    id, folder_name, folder_path, clean_title, display_title, original_title,
    rj_code, engine_type, executable_path, folder_size_bytes, folder_size_str,
    folder_modified_at, downloaded_at, cover_url, banner_url,
    SUBSTR(COALESCE(synopsis, ''), 1, 260) AS synopsis,
    circle_name, release_date, voice_actors, tags, source_url, source_type, rating_score,
    play_status, user_rating,
    SUBSTR(TRIM(COALESCE(user_notes, '')), 1, 180) AS user_notes,
    CASE WHEN {HAS_NOTES_SQL_COND} THEN 1 ELSE 0 END AS has_notes_flag,
    LENGTH(TRIM(COALESCE(user_notes, ''))) AS notes_length,
    user_tags, is_favorite, play_count, played_seconds, last_played_at, first_played_at,
    duplicate_group_id, duplicate_count, is_archived, is_tool, has_translation, is_missing,
    COALESCE(screenshot_count, 0) AS screenshot_count,
    COALESCE(cg_unlocked, 0) AS cg_unlocked,
    created_at, updated_at
"""


def format_bytes_short(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=25000;")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
    except Exception:
        pass
    return conn


@contextmanager
def db_session(commit: bool = False):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield conn, cursor
        if commit:
            conn.commit()
    except Exception:
        if commit:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        conn.close()


def init_db():
    with db_session(commit=True) as (conn, cursor):
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_name TEXT NOT NULL,
            folder_path TEXT NOT NULL UNIQUE,
            clean_title TEXT,
            display_title TEXT,
            original_title TEXT,
            rj_code TEXT,
            engine_type TEXT,
            executable_path TEXT,
            folder_size_bytes INTEGER DEFAULT 0,
            folder_size_str TEXT,
            folder_modified_at TEXT,
            downloaded_at TEXT,
            cover_url TEXT,
            banner_url TEXT,
            synopsis TEXT,
            circle_name TEXT,
            release_date TEXT,
            voice_actors TEXT,
            tags TEXT,
            source_url TEXT,
            source_type TEXT DEFAULT 'none',
            rating_score REAL DEFAULT 0.0,

            play_status TEXT DEFAULT 'unplayed',
            user_rating INTEGER DEFAULT 0,
            user_notes TEXT DEFAULT '',
            user_tags TEXT DEFAULT '[]',
            is_favorite INTEGER DEFAULT 0,
            play_count INTEGER DEFAULT 0,
            played_seconds INTEGER DEFAULT 0,
            last_played_at TEXT,
            first_played_at TEXT,

            duplicate_group_id TEXT,
            duplicate_count INTEGER DEFAULT 0,
            is_archived INTEGER DEFAULT 0,
            is_tool INTEGER DEFAULT 0,
            has_translation INTEGER DEFAULT 0,
            is_missing INTEGER DEFAULT 0,
            screenshot_count INTEGER DEFAULT 0,
            cg_unlocked INTEGER DEFAULT 0,

            created_at TEXT,
            updated_at TEXT
        );
        """)

        for col_sql in [
            "ALTER TABLE games ADD COLUMN downloaded_at TEXT;",
            "ALTER TABLE games ADD COLUMN has_translation INTEGER DEFAULT 0;",
            "ALTER TABLE games ADD COLUMN is_missing INTEGER DEFAULT 0;",
            "ALTER TABLE games ADD COLUMN screenshot_count INTEGER DEFAULT 0;",
            "ALTER TABLE games ADD COLUMN cg_unlocked INTEGER DEFAULT 0;"
        ]:
            try:
                cursor.execute(col_sql)
            except Exception:
                pass

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_folder_path ON games(folder_path);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_play_status ON games(play_status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rj_code ON games(rj_code);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_clean_title ON games(clean_title);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_duplicate_group ON games(duplicate_group_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_engine_type ON games(engine_type);")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrape_cache (
            query_key TEXT PRIMARY KEY,
            source TEXT,
            data_json TEXT,
            updated_at TEXT
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS duplicate_ignores (
            game_id_1 INTEGER NOT NULL,
            game_id_2 INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (game_id_1, game_id_2)
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dup_ignores ON duplicate_ignores(game_id_1, game_id_2);")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_screenshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            caption TEXT DEFAULT '',
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            size_bytes INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_screenshots_game_id ON game_screenshots(game_id);")


def _clean_note_str(s: Optional[str]) -> str:
    if not s:
        return ""
    return s.replace("\r", "").replace("\n", "").replace("\u3000", "").strip()


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    if d.get("tags") and isinstance(d["tags"], str):
        try:
            d["tags"] = json.loads(d["tags"])
        except Exception:
            d["tags"] = [t.strip() for t in d["tags"].split(",") if t.strip()]
    else:
        d["tags"] = d.get("tags") or []

    if d.get("user_tags") and isinstance(d["user_tags"], str):
        try:
            d["user_tags"] = json.loads(d["user_tags"])
        except Exception:
            d["user_tags"] = [t.strip() for t in d["user_tags"].split(",") if t.strip()]
    else:
        d["user_tags"] = d.get("user_tags") or []

    if d.get("voice_actors") and isinstance(d["voice_actors"], str):
        try:
            d["voice_actors"] = json.loads(d["voice_actors"])
        except Exception:
            d["voice_actors"] = [t.strip() for t in d["voice_actors"].split(",") if t.strip()]
    else:
        d["voice_actors"] = d.get("voice_actors") or []

    combined_text = " ".join([
        str(d.get("folder_name") or ""),
        str(d.get("display_title") or ""),
        " ".join(str(t) for t in d["tags"]),
        " ".join(str(t) for t in d["user_tags"])
    ]).lower()
    d["is_translated"] = 1 if (
        int(d.get("has_translation") or 0) == 1
        or any(kw in combined_text for kw in TRANSLATION_KEYWORDS)
    ) else 0

    if "has_notes_flag" in d:
        d["has_notes"] = int(d.pop("has_notes_flag") or 0)
    else:
        d["has_notes"] = 1 if len(_clean_note_str(d.get("user_notes"))) > 0 else 0

    if "notes_length" not in d:
        d["notes_length"] = len((d.get("user_notes") or "").strip())

    d["screenshot_count"] = int(d.get("screenshot_count") or 0)
    d["cg_unlocked"] = int(d.get("cg_unlocked") or 0)

    return d


def _build_filter_clause(
    keyword: Optional[str] = None,
    favorite_only: bool = False,
    duplicates_only: bool = False,
    missing_only: bool = False,
    is_tool: bool = False,
    has_notes_only: bool = False,
    engine_filter: Optional[str] = None,
    trans_filter: Optional[str] = None,
    unscraped_only: bool = False
) -> Tuple[str, List[Any]]:
    clause = " WHERE is_archived = 0 AND is_tool = ?"
    params: List[Any] = [1 if is_tool else 0]

    if favorite_only:
        clause += " AND is_favorite = 1"

    if duplicates_only:
        clause += " AND duplicate_count > 0"

    if missing_only:
        clause += " AND is_missing = 1"

    if has_notes_only:
        clause += f" AND {HAS_NOTES_SQL_COND}"

    if engine_filter and engine_filter != "all":
        clause += " AND engine_type LIKE ?"
        params.append(f"%{engine_filter}%")

    if trans_filter == "translated":
        clause += f" AND {TRANSLATED_SQL_COND}"
    elif trans_filter == "raw":
        clause += f" AND NOT {TRANSLATED_SQL_COND}"

    if unscraped_only:
        clause += " AND (cover_url IS NULL OR TRIM(cover_url) = '' OR synopsis IS NULL OR TRIM(synopsis) = '')"

    if keyword and keyword.strip():
        k = f"%{keyword.strip()}%"
        clause += (
            " AND (folder_name LIKE ? OR clean_title LIKE ? OR display_title LIKE ? "
            "OR original_title LIKE ? OR circle_name LIKE ? OR rj_code LIKE ? "
            "OR tags LIKE ? OR user_tags LIKE ? OR voice_actors LIKE ?)"
        )
        params.extend([k, k, k, k, k, k, k, k, k])

    return clause, params


def get_filtered_status_counts(
    keyword: Optional[str] = None,
    favorite_only: bool = False,
    duplicates_only: bool = False,
    missing_only: bool = False,
    is_tool: bool = False,
    has_notes_only: bool = False,
    engine_filter: Optional[str] = None,
    trans_filter: Optional[str] = None,
    unscraped_only: bool = False
) -> Dict[str, int]:
    clause, params = _build_filter_clause(
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
    sql = f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN play_status = 'unplayed' THEN 1 ELSE 0 END) as unplayed,
            SUM(CASE WHEN play_status = 'playing' THEN 1 ELSE 0 END) as playing,
            SUM(CASE WHEN play_status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN play_status = 'dropped' THEN 1 ELSE 0 END) as dropped,
            SUM(CASE WHEN play_status = 'backlog' THEN 1 ELSE 0 END) as backlog
        FROM games
        {clause}
    """
    with db_session(commit=False) as (_, cursor):
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return {
            "all": (row["total"] or 0) if row else 0,
            "unplayed": (row["unplayed"] or 0) if row else 0,
            "playing": (row["playing"] or 0) if row else 0,
            "completed": (row["completed"] or 0) if row else 0,
            "dropped": (row["dropped"] or 0) if row else 0,
            "backlog": (row["backlog"] or 0) if row else 0,
        }


def get_all_games(
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    favorite_only: bool = False,
    duplicates_only: bool = False,
    missing_only: bool = False,
    is_tool: bool = False,
    has_notes_only: bool = False,
    engine_filter: Optional[str] = None,
    trans_filter: Optional[str] = None,
    unscraped_only: bool = False,
    sort_by: str = "title",
    sort_order: str = "asc",
    include_full_notes: bool = False
) -> List[Dict[str, Any]]:
    clause, params = _build_filter_clause(
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
    cols = "*" if include_full_notes else LIGHTWEIGHT_GAME_COLUMNS
    query = f"SELECT {cols} FROM games {clause}"

    if status and status != "all":
        query += " AND play_status = ?"
        params.append(status)

    sort_map = {
        "title": "display_title",
        "clean_title": "clean_title",
        "name": "folder_name",
        "date_added": "created_at",
        "downloaded_at": "downloaded_at",
        "download_date": "downloaded_at",
        "last_played": "last_played_at",
        "play_time": "played_seconds",
        "rating": "user_rating",
        "release_date": "release_date",
        "size": "folder_size_bytes"
    }
    col = sort_map.get(sort_by, "display_title")
    order = "DESC" if sort_order.lower() == "desc" else "ASC"

    if col in ("last_played_at", "release_date", "downloaded_at", "user_rating", "created_at"):
        query += f" ORDER BY ({col} IS NULL OR {col} = '') ASC, {col} {order}, display_title ASC"
    else:
        query += f" ORDER BY {col} {order}, display_title ASC"

    with db_session(commit=False) as (_, cursor):
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [row_to_dict(r) for r in rows]


def get_game_by_id(game_id: int) -> Optional[Dict[str, Any]]:
    with db_session(commit=False) as (_, cursor):
        cursor.execute("SELECT * FROM games WHERE id = ?", (game_id,))
        row = cursor.fetchone()
        return row_to_dict(row) if row else None


def get_game_by_path(folder_path: str) -> Optional[Dict[str, Any]]:
    with db_session(commit=False) as (_, cursor):
        cursor.execute("SELECT * FROM games WHERE folder_path = ?", (folder_path,))
        row = cursor.fetchone()
        return row_to_dict(row) if row else None


def get_existing_scan_cache() -> Dict[str, Dict[str, Any]]:
    """Returns normalized folder_path -> existing row metadata for fast incremental directory scanning."""
    with db_session(commit=False) as (_, cursor):
        cursor.execute("""
            SELECT id, folder_name, folder_path, clean_title, display_title, rj_code,
                   engine_type, executable_path, folder_size_bytes, folder_size_str,
                   folder_modified_at, downloaded_at, is_tool, has_translation
            FROM games
            WHERE is_archived = 0
        """)
        rows = cursor.fetchall()
        cache: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            d = dict(r)
            norm_p = os.path.normcase(os.path.normpath(d["folder_path"]))
            cache[norm_p] = d
        return cache


def upsert_game(game_data: Dict[str, Any]) -> int:
    now = datetime.now().isoformat()

    tags_str = json.dumps(game_data.get("tags", []), ensure_ascii=False) if isinstance(game_data.get("tags"), list) else game_data.get("tags", "[]")
    user_tags_str = json.dumps(game_data.get("user_tags", []), ensure_ascii=False) if isinstance(game_data.get("user_tags"), list) else game_data.get("user_tags", "[]")
    va_str = json.dumps(game_data.get("voice_actors", []), ensure_ascii=False) if isinstance(game_data.get("voice_actors"), list) else game_data.get("voice_actors", "[]")

    with db_session(commit=True) as (_, cursor):
        cursor.execute("SELECT * FROM games WHERE folder_path = ?", (game_data["folder_path"],))
        existing_row = cursor.fetchone()
        existing = row_to_dict(existing_row) if existing_row else None

        if existing:
            game_id = existing["id"]
            update_fields = [
                "folder_name = ?", "clean_title = ?", "engine_type = ?", "executable_path = ?",
                "folder_size_bytes = ?", "folder_size_str = ?", "folder_modified_at = ?",
                "updated_at = ?", "is_tool = ?"
            ]
            values = [
                game_data["folder_name"],
                game_data.get("clean_title") or existing["clean_title"],
                game_data.get("engine_type") or existing["engine_type"],
                game_data.get("executable_path") or existing["executable_path"],
                game_data.get("folder_size_bytes", existing.get("folder_size_bytes", 0)),
                game_data.get("folder_size_str") or existing.get("folder_size_str", ""),
                game_data.get("folder_modified_at") or existing.get("folder_modified_at", ""),
                now,
                game_data.get("is_tool", existing.get("is_tool", 0))
            ]

            if "downloaded_at" in game_data and game_data["downloaded_at"]:
                update_fields.append("downloaded_at = ?")
                values.append(game_data["downloaded_at"])

            if "has_translation" in game_data and game_data["has_translation"] is not None:
                update_fields.append("has_translation = ?")
                values.append(int(game_data["has_translation"]))

            for field in ["rj_code", "display_title", "original_title", "cover_url", "banner_url",
                          "synopsis", "circle_name", "release_date", "source_url", "source_type", "rating_score"]:
                if field in game_data and game_data[field] is not None:
                    update_fields.append(f"{field} = ?")
                    values.append(game_data[field])

            if "tags" in game_data and game_data["tags"]:
                update_fields.append("tags = ?")
                values.append(tags_str)

            if "user_tags" in game_data and game_data["user_tags"] is not None:
                update_fields.append("user_tags = ?")
                values.append(user_tags_str)

            if "voice_actors" in game_data and game_data["voice_actors"]:
                update_fields.append("voice_actors = ?")
                values.append(va_str)

            values.append(game_id)
            cursor.execute(f"UPDATE games SET {', '.join(update_fields)} WHERE id = ?", values)
        else:
            fields = [
                "folder_name", "folder_path", "clean_title", "display_title", "original_title",
                "rj_code", "engine_type", "executable_path", "folder_size_bytes", "folder_size_str",
                "folder_modified_at", "downloaded_at", "cover_url", "banner_url", "synopsis", "circle_name",
                "release_date", "voice_actors", "tags", "source_url", "source_type", "rating_score",
                "play_status", "user_rating", "user_notes", "user_tags", "is_favorite",
                "is_tool", "has_translation", "created_at", "updated_at"
            ]
            placeholders = ", ".join(["?"] * len(fields))
            values = [
                game_data["folder_name"],
                game_data["folder_path"],
                game_data.get("clean_title", game_data["folder_name"]),
                game_data.get("display_title", game_data.get("clean_title", game_data["folder_name"])),
                game_data.get("original_title", ""),
                game_data.get("rj_code", ""),
                game_data.get("engine_type", "Unknown"),
                game_data.get("executable_path", ""),
                game_data.get("folder_size_bytes", 0),
                game_data.get("folder_size_str", "0 MB"),
                game_data.get("folder_modified_at", ""),
                game_data.get("downloaded_at", ""),
                game_data.get("cover_url", ""),
                game_data.get("banner_url", ""),
                game_data.get("synopsis", ""),
                game_data.get("circle_name", ""),
                game_data.get("release_date", ""),
                va_str,
                tags_str,
                game_data.get("source_url", ""),
                game_data.get("source_type", "none"),
                game_data.get("rating_score", 0.0),
                game_data.get("play_status", "unplayed"),
                game_data.get("user_rating", 0),
                game_data.get("user_notes", ""),
                user_tags_str,
                game_data.get("is_favorite", 0),
                game_data.get("is_tool", 0),
                int(game_data.get("has_translation", 0)),
                now,
                now
            ]
            cursor.execute(f"INSERT INTO games ({', '.join(fields)}) VALUES ({placeholders})", values)
            game_id = cursor.lastrowid

    return game_id


def batch_upsert_games(games_list: List[Dict[str, Any]]):
    """Performs fast transaction batch upsert for scanned games, protecting user-customized fields."""
    if not games_list:
        return
    now = datetime.now().isoformat()

    with db_session(commit=True) as (_, cursor):
        cursor.execute("SELECT id, folder_path, folder_name, clean_title, engine_type, executable_path, downloaded_at FROM games")
        existing_map = {row["folder_path"]: dict(row) for row in cursor.fetchall()}

        for g in games_list:
            fpath = g["folder_path"]
            tags_str = json.dumps(g.get("tags", []), ensure_ascii=False)
            va_str = json.dumps(g.get("voice_actors", []), ensure_ascii=False)
            has_trs = int(g.get("has_translation", 0))

            if fpath in existing_map:
                ex = existing_map[fpath]
                gid = ex["id"]
                prev_exe = ex.get("executable_path") or ""
                final_exe = prev_exe if (prev_exe and os.path.exists(prev_exe)) else (g.get("executable_path") or prev_exe)

                prev_clean = ex.get("clean_title") or ""
                new_clean = g.get("clean_title") or prev_clean
                if prev_clean and prev_clean != ex.get("folder_name") and g["folder_name"] == ex.get("folder_name"):
                    final_clean = prev_clean
                else:
                    final_clean = new_clean

                cursor.execute("""
                    UPDATE games SET
                        folder_name = ?,
                        clean_title = ?,
                        engine_type = ?,
                        executable_path = ?,
                        folder_size_bytes = ?,
                        folder_size_str = ?,
                        folder_modified_at = ?,
                        downloaded_at = COALESCE(NULLIF(downloaded_at, ''), ?),
                        is_tool = ?,
                        has_translation = ?,
                        is_missing = 0,
                        rj_code = CASE WHEN (rj_code IS NULL OR rj_code = '') AND ? != '' THEN ? ELSE rj_code END,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    g["folder_name"], final_clean, g.get("engine_type"), final_exe,
                    g.get("folder_size_bytes", 0), g.get("folder_size_str", ""), g.get("folder_modified_at", ""),
                    g.get("downloaded_at", ""), g.get("is_tool", 0), has_trs,
                    g.get("rj_code", ""), g.get("rj_code", ""), now, gid
                ))
            else:
                fields = [
                    "folder_name", "folder_path", "clean_title", "display_title", "original_title",
                    "rj_code", "engine_type", "executable_path", "folder_size_bytes", "folder_size_str",
                    "folder_modified_at", "downloaded_at", "cover_url", "banner_url", "synopsis", "circle_name",
                    "release_date", "voice_actors", "tags", "source_url", "source_type", "rating_score",
                    "play_status", "user_rating", "user_notes", "user_tags", "is_favorite",
                    "is_tool", "has_translation", "is_missing", "created_at", "updated_at"
                ]
                cursor.execute(f"INSERT INTO games ({', '.join(fields)}) VALUES ({', '.join(['?']*len(fields))})", (
                    g["folder_name"], g["folder_path"], g.get("clean_title", g["folder_name"]),
                    g.get("display_title", g.get("clean_title", g["folder_name"])), "",
                    g.get("rj_code", ""), g.get("engine_type", "Unknown"), g.get("executable_path", ""),
                    g.get("folder_size_bytes", 0), g.get("folder_size_str", "0 MB"), g.get("folder_modified_at", ""),
                    g.get("downloaded_at", ""), "", "", "", "", "", va_str, tags_str, "", "none", 0.0,
                    "unplayed", 0, "", "[]", 0, g.get("is_tool", 0), has_trs, 0, now, now
                ))


def manual_update_game_metadata(game_id: int, data: Dict[str, Any]) -> bool:
    """Allows full manual customization/modification of game metadata."""
    now = datetime.now().isoformat()

    fields = ["updated_at = ?"]
    values: List[Any] = [now]

    allowed_fields = [
        "display_title", "original_title", "circle_name", "release_date",
        "downloaded_at", "cover_url", "banner_url", "synopsis", "rj_code",
        "source_type", "source_url", "rating_score", "executable_path",
        "has_translation", "cg_unlocked", "screenshot_count"
    ]

    for key in allowed_fields:
        if key in data and data[key] is not None:
            fields.append(f"{key} = ?")
            values.append(data[key])

    if "tags" in data and data["tags"] is not None:
        fields.append("tags = ?")
        tags_val = json.dumps(data["tags"], ensure_ascii=False) if isinstance(data["tags"], list) else str(data["tags"])
        values.append(tags_val)

    if "user_tags" in data and data["user_tags"] is not None:
        fields.append("user_tags = ?")
        utags_val = json.dumps(data["user_tags"], ensure_ascii=False) if isinstance(data["user_tags"], list) else str(data["user_tags"])
        values.append(utags_val)

    if "voice_actors" in data and data["voice_actors"] is not None:
        fields.append("voice_actors = ?")
        va_val = json.dumps(data["voice_actors"], ensure_ascii=False) if isinstance(data["voice_actors"], list) else str(data["voice_actors"])
        values.append(va_val)

    values.append(game_id)
    with db_session(commit=True) as (_, cursor):
        cursor.execute(f"UPDATE games SET {', '.join(fields)} WHERE id = ?", values)
    return True


def update_game_user_state(
    game_id: int,
    play_status: Optional[str] = None,
    user_rating: Optional[int] = None,
    user_notes: Optional[str] = None,
    user_tags: Optional[List[str]] = None,
    is_favorite: Optional[int] = None,
    display_title: Optional[str] = None,
    executable_path: Optional[str] = None
) -> bool:
    fields = ["updated_at = ?"]
    now = datetime.now().isoformat()
    values: List[Any] = [now]

    if play_status is not None:
        fields.append("play_status = ?")
        values.append(play_status)
    if user_rating is not None:
        fields.append("user_rating = ?")
        values.append(user_rating)
    if user_notes is not None:
        fields.append("user_notes = ?")
        values.append(user_notes)
    if user_tags is not None:
        fields.append("user_tags = ?")
        values.append(json.dumps(user_tags, ensure_ascii=False))
    if is_favorite is not None:
        fields.append("is_favorite = ?")
        values.append(is_favorite)
    if display_title is not None:
        fields.append("display_title = ?")
        values.append(display_title)
    if executable_path is not None:
        fields.append("executable_path = ?")
        values.append(executable_path)

    values.append(game_id)
    with db_session(commit=True) as (_, cursor):
        cursor.execute(f"UPDATE games SET {', '.join(fields)} WHERE id = ?", values)
    return True


def record_game_launch(game_id: int, duration_seconds: int = 0, increment_count: bool = True):
    now = datetime.now().isoformat()
    with db_session(commit=True) as (_, cursor):
        if increment_count:
            cursor.execute("""
                UPDATE games
                SET play_count = play_count + 1,
                    played_seconds = played_seconds + ?,
                    last_played_at = ?,
                    first_played_at = COALESCE(first_played_at, ?),
                    play_status = CASE WHEN play_status = 'unplayed' THEN 'playing' ELSE play_status END,
                    updated_at = ?
                WHERE id = ?
            """, (duration_seconds, now, now, now, game_id))
        else:
            cursor.execute("""
                UPDATE games
                SET played_seconds = played_seconds + ?,
                    last_played_at = ?,
                    updated_at = ?
                WHERE id = ?
            """, (duration_seconds, now, now, game_id))


def get_stats() -> Dict[str, Any]:
    with db_session(commit=False) as (_, cursor):
        cursor.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN play_status = 'unplayed' THEN 1 ELSE 0 END) as unplayed,
                SUM(CASE WHEN play_status = 'playing' THEN 1 ELSE 0 END) as playing,
                SUM(CASE WHEN play_status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN play_status = 'dropped' THEN 1 ELSE 0 END) as dropped,
                SUM(CASE WHEN play_status = 'backlog' THEN 1 ELSE 0 END) as backlog,
                SUM(CASE WHEN is_favorite = 1 THEN 1 ELSE 0 END) as favorites,
                SUM(CASE WHEN duplicate_count > 0 THEN 1 ELSE 0 END) as duplicates,
                SUM(CASE WHEN is_missing = 1 THEN 1 ELSE 0 END) as missing,
                SUM(CASE WHEN {HAS_NOTES_SQL_COND} THEN 1 ELSE 0 END) as has_notes,
                SUM(CASE WHEN {TRANSLATED_SQL_COND} THEN 1 ELSE 0 END) as translated,
                SUM(CASE WHEN cover_url IS NULL OR TRIM(cover_url) = '' OR synopsis IS NULL OR TRIM(synopsis) = '' THEN 1 ELSE 0 END) as unscraped,
                SUM(played_seconds) as total_seconds,
                SUM(folder_size_bytes) as total_size_bytes,
                SUM(COALESCE(screenshot_count, 0)) as total_screenshots,
                SUM(CASE WHEN COALESCE(cg_unlocked, 0) = 1 THEN 1 ELSE 0 END) as cg_unlocked_count
            FROM games
            WHERE is_archived = 0 AND is_tool = 0
        """)
        row = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) as tools_count FROM games WHERE is_archived = 0 AND is_tool = 1")
        tools_row = cursor.fetchone()

    total_bytes = (row["total_size_bytes"] or 0) if row else 0
    return {
        "total": (row["total"] or 0) if row else 0,
        "unplayed": (row["unplayed"] or 0) if row else 0,
        "playing": (row["playing"] or 0) if row else 0,
        "completed": (row["completed"] or 0) if row else 0,
        "dropped": (row["dropped"] or 0) if row else 0,
        "backlog": (row["backlog"] or 0) if row else 0,
        "favorites": (row["favorites"] or 0) if row else 0,
        "duplicates": (row["duplicates"] or 0) if row else 0,
        "missing": (row["missing"] or 0) if row else 0,
        "has_notes": (row["has_notes"] or 0) if row else 0,
        "translated": (row["translated"] or 0) if row else 0,
        "unscraped": (row["unscraped"] or 0) if row else 0,
        "tools_count": (tools_row["tools_count"] or 0) if tools_row else 0,
        "total_size_bytes": total_bytes,
        "total_size_str": format_bytes_short(total_bytes),
        "total_played_hours": round(((row["total_seconds"] or 0) if row else 0) / 3600, 1),
        "total_screenshots": (row["total_screenshots"] or 0) if row else 0,
        "cg_unlocked_count": (row["cg_unlocked_count"] or 0) if row else 0
    }


def get_analytics_data() -> Dict[str, Any]:
    """Computes rich multi-dimensional analytics, rankings, heatmaps, and timeline events."""
    games = get_all_games(status="all", is_tool=False, include_full_notes=False)
    stats = get_stats()
    total_games = max(1, len(games))
    total_bytes = max(1, stats.get("total_size_bytes") or 1)

    # 1. Play time distribution buckets
    buckets = [
        {"key": "zero", "label": "未开封 (0m)", "count": 0, "color": "#64748b"},
        {"key": "under_1h", "label": "初体验 (<1h)", "count": 0, "color": "#38bdf8"},
        {"key": "1_to_5h", "label": "深入游玩 (1-5h)", "count": 0, "color": "#6366f1"},
        {"key": "5_to_20h", "label": "核心沉迷 (5-20h)", "count": 0, "color": "#a855f7"},
        {"key": "over_20h", "label": "殿堂真爱 (>20h)", "count": 0, "color": "#ec4899"},
    ]
    for g in games:
        sec = int(g.get("played_seconds") or 0)
        if sec < 60:
            buckets[0]["count"] += 1
        elif sec < 3600:
            buckets[1]["count"] += 1
        elif sec < 18000:
            buckets[2]["count"] += 1
        elif sec < 72000:
            buckets[3]["count"] += 1
        else:
            buckets[4]["count"] += 1
    for b in buckets:
        b["percentage"] = round((b["count"] / total_games) * 100, 1)

    # 2. Top played games
    played_sorted = sorted(
        [g for g in games if (g.get("played_seconds") or 0) > 0 or (g.get("play_count") or 0) > 0],
        key=lambda x: (x.get("played_seconds") or 0, x.get("play_count") or 0),
        reverse=True
    )[:10]
    max_played_sec = max([g.get("played_seconds") or 1 for g in played_sorted], default=1)
    top_played = [{
        "id": g["id"],
        "display_title": g.get("display_title") or g.get("folder_name"),
        "circle_name": g.get("circle_name") or "",
        "cover_url": g.get("cover_url") or "",
        "played_seconds": g.get("played_seconds") or 0,
        "played_hours": round((g.get("played_seconds") or 0) / 3600, 1),
        "play_count": g.get("play_count") or 0,
        "bar_pct": round(((g.get("played_seconds") or 0) / max_played_sec) * 100, 1)
    } for g in played_sorted]

    # 3. Circle & Voice Actor & Tag Rankings
    circle_map: Dict[str, Dict[str, Any]] = {}
    va_map: Dict[str, Dict[str, Any]] = {}
    tag_map: Dict[str, Dict[str, Any]] = {}
    engine_map: Dict[str, Dict[str, Any]] = {}

    for g in games:
        sec = int(g.get("played_seconds") or 0)
        rating = int(g.get("user_rating") or 0)
        is_trs = int(g.get("is_translated") or 0)
        fsize = int(g.get("folder_size_bytes") or 0)

        cir = (g.get("circle_name") or "").strip()
        if cir:
            if cir not in circle_map:
                circle_map[cir] = {"name": cir, "count": 0, "played_seconds": 0, "ratings": [], "translated_count": 0}
            circle_map[cir]["count"] += 1
            circle_map[cir]["played_seconds"] += sec
            circle_map[cir]["translated_count"] += is_trs
            if rating > 0:
                circle_map[cir]["ratings"].append(rating)

        for va in (g.get("voice_actors") or []):
            va_clean = str(va).strip()
            if va_clean:
                if va_clean not in va_map:
                    va_map[va_clean] = {"name": va_clean, "count": 0, "played_seconds": 0}
                va_map[va_clean]["count"] += 1
                va_map[va_clean]["played_seconds"] += sec

        seen_tags = set()
        for t in (g.get("user_tags") or []):
            tc = str(t).strip()
            if tc and tc not in seen_tags:
                seen_tags.add(tc)
                if tc not in tag_map:
                    tag_map[tc] = {"name": tc, "count": 0, "is_user_tag": True}
                tag_map[tc]["count"] += 1

        for t in (g.get("tags") or []):
            tc = str(t).strip()
            if tc and tc not in seen_tags:
                seen_tags.add(tc)
                if tc not in tag_map:
                    tag_map[tc] = {"name": tc, "count": 0, "is_user_tag": False}
                tag_map[tc]["count"] += 1

        eng = (g.get("engine_type") or "Unknown").strip()
        if eng not in engine_map:
            engine_map[eng] = {"engine": eng, "count": 0, "size_bytes": 0, "translated_count": 0}
        engine_map[eng]["count"] += 1
        engine_map[eng]["size_bytes"] += fsize
        engine_map[eng]["translated_count"] += is_trs

    top_circles = sorted(circle_map.values(), key=lambda x: (x["count"], x["played_seconds"]), reverse=True)[:12]
    max_cir_cnt = max([c["count"] for c in top_circles], default=1)
    for c in top_circles:
        c["played_hours"] = round(c["played_seconds"] / 3600, 1)
        c["avg_rating"] = round(sum(c["ratings"]) / len(c["ratings"]), 1) if c["ratings"] else 0.0
        c["bar_pct"] = round((c["count"] / max_cir_cnt) * 100, 1)
        c.pop("ratings", None)

    top_vas = sorted(va_map.values(), key=lambda x: (x["count"], x["played_seconds"]), reverse=True)[:12]
    max_va_cnt = max([v["count"] for v in top_vas], default=1)
    for v in top_vas:
        v["played_hours"] = round(v["played_seconds"] / 3600, 1)
        v["bar_pct"] = round((v["count"] / max_va_cnt) * 100, 1)

    top_tags = sorted(tag_map.values(), key=lambda x: (x["is_user_tag"], x["count"]), reverse=True)[:28]

    engine_breakdown = sorted(engine_map.values(), key=lambda x: x["count"], reverse=True)
    for e in engine_breakdown:
        e["percentage"] = round((e["count"] / total_games) * 100, 1)
        e["size_str"] = format_bytes_short(e["size_bytes"])
        e["translated_pct"] = round((e["translated_count"] / max(1, e["count"])) * 100, 0)

    # 4. Monthly Heatmap / Trend (last 12 months + active months)
    month_counts: Dict[str, Dict[str, int]] = {}
    now_dt = datetime.now()
    for i in range(11, -1, -1):
        dt = (now_dt.replace(day=1) - timedelta(days=i * 28)).replace(day=1)
        m_key = dt.strftime("%Y-%m")
        month_counts[m_key] = {"month": m_key, "added_count": 0, "played_count": 0}

    for g in games:
        dl_at = (g.get("downloaded_at") or g.get("created_at") or "")[:7]
        if len(dl_at) == 7 and dl_at[4] == "-":
            if dl_at not in month_counts:
                month_counts[dl_at] = {"month": dl_at, "added_count": 0, "played_count": 0}
            month_counts[dl_at]["added_count"] += 1
        lp_at = (g.get("last_played_at") or "")[:7]
        if len(lp_at) == 7 and lp_at[4] == "-":
            if lp_at not in month_counts:
                month_counts[lp_at] = {"month": lp_at, "added_count": 0, "played_count": 0}
            month_counts[lp_at]["played_count"] += 1

    monthly_activity = [month_counts[k] for k in sorted(month_counts.keys())[-12:]]
    max_month_val = max([max(m["added_count"], m["played_count"]) for m in monthly_activity], default=1) or 1
    for m in monthly_activity:
        m["added_pct"] = round((m["added_count"] / max_month_val) * 100, 1)
        m["played_pct"] = round((m["played_count"] / max_month_val) * 100, 1)

    # 5. Storage Space Ranking Top 10
    size_sorted = sorted(games, key=lambda x: x.get("folder_size_bytes") or 0, reverse=True)[:10]
    max_game_bytes = max([g.get("folder_size_bytes") or 1 for g in size_sorted], default=1)
    storage_ranking = [{
        "id": g["id"],
        "display_title": g.get("display_title") or g.get("folder_name"),
        "folder_name": g.get("folder_name"),
        "engine_type": g.get("engine_type") or "Unknown",
        "folder_size_bytes": g.get("folder_size_bytes") or 0,
        "folder_size_str": g.get("folder_size_str") or "0 MB",
        "share_pct": round(((g.get("folder_size_bytes") or 0) / total_bytes) * 100, 1),
        "bar_pct": round(((g.get("folder_size_bytes") or 0) / max_game_bytes) * 100, 1),
        "cover_url": g.get("cover_url") or ""
    } for g in size_sorted]

    # 6. Recent Activity Timeline
    timeline = []
    for g in games:
        title = g.get("display_title") or g.get("folder_name")
        if g.get("last_played_at"):
            timeline.append({
                "type": "played",
                "game_id": g["id"],
                "title": title,
                "cover_url": g.get("cover_url") or "",
                "timestamp": g["last_played_at"][:16].replace("T", " "),
                "detail": f"游玩状态: {g.get('play_status')} · 累计 {round((g.get('played_seconds') or 0)/3600, 1)}h"
            })
        if g.get("has_notes") and g.get("updated_at"):
            timeline.append({
                "type": "guide",
                "game_id": g["id"],
                "title": title,
                "cover_url": g.get("cover_url") or "",
                "timestamp": g["updated_at"][:16].replace("T", " "),
                "detail": f"收录通关攻略 ({g.get('notes_length', 0)} 字符)"
            })
        dl_time = g.get("downloaded_at") or g.get("created_at")
        if dl_time:
            timeline.append({
                "type": "added",
                "game_id": g["id"],
                "title": title,
                "cover_url": g.get("cover_url") or "",
                "timestamp": dl_time[:16].replace("T", " "),
                "detail": f"入库归档 · {g.get('engine_type') or 'PC'} · {g.get('folder_size_str')}"
            })

    timeline.sort(key=lambda x: x["timestamp"], reverse=True)

    return {
        "overview": {
            "total": stats["total"],
            "total_size_str": stats["total_size_str"],
            "total_played_hours": stats["total_played_hours"],
            "completed": stats["completed"],
            "completion_rate": round((stats["completed"] / total_games) * 100, 1),
            "translated": stats["translated"],
            "translation_rate": round((stats["translated"] / total_games) * 100, 1),
            "has_notes": stats["has_notes"],
            "notes_rate": round((stats["has_notes"] / total_games) * 100, 1),
            "favorites": stats["favorites"],
            "total_screenshots": stats["total_screenshots"],
            "cg_unlocked_count": stats["cg_unlocked_count"]
        },
        "play_time_buckets": buckets,
        "top_played_games": top_played,
        "top_circles": top_circles,
        "top_voice_actors": top_vas,
        "top_tags": top_tags,
        "engine_breakdown": engine_breakdown,
        "monthly_activity": monthly_activity,
        "storage_ranking": storage_ranking,
        "timeline": timeline[:24]
    }


# ---------------------------------------------------------
# Game Screenshots CRUD
# ---------------------------------------------------------
def add_game_screenshot(
    game_id: int,
    filename: str,
    caption: str = "",
    width: int = 0,
    height: int = 0,
    size_bytes: int = 0
) -> Dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session(commit=True) as (_, cursor):
        cursor.execute("""
            INSERT INTO game_screenshots (game_id, filename, caption, width, height, size_bytes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (game_id, filename, caption, width, height, size_bytes, now))
        shot_id = cursor.lastrowid
        cursor.execute("""
            UPDATE games
            SET screenshot_count = (SELECT COUNT(*) FROM game_screenshots WHERE game_id = ?),
                updated_at = ?
            WHERE id = ?
        """, (game_id, datetime.now().isoformat(), game_id))
    return {
        "id": shot_id,
        "game_id": game_id,
        "filename": filename,
        "url": f"/api/gallery/{game_id}/{filename}",
        "caption": caption,
        "width": width,
        "height": height,
        "size_kb": round(size_bytes / 1024, 1),
        "created_at": now
    }


def get_game_screenshots(game_id: int) -> List[Dict[str, Any]]:
    with db_session(commit=False) as (_, cursor):
        cursor.execute("""
            SELECT * FROM game_screenshots
            WHERE game_id = ?
            ORDER BY id DESC
        """, (game_id,))
        rows = cursor.fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["url"] = f"/api/gallery/{game_id}/{d['filename']}"
            d["size_kb"] = round((d.get("size_bytes") or 0) / 1024, 1)
            res.append(d)
        return res


def update_screenshot_caption(shot_id: int, game_id: int, caption: str) -> bool:
    with db_session(commit=True) as (_, cursor):
        cursor.execute(
            "UPDATE game_screenshots SET caption = ? WHERE id = ? AND game_id = ?",
            (caption, shot_id, game_id)
        )
        return cursor.rowcount > 0


def delete_game_screenshot(shot_id: int, game_id: int) -> Optional[str]:
    with db_session(commit=True) as (_, cursor):
        cursor.execute("SELECT filename FROM game_screenshots WHERE id = ? AND game_id = ?", (shot_id, game_id))
        row = cursor.fetchone()
        if not row:
            return None
        fname = row["filename"]
        cursor.execute("DELETE FROM game_screenshots WHERE id = ? AND game_id = ?", (shot_id, game_id))
        cursor.execute("""
            UPDATE games
            SET screenshot_count = (SELECT COUNT(*) FROM game_screenshots WHERE game_id = ?),
                updated_at = ?
            WHERE id = ?
        """, (game_id, datetime.now().isoformat(), game_id))
        return fname


def get_scrape_cache(query_key: str, source: Optional[str] = None, max_age_days: int = 14) -> Optional[Dict[str, Any]]:
    if not query_key:
        return None
    norm_key = f"{source or 'any'}:{query_key.strip().lower()}"
    with db_session(commit=False) as (_, cursor):
        cursor.execute("SELECT data_json, updated_at FROM scrape_cache WHERE query_key = ?", (norm_key,))
        row = cursor.fetchone()
        if not row or not row["data_json"]:
            return None
        try:
            if row["updated_at"]:
                dt = datetime.fromisoformat(row["updated_at"])
                if datetime.now() - dt > timedelta(days=max_age_days):
                    return None
            return json.loads(row["data_json"])
        except Exception:
            return None


def set_scrape_cache(query_key: str, source: str, data: Dict[str, Any]):
    if not query_key or not data:
        return
    norm_key = f"{source or 'any'}:{query_key.strip().lower()}"
    now = datetime.now().isoformat()
    try:
        with db_session(commit=True) as (_, cursor):
            cursor.execute("""
                INSERT INTO scrape_cache (query_key, source, data_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(query_key) DO UPDATE SET
                    source = excluded.source,
                    data_json = excluded.data_json,
                    updated_at = excluded.updated_at
            """, (norm_key, source, json.dumps(data, ensure_ascii=False), now))
    except Exception:
        pass


def batch_update_duplicates(dup_updates: List[Tuple[Optional[str], int, int]]):
    if not dup_updates:
        return
    now = datetime.now().isoformat()
    with db_session(commit=True) as (_, cursor):
        cursor.executemany(
            "UPDATE games SET duplicate_group_id = ?, duplicate_count = ?, updated_at = ? WHERE id = ?",
            [(gid, cnt, now, gid_val) for gid, cnt, gid_val in dup_updates]
        )


def get_duplicate_groups() -> Dict[str, List[Dict[str, Any]]]:
    with db_session(commit=False) as (_, cursor):
        cursor.execute(f"""
            SELECT {LIGHTWEIGHT_GAME_COLUMNS} FROM games
            WHERE is_archived = 0 AND is_tool = 0 AND duplicate_group_id IS NOT NULL AND duplicate_count > 0
            ORDER BY duplicate_group_id ASC, folder_modified_at DESC
        """)
        rows = cursor.fetchall()

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        d = row_to_dict(r)
        gid = d["duplicate_group_id"]
        if gid not in groups:
            groups[gid] = []
        groups[gid].append(d)
    return {k: v for k, v in groups.items() if len(v) > 1}


def add_duplicate_ignore(id1: int, id2: int):
    if id1 == id2:
        return
    g1, g2 = min(id1, id2), max(id1, id2)
    with db_session(commit=True) as (_, cursor):
        cursor.execute("""
            INSERT OR IGNORE INTO duplicate_ignores (game_id_1, game_id_2, created_at)
            VALUES (?, ?, ?)
        """, (g1, g2, datetime.now().isoformat()))


def get_all_duplicate_ignores() -> set:
    with db_session(commit=False) as (_, cursor):
        cursor.execute("SELECT game_id_1, game_id_2 FROM duplicate_ignores")
        rows = cursor.fetchall()
        return {(r["game_id_1"], r["game_id_2"]) for r in rows}


def dismiss_game_from_duplicates(game_id: int, target_id: Optional[int] = None) -> bool:
    if target_id and target_id != game_id:
        add_duplicate_ignore(game_id, target_id)
        return True

    with db_session(commit=False) as (_, cursor):
        cursor.execute("SELECT duplicate_group_id FROM games WHERE id = ?", (game_id,))
        row = cursor.fetchone()
        if row and row["duplicate_group_id"]:
            gid = row["duplicate_group_id"]
            cursor.execute("SELECT id FROM games WHERE duplicate_group_id = ? AND id != ?", (gid, game_id))
            other_games = [og["id"] for og in cursor.fetchall()]
        else:
            other_games = []

    for oid in other_games:
        add_duplicate_ignore(game_id, oid)
    return True


def mark_archived(game_id: int):
    with db_session(commit=True) as (_, cursor):
        cursor.execute("UPDATE games SET is_archived = 1, updated_at = ? WHERE id = ?", (datetime.now().isoformat(), game_id))


def delete_game_by_id(game_id: int) -> bool:
    with db_session(commit=True) as (_, cursor):
        cursor.execute("DELETE FROM game_screenshots WHERE game_id = ?", (game_id,))
        cursor.execute("DELETE FROM games WHERE id = ?", (game_id,))
        return cursor.rowcount > 0


def mark_game_missing(game_id: int, is_missing: int = 1):
    with db_session(commit=True) as (_, cursor):
        cursor.execute("UPDATE games SET is_missing = ?, updated_at = ? WHERE id = ?", (is_missing, datetime.now().isoformat(), game_id))


def get_all_stored_game_paths() -> List[Tuple[int, str, int]]:
    with db_session(commit=False) as (_, cursor):
        cursor.execute("SELECT id, folder_path, is_missing FROM games WHERE is_archived = 0")
        rows = cursor.fetchall()
        return [(r["id"], r["folder_path"], r["is_missing"]) for r in rows]


def set_games_missing_batch(missing_ids: List[int], existing_ids: List[int]):
    if not missing_ids and not existing_ids:
        return
    now = datetime.now().isoformat()
    with db_session(commit=True) as (_, cursor):
        if missing_ids:
            cursor.execute(f"UPDATE games SET is_missing = 1, updated_at = ? WHERE id IN ({','.join(['?']*len(missing_ids))})", [now] + missing_ids)
        if existing_ids:
            cursor.execute(f"UPDATE games SET is_missing = 0, updated_at = ? WHERE id IN ({','.join(['?']*len(existing_ids))})", [now] + existing_ids)


def cleanup_all_missing_games() -> int:
    with db_session(commit=True) as (_, cursor):
        cursor.execute("DELETE FROM games WHERE is_missing = 1 AND is_archived = 0")
        return cursor.rowcount


def batch_update_games_status(game_ids: List[int], play_status: str) -> int:
    if not game_ids:
        return 0
    now = datetime.now().isoformat()
    with db_session(commit=True) as (_, cursor):
        cursor.execute(
            f"UPDATE games SET play_status = ?, updated_at = ? WHERE id IN ({','.join(['?']*len(game_ids))})",
            [play_status, now] + game_ids
        )
        return cursor.rowcount


def batch_delete_games_by_ids(game_ids: List[int]) -> int:
    if not game_ids:
        return 0
    with db_session(commit=True) as (_, cursor):
        cursor.execute(
            f"DELETE FROM game_screenshots WHERE game_id IN ({','.join(['?']*len(game_ids))})",
            game_ids
        )
        cursor.execute(
            f"DELETE FROM games WHERE id IN ({','.join(['?']*len(game_ids))})",
            game_ids
        )
        return cursor.rowcount
