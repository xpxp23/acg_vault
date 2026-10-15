#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ACG Vault - Game Guides Synchronizer
Synchronizes full Markdown walkthroughs from data/guides/ into acg_vault.db (games.user_notes).
"""

import os
import sys
import shutil
import sqlite3
import re
import argparse
from datetime import datetime
from pathlib import Path

# Set default console encoding to UTF-8 on Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

CURRENT_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = CURRENT_DIR / "data" / "acg_vault.db"
DEFAULT_GUIDES_DIR = CURRENT_DIR / "data" / "guides"


def backup_database(db_path: Path) -> Path:
    """Create a timestamped backup of the SQLite database."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.bak_{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def load_guide_clusters(guides_dir: Path):
    """
    Load all Markdown guide files and cluster duplicates
    (e.g. English slug vs Chinese detailed filename).
    Returns a dictionary of clusters.
    """
    if not guides_dir.exists():
        raise FileNotFoundError(f"Guides directory not found: {guides_dir}")

    guide_files = [f for f in os.listdir(guides_dir) if f.endswith('.md')]
    clusters = {}

    for gf in sorted(guide_files):
        p = guides_dir / gf
        size = p.stat().st_size
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Match existing cluster by size and text preview
        matched_cluster = None
        for k, v in clusters.items():
            if abs(v['size'] - size) < 50 and (
                v['content'][:200] == content[:200] or v['content'][-200:] == content[-200:]
            ):
                matched_cluster = k
                break

        if matched_cluster:
            clusters[matched_cluster]['files'].append(gf)
            # Prefer Chinese/longer filename as representative cluster name
            if len(gf) > len(matched_cluster) or any('\u4e00' <= c <= '\u9fff' for c in gf):
                # Update preferred file if better
                pass
        else:
            # Extract title line
            first_line = content.split('\n')[0].strip() if content else ''
            clusters[gf] = {
                'files': [gf],
                'size': size,
                'chars': len(content),
                'content': content,
                'title_line': first_line,
                'primary_file': gf
            }

    return clusters


def match_guide_to_game(guide_data, games):
    """
    Match a guide cluster to the best matching game in DB.
    Uses RJ code matching first, then multi-field fuzzy text scoring.
    """
    all_text = " ".join(guide_data['files']) + " " + guide_data['title_line']
    rjs = re.findall(r'RJ\d+', all_text, re.IGNORECASE)

    candidates = []
    for g in games:
        score = 0
        reasons = []
        g_rj = (g['rj_code'] or '').upper()

        # 1. RJ Code Match (High confidence)
        if g_rj and any(g_rj == r.upper() for r in rjs):
            score += 200
            reasons.append(f"RJ匹配({g_rj})")

        # 2. Field Match
        for field in ['clean_title', 'display_title', 'original_title', 'folder_name']:
            val = g[field] or ''
            if not val or len(val) < 2:
                continue
            
            # Exact substring
            if val.lower() in all_text.lower():
                score += 30 + len(val)
                reasons.append(f"{field}完整命中('{val}')")
                continue

            # Sub-chunks
            chunks = [c for c in re.split(r'[\s_~～\-·：:()（）]+', val) if len(c) >= 2]
            for chunk in chunks:
                if chunk.lower() in all_text.lower():
                    score += 5 + len(chunk)
                    reasons.append(f"词段命中('{chunk}')")

        if score > 0:
            candidates.append((score, g, reasons))

    if not candidates:
        return None, 0, []

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_game, best_reasons = candidates[0]
    return best_game, best_score, best_reasons


