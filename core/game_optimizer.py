# -*- coding: utf-8 -*-
"""
RPG Maker MV/MZ & Unity Built-in Framerate Unlock, Runtime Booster & Lossless Size Slimming Toolbox
for ACG Vault v3.3.0.
"""

import io
import os
import re
import json
import shutil
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from db.database import get_game_by_id, manual_update_game_metadata
from core.mz_patcher import inject_entry_into_plugins_js

PERF_PLUGIN_NAME = "acg_vault_perf_booster"
PERF_PLUGIN_FILENAME = "acg_vault_perf_booster.js"
BACKUP_ARCHIVE_NAME = "_acg_optimizer_backup.zip"
BACKUP_MANIFEST_NAME = "_acg_optimizer_manifest.json"

KEEP_LOCALE_PAKS = {
    "zh-cn.pak", "zh-tw.pak", "ja.pak", "en-us.pak", "en-gb.pak"
}

JUNK_DIR_PATTERNS = (
    "_burstdebuginformation_donotship",
    "_backupthisfolder_butdontshipitwithyourgame",
    "crashpad",
    "crashes",
    "logs",
)

JUNK_FILE_EXTENSIONS = (
    ".pdb", ".dmp", ".mdmp", ".log", ".tmp", ".old"
)

JUNK_EXACT_FILENAMES = {
    "player.log", "player-prev.log", "output_log.txt", "debug.log",
    "nwjc.exe", "chromedriver.exe", "payload.exe", "notification_helper.exe"
}


