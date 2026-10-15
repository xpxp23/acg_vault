import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

db_path = r"E:\项目\AiProgram\apps\acg_vault\data\acg_vault.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

def get_folder_size(p):
    total = 0
    for root, dirs, files in os.walk(p):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except Exception:
                pass
    return total

def format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"

games_to_register = [
    {
        "folder_name": "HousekeepingNTR_CN",
        "folder_path": r"E:\acg\HousekeepingNTR_CN",
        "clean_title": "HousekeepingNTR",
        "display_title": "HousekeepingNTR (家政妇NTR)",
        "original_title": "HousekeepingNTR",
        "rj_code": "",
        "engine_type": "Unity",
        "executable_path": r"E:\acg\HousekeepingNTR_CN\HousekeepingNTR.exe",
        "circle_name": "独立制作",
        "release_date": "2024",
        "tags": "Unity, SLG, NTR, 家政妇, 恋爱养成, 汉化",
        "synopsis": "探索互动型家政妇与多女主互动SLG游戏。玩家扮演男主打扫房间、收集道具、与三位女主角互动交流，推进好感度与堕落度，解锁丰富日常及特殊画廊事件。",
        "has_translation": 1
    },
    {
        "folder_name": "Hとメイドと無人島 ver.1.02",
        "folder_path": r"E:\acg\Hとメイドと無人島 ver.1.02",
        "clean_title": "Hとメイドと無人島",
        "display_title": "Hとメイドと無人島 ver.1.02",
        "original_title": "Hとメイドと無人島",
        "rj_code": "",
        "engine_type": "RPG Maker MZ",
        "executable_path": r"E:\acg\Hとメイドと無人島 ver.1.02\Game.exe",
        "circle_name": "ジャングリーとコンクル",
        "release_date": "2025",
        "tags": "RPG Maker MZ, 孤岛探索, 女仆, 换装, 多结局, 探索ADV",
        "synopsis": "孤岛漂流求生与女仆换装探索ADV。主角与乃亚、尤莉、梨世三位女仆漂流至神秘无人岛，通过修缮设施、寻找关键道具推进主线，解锁丰富的换装及个人与全员脱出结局。",
        "has_translation": 1
    },
    {
        "folder_name": "カルティベーター ～引退騎士とモン娘のにぎやか開拓記～ Ver1.5d",
        "folder_path": r"E:\acg\カルティベーター ～引退騎士とモン娘のにぎやか開拓記～ Ver1.5d",
        "clean_title": "カルティベーター ～引退騎士とモン娘のにぎやか開拓記～",
        "display_title": "カルティベーター ～引退騎士とモン娘のにぎやか開拓記～ Ver1.5d",
        "original_title": "カルティベーター ～引退騎士とモン娘のにぎやか開拓記～",
        "rj_code": "RJ328940",
        "engine_type": "RPG Maker MV",
        "executable_path": r"E:\acg\カルティベーター ～引退騎士とモン娘のにぎやか開拓記～ Ver1.5d\contents\Game.exe",
        "circle_name": "かえでの",
        "release_date": "2026-09-19",
        "tags": "RPG Maker MV, 开拓经营, 魔物娘, 农场种植, 引退骑士, 建造, 角色扮演",
        "synopsis": "引退骑士与魔物娘的荒野拓荒建设RPG。退役骑士在边境未开发领地建立据点，与形形色色的魔物娘同伴邂逅、农耕种植、设施建造、击退魔物威胁，开拓繁华的世外桃源。",
        "has_translation": 0
    },
    {
        "folder_name": "ポンコツ魔法使いセリスVer1.02",
        "folder_path": r"E:\acg\ポンコツ魔法使いセリスVer1.02",
        "clean_title": "ポンコツ魔法使いセリスのHな冒険記",
        "display_title": "ポンコツ魔法使いセリスのHな冒険記 ～Hな呪いで精液を求める身体になった魔法使い～ Ver1.02",
        "original_title": "ポンコツ魔法使いセリスのHな冒険記 ～Hな呪いで精液を求める身体になった魔法使い～",
        "rj_code": "RJ01724124",
        "engine_type": "Wolf RPG",
        "executable_path": r"E:\acg\ポンコツ魔法使いセリスVer1.02\GamePro.exe",
        "circle_name": "桜桃社",
        "release_date": "2026-10-02",
        "tags": "Wolf RPG, 魔法使, 诅咒, 战斗状态异常, 打工, 动态立绘, MTool汉化",
        "synopsis": "废柴天才魔法使赛莉丝在冒险中被诅咒，身体产生了渴求精液的异常特质。在王都与迷宫中一边打工筹款、一边探索解咒之法，包含丰富的状态变化与战斗互动。",
        "has_translation": 1
    },
    {
        "folder_name": "状態異常Ⅲ",
        "folder_path": r"E:\acg\状態異常Ⅲ",
        "clean_title": "状態異常 =Abnormal Condition= ～酩酊/憑依/改変/苗床編～",
        "display_title": "状態異常Ⅲ【妖狐工房汉化】",
        "original_title": "状態異常 =Abnormal Condition= ～酩酊/憑依/改変/苗床編～",
        "rj_code": "RJ01617096",
        "engine_type": "RPG Maker MZ",
        "executable_path": r"E:\acg\状態異常Ⅲ\Game.exe",
        "circle_name": "オクトピグ",
        "release_date": "2026-09-12",
        "tags": "RPG Maker MZ, 状态异常, 射击战, 汉化, 寄生, 苗床, 凭依, 催眠",
        "synopsis": "社团オクトピグ人气系列《状態異常》第三弹终章，由女主角一之濑雫展开的奇妙状态异常冒险。融合了即时射击动作与丰富的异常状态、寄生、改写机制。",
        "has_translation": 1
    }
]