def sync_guides(db_path: Path, guides_dir: Path, apply_fix: bool = False):
    """Scan and synchronize guides into database."""
    print("=" * 80)
    print(f"ACG Vault 攻略全量同步与排查系统")
    print(f"数据库路径: {db_path}")
    print(f"攻略库目录: {guides_dir}")
    print(f"执行模式: {'【写入修复模式 --apply】' if apply_fix else '【试运行预览模式 --dry-run】'}")
    print("=" * 80)

    if not db_path.exists():
        print(f"❌ 错误: 数据库文件未找到: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT id, folder_name, folder_path, clean_title, display_title, original_title, 
               rj_code, LENGTH(user_notes) as note_len, user_notes 
        FROM games
    """)
    games = [dict(r) for r in c.fetchall()]

    clusters = load_guide_clusters(guides_dir)
    print(f"[*] 发现物理攻略文件 {sum(len(v['files']) for v in clusters.values())} 份，去重合并为 {len(clusters)} 个独立攻略专题。\n")

    incompletes = []
    already_complete = []
    unmatched = []

    for name, data in clusters.items():
        matched_game, score, reasons = match_guide_to_game(data, games)
        if not matched_game:
            unmatched.append((name, data))
            continue

        curr_notes = matched_game['user_notes'] or ''
        curr_len = len(curr_notes)
        full_len = data['chars']
        ratio = (curr_len / full_len) if full_len else 0.0

        item = {
            'cluster_name': name,
            'files': data['files'],
            'content': data['content'],
            'full_len': full_len,
            'game_id': matched_game['id'],
            'game_title': matched_game['display_title'] or matched_game['clean_title'],
            'rj_code': matched_game['rj_code'] or '',
            'curr_len': curr_len,
            'ratio': ratio,
            'reasons': reasons
        }

        # Considered incomplete if ratio < 0.95 or (short placeholder note)
        is_placeholder = (curr_len < 1200 and ('data/guides' in curr_notes or '攻略文件位置' in curr_notes))
        if ratio < 0.95 or is_placeholder:
            incompletes.append(item)
        else:
            already_complete.append(item)

    print(f"--- 1. 已全量对齐的攻略 ({len(already_complete)} 款) ---")
    for item in already_complete:
        print(f"  [✓ 100%] ID {item['game_id']:<3} | {item['game_title'][:30]:<30} | 库内字数: {item['curr_len']:<5} (攻略: {item['full_len']})")

    print(f"\n--- 2. 需补全/修复的残缺攻略 ({len(incompletes)} 款) ---")
    for item in incompletes:
        print(f"  [! 残缺] ID {item['game_id']:<3} | {item['game_title'][:28]:<28} | 当前: {item['curr_len']:<5} -> 全量: {item['full_len']:<5} | 完整度: {item['ratio']:.1%}")

    if unmatched:
        print(f"\n--- 3. 未在数据库中匹配到的攻略 ({len(unmatched)} 款) ---")
        for name, data in unmatched:
            print(f"  [? 未匹配] {name} ({data['chars']} 字符)")

    print("\n" + "=" * 80)

    if not apply_fix:
        print(f"💡 当前为预览模式。检测到 {len(incompletes)} 款游戏存在攻略残缺。")
        print("   若需执行数据库全量同步修复，请添加参数运行: python sync_guides.py --apply")
        conn.close()
        return

    # Apply fix
    if not incompletes:
        print("✨ 所有攻略均已是 100% 全量状态，无需修复。")
        conn.close()
        return

    # Step 1: Backup database
    backup_file = backup_database(db_path)
    print(f"🛡️ 已成功生成数据库安全快照备份: {backup_file.name}")

    # Step 2: Update database records
    updated_count = 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for item in incompletes:
        c.execute("""
            UPDATE games 
            SET user_notes = ?,
                updated_at = ?
            WHERE id = ?
        """, (item['content'], now_str, item['game_id']))
        updated_count += 1
        print(f"  ✅ 成功同步 ID {item['game_id']} 《{item['game_title']}》: 已注入 {item['full_len']} 字符全量 Markdown 攻略")

    conn.commit()
    conn.close()

    print(f"\n🎉 同步修复完成！共修复更新了 {updated_count} 款游戏的完整 Markdown 攻略。")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="ACG Vault Markdown 攻略全量同步工具")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="acg_vault.db 数据库路径")
    parser.add_argument("--guides", type=Path, default=DEFAULT_GUIDES_DIR, help="guides 目录路径")
    parser.add_argument("--apply", action="store_true", help="确认写入数据库（不加此参数时仅预览）")
    args = parser.parse_args()

    sync_guides(args.db, args.guides, apply_fix=args.apply)


if __name__ == "__main__":
    main()