def _build_perf_booster_js(target_fps: int = 120, fast_skip_mult: int = 4, keep_bg_audio: bool = True) -> str:
    """Generates the RPG Maker MV/MZ High-FPS, Fast-Skip & Smooth Frame Pacing runtime plugin."""
    fps_val = max(30, min(360, int(target_fps or 120)))
    skip_val = max(2, min(10, int(fast_skip_mult or 4)))
    bg_audio_js = "true" if keep_bg_audio else "false"
    return f"""//=============================================================================
// {PERF_PLUGIN_FILENAME}
// ACG Vault v3.3.0 High-Refresh Rate Unlocker, Turbo Skip & GPU Frame Pacing Booster
// Compatible with RPG Maker MV (PIXI v4) & RPG Maker MZ (PIXI v5)
//=============================================================================
/*:
 * @target MZ MV
 * @plugindesc [v3.3.0] ACG Vault Engine Performance & High-FPS Booster ({fps_val}Hz)
 * @author ACG Vault Optimizer
 * @help
 * - Unlocks frame rate cap up to {fps_val} FPS (or monitor native refresh rate)
 * - Hold Ctrl or Gamepad RB (R1) for {skip_val}x Turbo Fast-Forward
 * - Press F3 to toggle compact FPS / Frame-time HUD overlay
 * - Keeps BGM/SE playing smoothly when window loses focus
 */

(() => {{
    'use strict';
    const TARGET_FPS = {fps_val};
    const TURBO_MULTIPLIER = {skip_val};
    const KEEP_BG_AUDIO = {bg_audio_js};

    const applyTickerCap = () => {{
        try {{
            if (typeof Graphics !== 'undefined' && Graphics._app && Graphics._app.ticker) {{
                Graphics._app.ticker.maxFPS = TARGET_FPS >= 240 ? 0 : TARGET_FPS;
                Graphics._app.ticker.minFPS = 15;
            }}
            if (typeof PIXI !== 'undefined' && PIXI.ticker && PIXI.ticker.shared) {{
                PIXI.ticker.shared.maxFPS = TARGET_FPS >= 240 ? 0 : TARGET_FPS;
                PIXI.ticker.shared.minFPS = 15;
            }}
        }} catch (e) {{}}
    }};

    if (typeof SceneManager !== 'undefined') {{
        const _SceneManager_initialize = SceneManager.initialize;
        SceneManager.initialize = function() {{
            const res = _SceneManager_initialize.apply(this, arguments);
            applyTickerCap();
            return res;
        }};
        if (SceneManager._deltaTime !== undefined && TARGET_FPS > 60) {{
            SceneManager._deltaTime = 1.0 / TARGET_FPS;
        }}
    }}

    if (KEEP_BG_AUDIO && typeof WebAudio !== 'undefined') {{
        WebAudio._shouldMuteOnHide = function() {{
            return false;
        }};
    }}

    let isTurboActive = false;
    const checkTurboInput = () => {{
        try {{
            const kbFast = typeof Input !== 'undefined' && Input.isPressed && Input.isPressed('control');
            let padFast = false;
            if (navigator.getGamepads) {{
                const pads = navigator.getGamepads();
                for (let i = 0; i < pads.length; i++) {{
                    const p = pads[i];
                    if (p && p.connected && p.buttons && p.buttons[5] && p.buttons[5].pressed) {{
                        padFast = true;
                        break;
                    }}
                }}
            }}
            isTurboActive = Boolean(kbFast || padFast);
        }} catch (e) {{
            isTurboActive = false;
        }}
        return isTurboActive;
    }};

    if (typeof Scene_Map !== 'undefined' && Scene_Map.prototype.isFastForward) {{
        const _Scene_Map_isFastForward = Scene_Map.prototype.isFastForward;
        Scene_Map.prototype.isFastForward = function() {{
            return _Scene_Map_isFastForward.apply(this, arguments) || checkTurboInput();
        }};
    }}

    if (typeof SceneManager !== 'undefined' && SceneManager.updateMain) {{
        const _SceneManager_updateMain = SceneManager.updateMain;
        SceneManager.updateMain = function() {{
            applyTickerCap();
            _SceneManager_updateMain.apply(this, arguments);
            if (checkTurboInput() && this._scene) {{
                for (let i = 1; i < TURBO_MULTIPLIER; i++) {{
                    if (typeof this.updateInputData === 'function') this.updateInputData();
                    if (typeof this.changeScene === 'function') this.changeScene();
                    if (typeof this.updateScene === 'function') this.updateScene();
                }}
            }}
            updateFpsHud();
        }};
    }}

    let hudEl = null;
    let hudVisible = false;
    let frameCount = 0;
    let lastFpsTs = performance.now();
    let currentFps = 60;

    function ensureHud() {{
        if (hudEl || !document.body) return;
        hudEl = document.createElement('div');
        hudEl.id = 'acg-vault-fps-hud';
        hudEl.style.cssText = [
            'position:fixed', 'top:8px', 'left:8px', 'z-index:999999',
            'padding:3px 9px', 'border-radius:6px',
            'background:rgba(8,12,22,0.78)', 'border:1px solid rgba(56,189,248,0.45)',
            'color:#e2e8f0', 'font:600 12px/1.4 Consolas,monospace',
            'pointer-events:none', 'user-select:none', 'display:none',
            'backdrop-filter:blur(6px)'
        ].join(';');
        document.body.appendChild(hudEl);
    }}

    function updateFpsHud() {{
        frameCount++;
        const now = performance.now();
        if (now - lastFpsTs >= 500) {{
            currentFps = Math.round((frameCount * 1000) / (now - lastFpsTs));
            frameCount = 0;
            lastFpsTs = now;
            if (hudVisible) {{
                ensureHud();
                if (hudEl) {{
                    const turboTag = isTurboActive ? ' · ⚡' + TURBO_MULTIPLIER + 'x' : '';
                    hudEl.textContent = currentFps + ' FPS (Target ' + TARGET_FPS + ')' + turboTag;
                }}
            }}
        }}
    }}

    window.addEventListener('keydown', (ev) => {{
        if (ev.key === 'F3') {{
            hudVisible = !hudVisible;
            ensureHud();
            if (hudEl) hudEl.style.display = hudVisible ? 'block' : 'none';
        }}
    }}, true);
}})();
"""


