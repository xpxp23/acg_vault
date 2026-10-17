# -*- coding: utf-8 -*-
"""
In-Game Screenshot Gallery & 100% Full CG Save Unlocker / Importer for ACG Vault v2.2.
- Captures active game window screenshots via Win32 / PIL ImageGrab when hotkeys (e.g. F12) are pressed
- Manages gallery images, thumbnails, captions, and deletions
- Analyzes and unlocks 100% CG / Recall Gallery for RPG Maker MV/MZ and imports external full-CG save archives
"""

import os
import sys
import re
import io
import json
import time
import shutil
import zipfile
import ctypes
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from config import GALLERY_DIR, load_config
from db.database import (
    get_game_by_id,
    manual_update_game_metadata,
    add_game_screenshot,
    get_game_screenshots,
    update_screenshot_caption,
    delete_game_screenshot
)
from core.scraper import is_valid_image_bytes

IS_WINDOWS = sys.platform == "win32"

try:
    from PIL import Image, ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def get_game_gallery_dir(game_id: int) -> Path:
    d = GALLERY_DIR / f"game_{game_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_image_dimensions(img_bytes: bytes) -> Tuple[int, int]:
    if HAS_PIL:
        try:
            with Image.open(io.BytesIO(img_bytes)) as im:
                return im.width, im.height
        except Exception:
            pass
    return 0, 0


def _find_window_rect_for_pid(target_pid: int) -> Optional[Tuple[int, int, int, int]]:
    """Finds the visible bounding rectangle (left, top, right, bottom) of a process window on Windows."""
    if not IS_WINDOWS or not target_pid:
        return None
    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        dwmapi = getattr(ctypes.windll, "dwmapi", None)

        fg_hwnd = user32.GetForegroundWindow()
        if fg_hwnd:
            fg_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(fg_pid))
            if fg_pid.value == target_pid and user32.IsWindowVisible(fg_hwnd):
                rect = wintypes.RECT()
                if dwmapi:
                    DWMWA_EXTENDED_FRAME_BOUNDS = 9
                    res = dwmapi.DwmGetWindowAttribute(
                        fg_hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
                    )
                    if res == 0 and (rect.right - rect.left) > 100:
                        return (rect.left, rect.top, rect.right, rect.bottom)
                if user32.GetWindowRect(fg_hwnd, ctypes.byref(rect)):
                    if (rect.right - rect.left) > 100 and (rect.bottom - rect.top) > 100:
                        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        pass
    return None


def is_pid_foreground(target_pid: Optional[int], folder_path: Optional[str] = None) -> bool:
    """Checks whether the currently focused foreground window belongs to target_pid or any process in folder_path."""
    if not IS_WINDOWS:
        return False
    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        fg_hwnd = user32.GetForegroundWindow()
        if not fg_hwnd:
            return False
        fg_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(fg_pid))
        if target_pid and fg_pid.value == target_pid:
            return True
        if folder_path and fg_pid.value > 0:
            from core.launcher import get_process_image_path, is_subpath
            img_path = get_process_image_path(fg_pid.value)
            if img_path and is_subpath(img_path, folder_path):
                return True
    except Exception:
        pass
    return False


def capture_game_window_screenshot(game_id: int, pid: Optional[int] = None, caption: str = "") -> Dict[str, Any]:
    """Captures the active game window (or full screen fallback) and saves to the game's gallery."""
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    if not HAS_PIL:
        return {"success": False, "message": "当前 Python 环境未安装 Pillow (PIL)，无法执行屏幕截图，请运行 pip install Pillow"}

    try:
        bbox = _find_window_rect_for_pid(pid) if pid else None
        try:
            img = ImageGrab.grab(bbox=bbox) if bbox else ImageGrab.grab()
        except Exception:
            img = ImageGrab.grab()

        gallery_dir = get_game_gallery_dir(game_id)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        filename = f"shot_{ts_str}.png"
        target_path = gallery_dir / filename

        img.save(target_path, format="PNG", optimize=True)
        size_bytes = target_path.stat().st_size
        auto_caption = caption or f"游戏内截图 ({datetime.now().strftime('%m-%d %H:%M')})"

        shot_record = add_game_screenshot(
            game_id=game_id,
            filename=filename,
            caption=auto_caption,
            width=img.width,
            height=img.height,
            size_bytes=size_bytes
        )
        return {
            "success": True,
            "message": "已成功截取当前画面并归档至游戏画廊！",
            "screenshot": shot_record,
            "screenshots": get_game_screenshots(game_id)
        }
    except Exception as e:
        return {"success": False, "message": f"截图失败: {str(e)}"}


