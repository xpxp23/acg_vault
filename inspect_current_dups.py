import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect(r"E:\项目\AiProgram\apps\acg_vault\data\acg_vault.db")
cur = conn.cursor()

cur.execute("""
    SELECT id, folder_name, folder_path, clean_title, display_title, rj_code, engine_type, 
           duplicate_group_id, duplicate_count, cover_url
    FROM games
    WHERE duplicate_group_id IS NOT NULL AND duplicate_group_id != ''
    ORDER BY duplicate_group_id, id
""")
rows = cur.fetchall()

current_group = None
for r in rows:
    gid = r[7]
    if gid != current_group:
        current_group = gid
        print("\n" + "="*70)
        print(f"📁 GROUP: {gid}")
        print("="*70)
    print(f"ID {r[0]}: Folder='{r[1]}' | CleanTitle='{r[3]}' | RJ='{r[5]}' | Path='{r[2]}'")

conn.close()