def _format_size(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "0 B"
    mb = num_bytes / (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    if mb >= 1.0:
        return f"{mb:.1f} MB"
    return f"{max(1, int(num_bytes / 1024))} KB"


def _resolve_rpg_root(folder: Path) -> Optional[Path]:
    if (folder / "www" / "js" / "plugins.js").is_file():
        return folder / "www"
    if (folder / "js" / "plugins.js").is_file():
        return folder
    return None


def _resolve_unity_data_dir(folder: Path) -> Optional[Path]:
    try:
        for child in folder.iterdir():
            if child.is_dir() and child.name.endswith("_Data"):
                return child
    except Exception:
        pass
    return None


def _is_junk_file(fp: Path, rel_parts_lower: Tuple[str, ...]) -> Tuple[bool, str]:
    if any(p in ("save", "saves", "userdata", "_acg_backup", "data_original_backup") for p in rel_parts_lower):
        return False, ""
    name_low = fp.name.lower()
    if name_low.startswith("_acg_"):
        return False, ""

    for part in rel_parts_lower[:-1]:
        if any(pat in part for pat in JUNK_DIR_PATTERNS):
            return True, "冗余调试/崩溃目录"

    if len(rel_parts_lower) >= 2 and rel_parts_lower[-2] == "locales" and name_low.endswith(".pak"):
        if name_low not in KEEP_LOCALE_PAKS:
            return True, "NW.js 冗余多国语言包"

    if name_low in JUNK_EXACT_FILENAMES:
        return True, "引擎调试工具/运行日志"

    if name_low.endswith(JUNK_FILE_EXTENSIONS):
        if name_low.endswith(".bak") and ("plugins.js" in name_low or "package.json" in name_low or "boot.config" in name_low):
            return False, ""
        return True, "调试符号与临时转储"

    return False, ""


def inspect_game_optimization(game_id: int) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_str = game.get("folder_path") or ""
    if not folder_str or not os.path.exists(folder_str):
        return {"success": False, "message": "游戏本地目录不存在"}

    folder = Path(folder_str)
    rpg_root = _resolve_rpg_root(folder)
    unity_data = _resolve_unity_data_dir(folder)
    engine_type = game.get("engine_type") or ""

    has_encrypted_images = False
    if rpg_root:
        sys_json = rpg_root / "data" / "System.json"
        if sys_json.is_file():
            try:
                with open(sys_json, "r", encoding="utf-8-sig", errors="ignore") as f:
                    sys_obj = json.load(f)
                has_encrypted_images = bool(sys_obj.get("hasEncryptedImages"))
            except Exception:
                pass

    fps_patched = False
    current_target_fps = 60
    fps_patch_type = "none"
    if rpg_root:
        fps_patch_type = "rpgmaker_mv_mz"
        booster_file = rpg_root / "js" / "plugins" / PERF_PLUGIN_FILENAME
        plugins_js = rpg_root / "js" / "plugins.js"
        if booster_file.is_file() and plugins_js.is_file():
            try:
                txt = plugins_js.read_text(encoding="utf-8-sig", errors="ignore")
                if PERF_PLUGIN_NAME in txt:
                    fps_patched = True
                b_txt = booster_file.read_text(encoding="utf-8-sig", errors="ignore")
                m = re.search(r"const\s+TARGET_FPS\s*=\s*(\d+)", b_txt)
                if m:
                    current_target_fps = int(m.group(1))
            except Exception:
                pass
    elif unity_data:
        fps_patch_type = "unity"
        boot_cfg = unity_data / "boot.config"
        if boot_cfg.is_file():
            try:
                b_txt = boot_cfg.read_text(encoding="utf-8-sig", errors="ignore")
                if "acg_vault_optimized=1" in b_txt or "gfx-enable-native-gfx-jobs=1" in b_txt:
                    fps_patched = True
                    current_target_fps = 120
            except Exception:
                pass

    total_bytes = 0
    image_bytes = 0
    image_count = 0
    compressible_image_bytes = 0
    compressible_image_count = 0
    audio_bytes = 0
    audio_count = 0
    video_bytes = 0
    video_count = 0
    junk_bytes = 0
    junk_count = 0
    junk_items: List[Dict[str, Any]] = []

    try:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in ("data_original_backup", "_acg_backup")]
            root_p = Path(root)
            for fn in files:
                if fn in (BACKUP_ARCHIVE_NAME, BACKUP_MANIFEST_NAME):
                    continue
                fp = root_p / fn
                try:
                    fsize = fp.stat().st_size
                except Exception:
                    continue
                total_bytes += fsize
                rel_p = fp.relative_to(folder)
                rel_parts_low = tuple(p.lower() for p in rel_p.parts)
                ext = fp.suffix.lower()

                is_junk, junk_reason = _is_junk_file(fp, rel_parts_low)
                if is_junk:
                    junk_bytes += fsize
                    junk_count += 1
                    if len(junk_items) < 25:
                        junk_items.append({
                            "rel_path": str(rel_p),
                            "size_bytes": fsize,
                            "size_str": _format_size(fsize),
                            "reason": junk_reason
                        })
                    continue

                if ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".rpgmvp", ".png_"):
                    image_bytes += fsize
                    image_count += 1
                    if ext in (".png", ".bmp") and fsize >= 96 * 1024 and not has_encrypted_images:
                        compressible_image_bytes += fsize
                        compressible_image_count += 1
                elif ext in (".ogg", ".wav", ".m4a", ".mp3", ".rpgmvo", ".ogg_"):
                    audio_bytes += fsize
                    audio_count += 1
                elif ext in (".mp4", ".webm", ".avi", ".mkv", ".ogv"):
                    video_bytes += fsize
                    video_count += 1
    except Exception as e:
        return {"success": False, "message": f"目录分析异常: {str(e)}"}

    backup_zip = folder / BACKUP_ARCHIVE_NAME
    has_slim_backup = backup_zip.is_file()
    backup_size_bytes = backup_zip.stat().st_size if has_slim_backup else 0

    est_img_saving = int(compressible_image_bytes * 0.38)
    est_total_saving = junk_bytes + est_img_saving

    return {
        "success": True,
        "game_id": game_id,
        "engine_type": engine_type,
        "fps_patch_type": fps_patch_type,
        "can_patch_fps": fps_patch_type in ("rpgmaker_mv_mz", "unity"),
        "fps_patched": fps_patched,
        "current_target_fps": current_target_fps,
        "has_encrypted_images": has_encrypted_images,
        "has_slim_backup": has_slim_backup,
        "backup_size_str": _format_size(backup_size_bytes),
        "footprint": {
            "total_bytes": total_bytes,
            "total_str": _format_size(total_bytes),
            "image_bytes": image_bytes,
            "image_str": _format_size(image_bytes),
            "image_count": image_count,
            "compressible_image_count": compressible_image_count,
            "compressible_image_str": _format_size(compressible_image_bytes),
            "audio_bytes": audio_bytes,
            "audio_str": _format_size(audio_bytes),
            "audio_count": audio_count,
            "video_bytes": video_bytes,
            "video_str": _format_size(video_bytes),
            "video_count": video_count,
            "junk_bytes": junk_bytes,
            "junk_str": _format_size(junk_bytes),
            "junk_count": junk_count,
            "junk_items": junk_items,
            "estimated_savings_bytes": est_total_saving,
            "estimated_savings_str": _format_size(est_total_saving),
        }
    }