def save_uploaded_screenshot(game_id: int, content: bytes, orig_filename: str = "", caption: str = "") -> Dict[str, Any]:
    """Saves an uploaded or pasted image into the game's screenshot gallery."""
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    if not is_valid_image_bytes(content):
        return {"success": False, "message": "上传的文件不是有效的图片格式"}

    ext = Path(orig_filename).suffix.lower() if orig_filename else ".png"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
        ext = ".png"

    gallery_dir = get_game_gallery_dir(game_id)
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
    filename = f"gallery_{ts_str}{ext}"
    target_path = gallery_dir / filename

    with open(target_path, "wb") as f:
        f.write(content)

    w, h = _get_image_dimensions(content)
    shot_record = add_game_screenshot(
        game_id=game_id,
        filename=filename,
        caption=caption or "",
        width=w,
        height=h,
        size_bytes=len(content)
    )
    return {
        "success": True,
        "message": "图片已添加至游戏专属画廊！",
        "screenshot": shot_record,
        "screenshots": get_game_screenshots(game_id)
    }


def remove_game_screenshot_file(game_id: int, shot_id: int) -> Dict[str, Any]:
    fname = delete_game_screenshot(shot_id, game_id)
    if not fname:
        return {"success": False, "message": "未找到该画廊截图记录"}
    fpath = get_game_gallery_dir(game_id) / Path(fname).name
    if fpath.exists():
        try:
            fpath.unlink()
        except Exception:
            pass
    return {
        "success": True,
        "message": "截图已从画廊移除",
        "screenshots": get_game_screenshots(game_id)
    }


# ---------------------------------------------------------
# 100% Full CG / Recall Gallery Unlocker & Save Importer
# ---------------------------------------------------------
CG_UNLOCKER_PLUGIN_CODE = """//=============================================================================
// acg_vault_cg_unlocker.js
// Non-Destructive One-Click Full CG / Recall Gallery & Cheat Unlocker for MV/MZ
// Press [F8] in-game to unlock all Recall/CG Switches, Common Events & Max Gold
//=============================================================================
/*:
 * @target MZ
 * @plugindesc [v2.2.0] ACG Vault Full CG & Recall Gallery Unlocker (Press F8)
 * @author ACG Vault
 */

(() => {
    'use strict';
    const RECALL_KEYWORDS = /回想|全開|全开|解放|解禁|クリア|ギャラリー|CG|Gallery|Recall|Scene|Ending|ED|シーン|イベント|Hシーン|记忆|画廊/i;

    function unlockRecallSwitches(forceAll) {
        if (typeof $gameSwitches === 'undefined' || !$gameSwitches || typeof $dataSystem === 'undefined' || !$dataSystem) {
            return 0;
        }
        const switches = $dataSystem.switches || [];
        let unlockedCount = 0;
        for (let i = 1; i < switches.length; i++) {
            const name = String(switches[i] || '');
            if (forceAll || (name && RECALL_KEYWORDS.test(name))) {
                $gameSwitches.setValue(i, true);
                unlockedCount++;
            }
        }
        if (typeof $gameParty !== 'undefined' && $gameParty && $gameParty.gainGold) {
            if ($gameParty.gold() < 999999) {
                $gameParty.gainGold(999999);
            }
        }
        if (typeof $gameMap !== 'undefined' && $gameMap && $gameMap.requestRefresh) {
            $gameMap.requestRefresh();
        }
        return unlockedCount;
    }

    // Auto-unlock named recall/gallery switches on map/scene load
    if (typeof Scene_Map !== 'undefined' && Scene_Map.prototype) {
        const _Scene_Map_onMapLoaded = Scene_Map.prototype.onMapLoaded;
        Scene_Map.prototype.onMapLoaded = function() {
            _Scene_Map_onMapLoaded.apply(this, arguments);
            unlockRecallSwitches(false);
        };
    }

    // Hotkey F8: Toggle / Force Unlock All Switches + Max Gold with Visual Toast
    window.addEventListener('keydown', (e) => {
        if (e.key === 'F8') {
            e.preventDefault();
            const forceAll = e.shiftKey;
            const cnt = unlockRecallSwitches(forceAll);
            try {
                if (typeof SoundManager !== 'undefined' && SoundManager.playSave) {
                    SoundManager.playSave();
                }
                const banner = document.createElement('div');
                banner.style.cssText = 'position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:999999;background:rgba(16,185,129,0.94);color:#fff;padding:10px 22px;border-radius:12px;font-family:sans-serif;font-size:14px;font-weight:bold;box-shadow:0 10px 25px rgba(0,0,0,0.6);pointer-events:none;transition:opacity 0.3s;';
                banner.innerText = forceAll
                    ? `✨ [ACG Vault] 已强制开启全部 ${cnt} 个开关并注入 999,999 金币！`
                    : `✨ [ACG Vault] 已激活 ${cnt} 个回想/CG/画廊开关 & 注入 999,999 金币！(按 Shift+F8 可强开全部开关)`;
                document.body.appendChild(banner);
                setTimeout(() => { banner.style.opacity = '0'; setTimeout(() => banner.remove(), 350); }, 2800);
            } catch (err) {}
        }
    });
})();
"""


