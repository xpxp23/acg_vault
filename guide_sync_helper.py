import sqlite3
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = r"E:\项目\AiProgram\apps\acg_vault\data\acg_vault.db"
GUIDES_DIR = r"E:\项目\AiProgram\apps\acg_vault\data\guides"
os.makedirs(GUIDES_DIR, exist_ok=True)

def sync_game_guide(game_id: int, clean_title: str, guide_markdown: str):
    # Write files
    safe_title = clean_title.replace(":", "_").replace("/", "_").replace("\\", "_").replace(" ", "_")
    p1 = Path(GUIDES_DIR) / f"{safe_title}_Guide.md"
    p2 = Path(GUIDES_DIR) / f"{safe_title}_全剧情与全结局全攻略.md"
    with open(p1, "w", encoding="utf-8") as f:
        f.write(guide_markdown)
    with open(p2, "w", encoding="utf-8") as f:
        f.write(guide_markdown)
    
    # Update SQLite database
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE games SET user_notes = ? WHERE id = ?", (guide_markdown, game_id))
    conn.commit()
    conn.close()
    print(f"✅ Synced Game [ID {game_id}] {clean_title} ({len(guide_markdown)} chars) -> {p1.name}")

print("Sync helper loaded.")