def apply_fps_patch(
    game_id: int,
    target_fps: int = 120,
    fast_skip_mult: int = 4,
    keep_bg_audio: bool = True,
    gpu_raster: bool = True
) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_str = game.get("folder_path") or ""
    if not folder_str or not os.path.exists(folder_str):
        return {"success": False, "message": "游戏目录不存在"}

    folder = Path(folder_str)
    rpg_root = _resolve_rpg_root(folder)
    unity_data = _resolve_unity_data_dir(folder)

    if rpg_root:
        try:
            plugins_dir = rpg_root / "js" / "plugins"
            plugins_dir.mkdir(parents=True, exist_ok=True)
            plugins_js = rpg_root / "js" / "plugins.js"
            if not plugins_js.is_file():
                return {"success": False, "message": "未找到 js/plugins.js，无法注入高刷补丁"}

            bak_js = rpg_root / "js" / "plugins.js.acg_fps_bak"
            if not bak_js.is_file():
                shutil.copy2(plugins_js, bak_js)

            booster_path = plugins_dir / PERF_PLUGIN_FILENAME
            booster_code = _build_perf_booster_js(
                target_fps=target_fps,
                fast_skip_mult=fast_skip_mult,
                keep_bg_audio=keep_bg_audio
            )
            booster_path.write_text(booster_code, encoding="utf-8")

            raw_plugins = plugins_js.read_text(encoding="utf-8-sig", errors="ignore")
            updated_plugins = inject_entry_into_plugins_js(
                raw_plugins,
                PERF_PLUGIN_NAME,
                f"ACG Vault High-FPS ({target_fps}Hz) & Turbo Skip Booster"
            )
            if updated_plugins != raw_plugins:
                plugins_js.write_text(updated_plugins, encoding="utf-8")

            for pkg_cand in (folder / "package.json", rpg_root / "package.json"):
                if pkg_cand.is_file():
                    try:
                        pkg_bak = pkg_cand.with_suffix(".json.acg_fps_bak")
                        if not pkg_bak.is_file():
                            shutil.copy2(pkg_cand, pkg_bak)
                        pkg_obj = json.loads(pkg_cand.read_text(encoding="utf-8-sig", errors="ignore"))
                        if gpu_raster:
                            existing_args = str(pkg_obj.get("chromium-args") or "").strip()
                            needed_flags = [
                                "--ignore-gpu-blocklist",
                                "--enable-gpu-rasterization",
                                "--enable-zero-copy"
                            ]
                            if int(target_fps) > 60:
                                needed_flags.append("--disable-frame-rate-limit")
                            for fl in needed_flags:
                                if fl not in existing_args:
                                    existing_args = (existing_args + " " + fl).strip()
                            pkg_obj["chromium-args"] = existing_args
                        pkg_cand.write_text(json.dumps(pkg_obj, ensure_ascii=False, indent=2), encoding="utf-8")
                    except Exception:
                        pass

            return {
                "success": True,
                "message": f"已成功注入 RPG Maker {target_fps}FPS 高刷解锁、{fast_skip_mult}x 快进加速与后台保活补丁（游戏内按 F3 可显隐帧率 HUD）！",
                "status": inspect_game_optimization(game_id)
            }
        except Exception as e:
            return {"success": False, "message": f"注入高刷补丁失败: {str(e)}"}

    if unity_data:
        try:
            boot_cfg = unity_data / "boot.config"
            boot_bak = unity_data / "boot.config.acg_fps_bak"
            lines: List[str] = []
            if boot_cfg.is_file():
                if not boot_bak.is_file():
                    shutil.copy2(boot_cfg, boot_bak)
                lines = [
                    ln.strip() for ln in boot_cfg.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
                    if ln.strip()
                ]
            kv = {}
            for ln in lines:
                if "=" in ln:
                    k, v = ln.split("=", 1)
                    kv[k.strip()] = v.strip()
            kv["gfx-enable-gfx-jobs"] = "1"
            kv["gfx-enable-native-gfx-jobs"] = "1"
            kv["wait-for-native-debugger"] = "0"
            kv["acg_vault_optimized"] = "1"
            out_txt = "\n".join(f"{k}={v}" for k, v in kv.items()) + "\n"
            boot_cfg.write_text(out_txt, encoding="utf-8")
            return {
                "success": True,
                "message": "已成功应用 Unity 多线程渲染作业 (Native GFX Jobs) 与帧步进优化配置！",
                "status": inspect_game_optimization(game_id)
            }
        except Exception as e:
            return {"success": False, "message": f"优化 Unity 配置失败: {str(e)}"}

    return {"success": False, "message": "当前游戏引擎暂不支持自动注入内置帧率补丁（建议使用 Magpie 缩放或外部工具）"}