def _find_rpgmaker_root(folder_path: str) -> Optional[Path]:
    p = Path(folder_path)
    if (p / "data" / "System.json").exists():
        return p
    if (p / "www" / "data" / "System.json").exists():
        return p / "www"
    for sub in p.iterdir() if p.exists() else []:
        if sub.is_dir() and not sub.name.startswith("."):
            if (sub / "data" / "System.json").exists():
                return sub
            if (sub / "www" / "data" / "System.json").exists():
                return sub / "www"
    return None


def unlock_game_all_cg(game_id: int) -> Dict[str, Any]:
    """
    One-click Full CG / Recall Gallery Unlocker:
    1. Automatically backs up current saves before modification.
    2. For RPG Maker MV/MZ: scans System.json for recall/gallery/CG switches, injects non-destructive
       acg_vault_cg_unlocker.js plugin (auto-enables gallery switches + F8 / Shift+F8 in-game hotkey).
    3. Marks game as cg_unlocked = 1.
    """
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_path = game.get("folder_path")
    if not folder_path or not os.path.exists(folder_path):
        return {"success": False, "message": "游戏本地目录不存在"}

    from core.launcher import backup_game_saves, get_game_save_status
    try:
        backup_game_saves(game_id, label="全CG解锁前备份")
    except Exception:
        pass

    rm_root = _find_rpgmaker_root(folder_path)
    if rm_root:
        try:
            sys_file = rm_root / "data" / "System.json"
            recall_sw_count = 0
            total_sw_count = 0
            if sys_file.exists():
                with open(sys_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                    sys_data = json.load(f)
                switches = sys_data.get("switches") or []
                total_sw_count = len([s for s in switches if s])
                pat = re.compile(r"回想|全開|全开|解放|解禁|クリア|ギャラリー|CG|Gallery|Recall|Scene|Ending|ED|シーン|イベント|Hシーン", re.I)
                recall_sw_count = len([s for s in switches if s and pat.search(str(s))])

            plugins_dir = rm_root / "js" / "plugins"
            plugins_dir.mkdir(parents=True, exist_ok=True)
            unlocker_js = plugins_dir / "acg_vault_cg_unlocker.js"
            with open(unlocker_js, "w", encoding="utf-8") as f:
                f.write(CG_UNLOCKER_PLUGIN_CODE)

            plugins_file = rm_root / "js" / "plugins.js"
            if plugins_file.exists():
                with open(plugins_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                    code = f.read()
                if '"name":"acg_vault_cg_unlocker"' not in code:
                    idx = code.rfind("];")
                    if idx != -1:
                        prefix_check = code[:idx].rstrip()
                        comma = "" if prefix_check.endswith("[") else ","
                        entry = f'{comma}\n{{"name":"acg_vault_cg_unlocker","status":true,"description":"ACG Vault Full CG Unlocker","parameters":{{}}}}\n];'
                        with open(plugins_file, "w", encoding="utf-8") as f:
                            f.write(code[:idx] + entry)

            manual_update_game_metadata(game_id, {"cg_unlocked": 1})
            return {
                "success": True,
                "cg_unlocked": 1,
                "recall_switches_found": recall_sw_count,
                "total_switches": total_sw_count,
                "save_status": get_game_save_status(game_id),
                "message": (
                    f"已成功注入全 CG 回想解锁模块（识别到 {recall_sw_count} 个回想/画廊专属开关，共 {total_sw_count} 个系统开关）！\n"
                    "进入游戏后将自动激活回想开关，您也可在游戏内随时按【F8】一键解锁全回想与满金币（按 Shift+F8 强开全部开关）。"
                )
            }
        except Exception as e:
            return {"success": False, "message": f"注入全 CG 模块失败: {str(e)}"}

    return {
        "success": False,
        "message": "该游戏引擎暂不支持自动生成全 CG 补丁，请使用右侧【导入全CG存档】上传 .zip 或存档文件一键合入。"
    }


def import_cg_save_archive(game_id: int, file_bytes: bytes, orig_filename: str) -> Dict[str, Any]:
    """
    Imports an external Full-CG save archive (.zip) or individual save file (.rpgsave, .rmmzsave, .rvdata2, .sav, .dat)
    into the game's save directory, automatically backing up existing saves first.
    """
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_path = game.get("folder_path", "")
    if not folder_path or not os.path.exists(folder_path):
        return {"success": False, "message": "游戏本地目录不存在"}

    from core.launcher import find_game_save_dir, backup_game_saves, get_game_save_status, is_subpath

    try:
        backup_game_saves(game_id, label="导入全CG存档前自动备份")
    except Exception:
        pass

    save_dir_str = find_game_save_dir(folder_path)
    if not save_dir_str:
        p = Path(folder_path)
        if (p / "www").is_dir():
            save_dir = p / "www" / "save"
        elif (p / "game").is_dir():
            save_dir = p / "game" / "saves"
        else:
            save_dir = p / "save"
        save_dir.mkdir(parents=True, exist_ok=True)
    else:
        save_dir = Path(save_dir_str)

    target_root = save_dir.resolve()
    ext = Path(orig_filename).suffix.lower() if orig_filename else ""

    try:
        imported_count = 0
        if ext == ".zip" or file_bytes.startswith(b"PK\x03\x04"):
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
                members = [m for m in zf.infolist() if not m.is_dir()]
                common_prefix = ""
                if members:
                    first_parts = [Path(m.filename).parts for m in members if Path(m.filename).parts]
                    if first_parts and all(len(p) > 1 and p[0].lower() in ("save", "saves", "savedata", "www") for p in first_parts):
                        common_prefix = first_parts[0][0]

                for member in members:
                    rel_parts = Path(member.filename).parts
                    if not rel_parts:
                        continue
                    if common_prefix and len(rel_parts) > 1 and rel_parts[0] == common_prefix:
                        rel_parts = rel_parts[1:]
                        if len(rel_parts) > 1 and rel_parts[0].lower() in ("save", "saves"):
                            rel_parts = rel_parts[1:]
                    clean_rel = Path(*rel_parts)
                    dest_path = (target_root / clean_rel).resolve()
                    if not is_subpath(str(dest_path), str(target_root)):
                        continue
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member, "r") as src, open(dest_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    imported_count += 1
        else:
            safe_name = Path(orig_filename).name if orig_filename else "global.rmmzsave"
            dest_path = (target_root / safe_name).resolve()
            if not is_subpath(str(dest_path), str(target_root)):
                return {"success": False, "message": "非法的文件名路径"}
            with open(dest_path, "wb") as dst:
                dst.write(file_bytes)
            imported_count = 1

        if imported_count == 0:
            return {"success": False, "message": "压缩包内未找到有效的存档文件"}

        manual_update_game_metadata(game_id, {"cg_unlocked": 1})
        return {
            "success": True,
            "cg_unlocked": 1,
            "imported_count": imported_count,
            "save_status": get_game_save_status(game_id),
            "message": f"成功导入 {imported_count} 个全 CG 存档文件至 {save_dir.name}（原存档已自动快照备份）！"
        }
    except Exception as e:
        return {"success": False, "message": f"导入全 CG 存档失败: {str(e)}"}