now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

for g in games_to_register:
    folder_path = g["folder_path"]
    folder_size = get_folder_size(folder_path)
    size_str = format_size(folder_size)
    mtime = os.path.getmtime(folder_path) if os.path.exists(folder_path) else 0
    mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime > 0 else now_str

    cur.execute("SELECT id FROM games WHERE folder_name = ? OR folder_path = ?", (g["folder_name"], folder_path))
    row = cur.fetchone()
    if row:
        gid = row[0]
        cur.execute("""
            UPDATE games SET
                folder_path = ?,
                clean_title = ?,
                display_title = ?,
                original_title = ?,
                rj_code = ?,
                engine_type = ?,
                executable_path = ?,
                folder_size_bytes = ?,
                folder_size_str = ?,
                folder_modified_at = ?,
                circle_name = ?,
                release_date = ?,
                tags = ?,
                synopsis = ?,
                has_translation = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            folder_path, g["clean_title"], g["display_title"], g["original_title"],
            g["rj_code"], g["engine_type"], g["executable_path"], folder_size,
            size_str, mtime_str, g["circle_name"], g["release_date"], g["tags"],
            g["synopsis"], g["has_translation"], now_str, gid
        ))
        print(f"Updated Game [ID {gid}]: {g['display_title']} ({size_str})")
    else:
        cur.execute("""
            INSERT INTO games (
                folder_name, folder_path, clean_title, display_title, original_title,
                rj_code, engine_type, executable_path, folder_size_bytes, folder_size_str,
                folder_modified_at, circle_name, release_date, tags, synopsis,
                has_translation, play_status, is_favorite, play_count, played_seconds,
                is_archived, is_tool, is_missing, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, 'unplayed', 0, 0, 0,
                0, 0, 0, ?, ?
            )
        """, (
            g["folder_name"], folder_path, g["clean_title"], g["display_title"], g["original_title"],
            g["rj_code"], g["engine_type"], g["executable_path"], folder_size, size_str,
            mtime_str, g["circle_name"], g["release_date"], g["tags"], g["synopsis"],
            g["has_translation"], now_str, now_str
        ))
        gid = cur.lastrowid
        print(f"Inserted Game [ID {gid}]: {g['display_title']} ({size_str})")

conn.commit()
conn.close()
print("All 5 games successfully registered in acg_vault.db!")