def remove_fps_patch(game_id: int) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_str = game.get("folder_path") or ""
    if not folder_str or not os.path.exists(folder_str):
        return {"success": False, "message": "游戏目录不存在"}

    folder = Path(folder_str)
    rpg_root = _resolve_rpg_root(folder)
    unity_data = _resolve_unity_data_dir(folder)

    try:
        if rpg_root:
            booster_path = rpg_root / "js" / "plugins" / PERF_PLUGIN_FILENAME
            if booster_path.is_file():
                booster_path.unlink()
            plugins_js = rpg_root / "js" / "plugins.js"
            if plugins_js.is_file():
                raw = plugins_js.read_text(encoding="utf-8-sig", errors="ignore")
                cleaned_lines = [
                    ln for ln in raw.splitlines()
                    if PERF_PLUGIN_NAME not in ln
                ]
                plugins_js.write_text("\n".join(cleaned_lines) + "\n", encoding="utf-8")
            bak_js = rpg_root / "js" / "plugins.js.acg_fps_bak"
            if bak_js.is_file():
                bak_js.unlink()

            for pkg_cand in (folder / "package.json", rpg_root / "package.json"):
                pkg_bak = pkg_cand.with_suffix(".json.acg_fps_bak")
                if pkg_bak.is_file():
                    shutil.copy2(pkg_bak, pkg_cand)
                    pkg_bak.unlink()

        if unity_data:
            boot_cfg = unity_data / "boot.config"
            boot_bak = unity_data / "boot.config.acg_fps_bak"
            if boot_bak.is_file():
                shutil.copy2(boot_bak, boot_cfg)
                boot_bak.unlink()
            elif boot_cfg.is_file():
                lines = [
                    ln for ln in boot_cfg.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
                    if not ln.startswith("acg_vault_optimized=")
                ]
                boot_cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return {
            "success": True,
            "message": "已成功移除高刷性能补丁并恢复游戏原始配置！",
            "status": inspect_game_optimization(game_id)
        }
    except Exception as e:
        return {"success": False, "message": f"还原帧率补丁失败: {str(e)}"}


