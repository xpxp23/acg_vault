import sqlite3
import os
import sys
from pathlib import Path
from config import DB_PATH, DATA_DIR

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

GUIDES_DIR = DATA_DIR / "guides"
GUIDES_DIR.mkdir(parents=True, exist_ok=True)

def sync_game_guide(game_id: int, clean_title: str, guide_markdown: str):
    safe_title = clean_title.replace(":", "_").replace("/", "_").replace("\\", "_").replace(" ", "_")
    p1 = GUIDES_DIR / f"{safe_title}_Guide.md"
    p2 = GUIDES_DIR / f"{safe_title}_全剧情与全结局全攻略.md"
    with open(p1, "w", encoding="utf-8") as f:
        f.write(guide_markdown)
    with open(p2, "w", encoding="utf-8") as f:
        f.write(guide_markdown)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE games SET user_notes = ? WHERE id = ?", (guide_markdown, game_id))
    conn.commit()
    conn.close()
    print(f"✅ Synced Game [ID {game_id}] {clean_title} ({len(guide_markdown)} chars) -> {p1.name}")
