import sqlite3
import json
import os
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from config import DB_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
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
        
        created_at TEXT,
        updated_at TEXT
    );
    """)
    
    # Auto-migration for downloaded_at, has_translation & is_missing columns if database was created earlier
    try:
        cursor.execute("ALTER TABLE games ADD COLUMN downloaded_at TEXT;")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE games ADD COLUMN has_translation INTEGER DEFAULT 0;")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE games ADD COLUMN is_missing INTEGER DEFAULT 0;")
    except Exception:
        pass

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_folder_path ON games(folder_path);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_play_status ON games(play_status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rj_code ON games(rj_code);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_clean_title ON games(clean_title);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_duplicate_group ON games(duplicate_group_id);")

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
    conn.commit()
    conn.close()

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
    return d

def get_all_games(
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    favorite_only: bool = False,
    duplicates_only: bool = False,
    missing_only: bool = False,
    is_tool: bool = False,
    has_notes_only: bool = False,
    sort_by: str = "title",
    sort_order: str = "asc"
) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM games WHERE is_archived = 0 AND is_tool = ?"
    params: List[Any] = [1 if is_tool else 0]

    if status and status != "all":
        query += " AND play_status = ?"
        params.append(status)

    if favorite_only:
        query += " AND is_favorite = 1"

    if duplicates_only:
        query += " AND duplicate_count > 0"

    if missing_only:
        query += " AND is_missing = 1"

    if has_notes_only:
        query += " AND user_notes IS NOT NULL AND TRIM(user_notes) != ''"

    if keyword:
        k = f"%{keyword}%"
        query += " AND (folder_name LIKE ? OR clean_title LIKE ? OR display_title LIKE ? OR original_title LIKE ? OR circle_name LIKE ? OR rj_code LIKE ? OR tags LIKE ? OR user_tags LIKE ? OR voice_actors LIKE ?)"
        params.extend([k, k, k, k, k, k, k, k, k])

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
        query += f" ORDER BY {col} IS NULL, {col} {order}, display_title ASC"
    else:
        query += f" ORDER BY {col} {order}"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

def get_game_by_id(game_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM games WHERE id = ?", (game_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row) if row else None

def get_game_by_path(folder_path: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM games WHERE folder_path = ?", (folder_path,))
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row) if row else None

def upsert_game(game_data: Dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    existing = get_game_by_path(game_data["folder_path"])
    
    tags_str = json.dumps(game_data.get("tags", []), ensure_ascii=False) if isinstance(game_data.get("tags"), list) else game_data.get("tags", "[]")
    user_tags_str = json.dumps(game_data.get("user_tags", []), ensure_ascii=False) if isinstance(game_data.get("user_tags"), list) else game_data.get("user_tags", "[]")
    va_str = json.dumps(game_data.get("voice_actors", []), ensure_ascii=False) if isinstance(game_data.get("voice_actors"), list) else game_data.get("voice_actors", "[]")

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
            game_data.get("folder_size_bytes", 0),
            game_data.get("folder_size_str", ""),
            game_data.get("folder_modified_at", ""),
            now,
            game_data.get("is_tool", 0)
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

    conn.commit()
    conn.close()
    return game_id

def batch_upsert_games(games_list: List[Dict[str, Any]]):
    """Performs fast transaction batch upsert for scanned games."""
    if not games_list:
        return
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    cursor.execute("SELECT id, folder_path, clean_title, engine_type, executable_path, downloaded_at FROM games")
    existing_map = {row["folder_path"]: dict(row) for row in cursor.fetchall()}

    for g in games_list:
        fpath = g["folder_path"]
        tags_str = json.dumps(g.get("tags", []), ensure_ascii=False)
        va_str = json.dumps(g.get("voice_actors", []), ensure_ascii=False)
        
        if fpath in existing_map:
            gid = existing_map[fpath]["id"]
            cursor.execute("""
                UPDATE games SET
                    folder_name = ?,
                    clean_title = COALESCE(NULLIF(clean_title, ''), ?),
                    engine_type = ?,
                    executable_path = ?,
                    folder_size_bytes = ?,
                    folder_size_str = ?,
                    folder_modified_at = ?,
                    downloaded_at = COALESCE(NULLIF(?, ''), downloaded_at),
                    is_tool = ?,
                    rj_code = CASE WHEN (rj_code IS NULL OR rj_code = '') AND ? != '' THEN ? ELSE rj_code END,
                    updated_at = ?
                WHERE id = ?
            """, (
                g["folder_name"], g.get("clean_title"), g.get("engine_type"), g.get("executable_path"),
                g.get("folder_size_bytes", 0), g.get("folder_size_str", ""), g.get("folder_modified_at", ""),
                g.get("downloaded_at", ""), g.get("is_tool", 0), g.get("rj_code", ""), g.get("rj_code", ""), now, gid
            ))
        else:
            fields = [
                "folder_name", "folder_path", "clean_title", "display_title", "original_title",
                "rj_code", "engine_type", "executable_path", "folder_size_bytes", "folder_size_str",
                "folder_modified_at", "downloaded_at", "cover_url", "banner_url", "synopsis", "circle_name",
                "release_date", "voice_actors", "tags", "source_url", "source_type", "rating_score",
                "play_status", "user_rating", "user_notes", "user_tags", "is_favorite",
                "is_tool", "created_at", "updated_at"
            ]
            cursor.execute(f"INSERT INTO games ({', '.join(fields)}) VALUES ({', '.join(['?']*len(fields))})", (
                g["folder_name"], g["folder_path"], g.get("clean_title", g["folder_name"]),
                g.get("display_title", g.get("clean_title", g["folder_name"])), "",
                g.get("rj_code", ""), g.get("engine_type", "Unknown"), g.get("executable_path", ""),
                g.get("folder_size_bytes", 0), g.get("folder_size_str", "0 MB"), g.get("folder_modified_at", ""),
                g.get("downloaded_at", ""), "", "", "", "", "", va_str, tags_str, "", "none", 0.0,
                "unplayed", 0, "", "[]", 0, g.get("is_tool", 0), now, now
            ))

    conn.commit()
    conn.close()

def manual_update_game_metadata(game_id: int, data: Dict[str, Any]) -> bool:
    """Allows full manual customization/modification of game metadata."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    fields = ["updated_at = ?"]
    values = [now]

    allowed_fields = [
        "display_title", "original_title", "circle_name", "release_date",
        "downloaded_at", "cover_url", "banner_url", "synopsis", "rj_code", "source_type"
    ]

    for key in allowed_fields:
        if key in data and data[key] is not None:
            fields.append(f"{key} = ?")
            values.append(data[key])

    if "tags" in data and data["tags"] is not None:
        fields.append("tags = ?")
        tags_val = json.dumps(data["tags"], ensure_ascii=False) if isinstance(data["tags"], list) else str(data["tags"])
        values.append(tags_val)

    if "voice_actors" in data and data["voice_actors"] is not None:
        fields.append("voice_actors = ?")
        va_val = json.dumps(data["voice_actors"], ensure_ascii=False) if isinstance(data["voice_actors"], list) else str(data["voice_actors"])
        values.append(va_val)

    values.append(game_id)
    cursor.execute(f"UPDATE games SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
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
    conn = get_connection()
    cursor = conn.cursor()
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
    cursor.execute(f"UPDATE games SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True

def record_game_launch(game_id: int, duration_seconds: int = 0):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
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
    conn.commit()
    conn.close()

def get_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
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
            SUM(CASE WHEN user_notes IS NOT NULL AND TRIM(user_notes) != '' THEN 1 ELSE 0 END) as has_notes,
            SUM(played_seconds) as total_seconds
        FROM games 
        WHERE is_archived = 0 AND is_tool = 0
    """)
    row = cursor.fetchone()
    conn.close()
    return {
        "total": row["total"] or 0,
        "unplayed": row["unplayed"] or 0,
        "playing": row["playing"] or 0,
        "completed": row["completed"] or 0,
        "dropped": row["dropped"] or 0,
        "backlog": row["backlog"] or 0,
        "favorites": row["favorites"] or 0,
        "duplicates": row["duplicates"] or 0,
        "missing": row["missing"] or 0,
        "has_notes": row["has_notes"] or 0,
        "total_played_hours": round((row["total_seconds"] or 0) / 3600, 1)
    }

def batch_update_duplicates(dup_updates: List[Tuple[Optional[str], int, int]]):
    if not dup_updates:
        return
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.executemany(
        "UPDATE games SET duplicate_group_id = ?, duplicate_count = ?, updated_at = ? WHERE id = ?",
        [(gid, cnt, now, gid_val) for gid, cnt, gid_val in dup_updates]
    )
    conn.commit()
    conn.close()

def get_duplicate_groups() -> Dict[str, List[Dict[str, Any]]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM games 
        WHERE is_archived = 0 AND is_tool = 0 AND duplicate_group_id IS NOT NULL AND duplicate_count > 0
        ORDER BY duplicate_group_id ASC, folder_modified_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS duplicate_ignores (
            game_id_1 INTEGER NOT NULL,
            game_id_2 INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (game_id_1, game_id_2)
        );
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO duplicate_ignores (game_id_1, game_id_2, created_at)
        VALUES (?, ?, ?)
    """, (g1, g2, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_all_duplicate_ignores() -> set:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS duplicate_ignores (
            game_id_1 INTEGER NOT NULL,
            game_id_2 INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (game_id_1, game_id_2)
        );
    """)
    cursor.execute("SELECT game_id_1, game_id_2 FROM duplicate_ignores")
    rows = cursor.fetchall()
    conn.close()
    return {(r["game_id_1"], r["game_id_2"]) for r in rows}

def dismiss_game_from_duplicates(game_id: int, target_id: Optional[int] = None) -> bool:
    """
    Unlinks a game from duplicates.
    If target_id is provided, marks (game_id, target_id) as ignored.
    If target_id is None, marks game_id as ignored against all other games in its current duplicate group.
    """
    conn = get_connection()
    cursor = conn.cursor()
    if target_id and target_id != game_id:
        add_duplicate_ignore(game_id, target_id)
    else:
        cursor.execute("SELECT duplicate_group_id FROM games WHERE id = ?", (game_id,))
        row = cursor.fetchone()
        if row and row["duplicate_group_id"]:
            gid = row["duplicate_group_id"]
            cursor.execute("SELECT id FROM games WHERE duplicate_group_id = ? AND id != ?", (gid, game_id))
            other_games = cursor.fetchall()
            for og in other_games:
                add_duplicate_ignore(game_id, og["id"])
    conn.close()
    return True

def mark_archived(game_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE games SET is_archived = 1, updated_at = ? WHERE id = ?", (datetime.now().isoformat(), game_id))
    conn.commit()
    conn.close()

def delete_game_by_id(game_id: int) -> bool:
    """Permanently deletes a single game record from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM games WHERE id = ?", (game_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def mark_game_missing(game_id: int, is_missing: int = 1):
    """Marks a game as missing from local storage."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE games SET is_missing = ?, updated_at = ? WHERE id = ?", (is_missing, datetime.now().isoformat(), game_id))
    conn.commit()
    conn.close()

def get_all_stored_game_paths() -> List[Tuple[int, str, int]]:
    """Returns (id, folder_path, is_missing) for all non-archived games."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, folder_path, is_missing FROM games WHERE is_archived = 0")
    rows = cursor.fetchall()
    conn.close()
    return [(r["id"], r["folder_path"], r["is_missing"]) for r in rows]

def set_games_missing_batch(missing_ids: List[int], existing_ids: List[int]):
    """Batch updates missing status."""
    if not missing_ids and not existing_ids:
        return
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    if missing_ids:
        cursor.execute(f"UPDATE games SET is_missing = 1, updated_at = ? WHERE id IN ({','.join(['?']*len(missing_ids))})", [now] + missing_ids)
    if existing_ids:
        cursor.execute(f"UPDATE games SET is_missing = 0, updated_at = ? WHERE id IN ({','.join(['?']*len(existing_ids))})", [now] + existing_ids)
    conn.commit()
    conn.close()

def cleanup_all_missing_games() -> int:
    """Deletes all games flagged as is_missing = 1 from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM games WHERE is_missing = 1 AND is_archived = 0")
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count

def batch_update_games_status(game_ids: List[int], play_status: str) -> int:
    """Batch updates play_status for a list of games."""
    if not game_ids:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        f"UPDATE games SET play_status = ?, updated_at = ? WHERE id IN ({','.join(['?']*len(game_ids))})",
        [play_status, now] + game_ids
    )
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count

def batch_delete_games_by_ids(game_ids: List[int]) -> int:
    """Batch deletes a list of game records from the database."""
    if not game_ids:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"DELETE FROM games WHERE id IN ({','.join(['?']*len(game_ids))})",
        game_ids
    )
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count