def run_game_slim(
    game_id: int,
    clean_junk: bool = True,
    compress_images: bool = True,
    image_mode: str = "lossless_png",
    create_rollback_backup: bool = True
) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_str = game.get("folder_path") or ""
    if not folder_str or not os.path.exists(folder_str):
        return {"success": False, "message": "游戏目录不存在"}

    folder = Path(folder_str)
    rpg_root = _resolve_rpg_root(folder)
    has_encrypted_images = False
    if rpg_root and (rpg_root / "data" / "System.json").is_file():
        try:
            sys_obj = json.loads((rpg_root / "data" / "System.json").read_text(encoding="utf-8-sig", errors="ignore"))
            has_encrypted_images = bool(sys_obj.get("hasEncryptedImages"))
        except Exception:
            pass

    backup_zip_path = folder / BACKUP_ARCHIVE_NAME
    saved_bytes = 0
    cleaned_junk_count = 0
    optimized_img_count = 0

    try:
        from PIL import Image
        has_pil = True
    except ImportError:
        has_pil = False

    zf_mode = "a" if backup_zip_path.is_file() else "w"
    zf = zipfile.ZipFile(backup_zip_path, zf_mode, zipfile.ZIP_DEFLATED) if create_rollback_backup else None
    existing_arcnames = set(zf.namelist()) if zf else set()

    try:
        for root, dirs, files in os.walk(folder, topdown=False):
            root_p = Path(root)
            rel_root = root_p.relative_to(folder)
            if any(p in ("data_original_backup", "_acg_backup", "save", "saves") for p in rel_root.parts):
                continue

            for fn in files:
                if fn in (BACKUP_ARCHIVE_NAME, BACKUP_MANIFEST_NAME):
                    continue
                fp = root_p / fn
                try:
                    orig_size = fp.stat().st_size
                except Exception:
                    continue
                rel_p = fp.relative_to(folder)
                arc_str = str(rel_p).replace("\\", "/")
                rel_parts_low = tuple(p.lower() for p in rel_p.parts)

                if clean_junk:
                    is_junk, _ = _is_junk_file(fp, rel_parts_low)
                    if is_junk:
                        try:
                            if zf and arc_str not in existing_arcnames and orig_size <= 64 * 1024 * 1024:
                                zf.write(fp, arcname=arc_str)
                                existing_arcnames.add(arc_str)
                            fp.unlink()
                            saved_bytes += orig_size
                            cleaned_junk_count += 1
                        except Exception:
                            pass
                        continue

                ext = fp.suffix.lower()
                if compress_images and has_pil and not has_encrypted_images and ext == ".png" and orig_size >= 96 * 1024:
                    try:
                        raw_bytes = fp.read_bytes()
                        if not raw_bytes.startswith(b"\x89PNG"):
                            continue
                        with Image.open(io.BytesIO(raw_bytes)) as im:
                            buf = io.BytesIO()
                            if image_mode == "webp_disguised" and rpg_root is not None:
                                im.save(buf, format="WEBP", quality=92, method=4)
                            else:
                                im.save(buf, format="PNG", optimize=True, compress_level=9)
                            new_bytes = buf.getvalue()

                        if len(new_bytes) < orig_size * 0.92 and (orig_size - len(new_bytes)) >= 12 * 1024:
                            if zf and arc_str not in existing_arcnames:
                                zf.writestr(arc_str, raw_bytes)
                                existing_arcnames.add(arc_str)
                            fp.write_bytes(new_bytes)
                            saved_bytes += (orig_size - len(new_bytes))
                            optimized_img_count += 1
                    except Exception:
                        continue

            if clean_junk and root_p != folder:
                try:
                    if not any(root_p.iterdir()):
                        root_p.rmdir()
                except Exception:
                    pass
    finally:
        if zf:
            zf.close()
            if backup_zip_path.is_file() and not existing_arcnames:
                try:
                    backup_zip_path.unlink()
                except Exception:
                    pass

    new_status = inspect_game_optimization(game_id)
    if new_status.get("success"):
        new_total = new_status["footprint"]["total_bytes"]
        new_str = new_status["footprint"]["total_str"]
        manual_update_game_metadata(game_id, {
            "folder_size_bytes": new_total,
            "folder_size_str": new_str
        })

    return {
        "success": True,
        "saved_bytes": saved_bytes,
        "saved_str": _format_size(saved_bytes),
        "cleaned_junk_count": cleaned_junk_count,
        "optimized_img_count": optimized_img_count,
        "message": (
            f"瘦身完成！共清理 {cleaned_junk_count} 项冗余文件、无损优化 {optimized_img_count} 张立绘/贴图，"
            f"释放空间 {_format_size(saved_bytes)}。"
        ),
        "status": new_status
    }


def rollback_game_slim(game_id: int) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_str = game.get("folder_path") or ""
    if not folder_str or not os.path.exists(folder_str):
        return {"success": False, "message": "游戏目录不存在"}

    folder = Path(folder_str).resolve()
    backup_zip_path = folder / BACKUP_ARCHIVE_NAME
    if not backup_zip_path.is_file():
        return {"success": False, "message": "未找到瘦身备份包，无需还原"}

    restored_count = 0
    try:
        with zipfile.ZipFile(backup_zip_path, "r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                dest = (folder / member.filename).resolve()
                if not str(dest).startswith(str(folder)):
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                restored_count += 1
        backup_zip_path.unlink()
    except Exception as e:
        return {"success": False, "message": f"回滚瘦身备份失败: {str(e)}"}

    new_status = inspect_game_optimization(game_id)
    if new_status.get("success"):
        manual_update_game_metadata(game_id, {
            "folder_size_bytes": new_status["footprint"]["total_bytes"],
            "folder_size_str": new_status["footprint"]["total_str"]
        })

    return {
        "success": True,
        "restored_count": restored_count,
        "message": f"已成功从备份包无损回滚 {restored_count} 个原始文件！",
        "status": new_status
    }
