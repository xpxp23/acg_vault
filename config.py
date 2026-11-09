import os
import sys
import copy
import json
import threading
from pathlib import Path
from typing import Dict, Any, Optional

APP_VERSION = "3.2.0"

# 冻结成 exe 后，__file__ 在 _MEIPASS 临时目录里；数据必须落在 exe 旁边，
# 静态资源则从打包目录读。这样 exe 和源码共享同一份 data/。
if getattr(sys, "frozen", False):
    _exe_dir = Path(sys.executable).resolve().parent
    # onedir 布局：exe 在 <root>\ACGVault\ 里，data 在 <root>\data。
    # 如果 exe 同目录已经有 data（便携版），就跟着 exe 走；否则用上一级，保证和源码共用同一份库。
    if (_exe_dir / "data").is_dir():
        BASE_DIR = _exe_dir
    elif (_exe_dir.parent / "data").is_dir():
        BASE_DIR = _exe_dir.parent
    else:
        BASE_DIR = _exe_dir
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", str(_exe_dir)))
else:
    BASE_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = BASE_DIR

DATA_DIR = Path(os.environ.get("ACG_VAULT_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
COVERS_DIR = DATA_DIR / "covers"
COVERS_DIR.mkdir(parents=True, exist_ok=True)
THUMBS_DIR = COVERS_DIR / "thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)
GALLERY_DIR = DATA_DIR / "gallery"
GALLERY_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = DATA_DIR / "config.json"
DB_PATH = DATA_DIR / "acg_vault.db"
L10N_TAGS_FILE = DATA_DIR / "l10n_tags_zh.json"

SENSITIVE_CONFIG_KEYS = ("llm_api_key", "webdav_password")

DEFAULT_CONFIG: Dict[str, Any] = {
    "game_directories": [r"E:\ACG"],
    "archive_directory": r"E:\ACG\_Archive_Duplicates",
    "save_backup_directory": r"E:\ACG\_Save_Backups",
    "mtool_directory": r"E:\ACG\MTool",
    "leproc_path": "",  # e.g. "E:\\ACG\\Locale.Emulator\\LEProc.exe"
    "proxy": "",  # e.g. "http://127.0.0.1:7890"
    "auto_scrape": True,
    "scrape_source": "auto",  # "auto", "dlsite", "bangumi", "steam", "vndb"
    "incremental_scan": True,
    "auto_localize_tags": True,
    # UI & Reading Customization
    "default_view_mode": "grid",  # "grid", "list", "analytics"
    "cover_fit_mode": "smart",  # "smart" (blur backdrop + contain), "portrait" (3:4), "landscape" (4:3)
    "grid_density": "standard",  # "compact", "standard", "comfortable"
    "card_hover_style": "minimal",  # "minimal" (corner play, unobstructed art) or "classic" (center play)
    "card_footer_slot": "auto",  # "auto" (rating if >0 else tags/playtime), "tags", "rating"
    "notes_default_layout": "last",  # "last" (记住上次) | "reader" (纯净阅读) | "split" | "editor"
    "notes_default_toc": True,
    "notes_sync_scroll": True,
    "notes_font_size": "md",  # "sm", "md", "lg"
    "clear_batch_on_filter": True,
    "theme": "dark",
    "port": 8000,
    # Desktop Native, Companion Overlay & Hotkey Settings
    "desktop_mode": "native",  # "native" (PyWebView / App window) or "browser"
    "frameless_window": True,  # 无边框窗口（自绘拖动条与窗口按钮）
    # Magpie 全屏集成 (v2.7)
    "magpie_enabled": True,
    "magpie_path": "",            # 留空自动探测
    "magpie_autostart": True,     # 需要时自动 Magpie.exe -st
    "magpie_auto_scale": True,    # 启动游戏后自动全屏（默认仅大屏模式）
    "magpie_auto_scope": "bigscreen",  # "bigscreen" | "always"
    "magpie_auto_delay": 8,       # 游戏窗口出现后再等 N 秒
    "magpie_active_preset": "pixel",  # 上次应用的 Magpie 预设
    "ui_theme": "auto",           # auto | dark | light（深色=夜间，浅色=Switch 风格日间）
    "ui_accent": "nintendo",      # nintendo | indigo | emerald | amber | violet
    "window_bounds": {"x": None, "y": None, "width": 1460, "height": 920, "maximized": False},
    "overlay_bounds": {"x": None, "y": None, "width": 460, "height": 740},
    "minimize_to_tray": True,
    "auto_start_windows": False,
    "global_boss_hotkey": "Alt+Space",
    "global_overlay_hotkey": "Alt+G",
    "overlay_click_through": False,
    "enable_ingame_screenshot": True,
    "screenshot_hotkey": "F12",
    # Gamepad → Keyboard bridge (v2.5, RPG Maker optimized)
    "gamepad_enabled": True,
    "gamepad_deadzone": 0.35,
    "gamepad_profile": "auto",  # "auto" | "rm_mv_mz" | "rm_rgss" | "wolf" | "generic"
    "gamepad_back_screenshot": True,
    "gamepad_bindings": {},      # {"a": "confirm", ...} 覆盖默认映射
    "gamepad_per_game": {},      # {"<game_id>": {"profile": "...", "enabled": false}}
    # Auto Incremental Save Snapshot & WebDAV Cloud Backup (v2.4)
    "enable_auto_save_backup": True,
    "auto_backup_min_minutes": 5,
    "auto_backup_max_keep": 5,
    "webdav_enabled": False,
    "webdav_url": "",
    "webdav_root_path": "/ACG_Vault_Saves",
    "webdav_username": "",
    "webdav_password": "",
    "webdav_auto_sync": True,
    # LLM AI Scraper & Walkthrough Engine Settings
    "llm_enabled": False,
    "llm_api_base": "https://api.deepseek.com/v1",
    "llm_api_key": "",
    "llm_model": "deepseek-chat",
    "llm_temperature": 0.3,
    "llm_auto_translate": True
}

_CONFIG_LOCK = threading.RLock()
_CONFIG_CACHE: Optional[Dict[str, Any]] = None
_CONFIG_MTIME: float = -1.0


def mask_sensitive_config(cfg: dict) -> dict:
    """Masks sensitive keys (e.g. llm_api_key, webdav_password) before returning config to the frontend."""
    out = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
    for key in SENSITIVE_CONFIG_KEYS:
        val = out.get(key)
        if isinstance(val, str) and val.strip():
            s = val.strip()
            if "****" in s:
                out[key] = s
            elif len(s) <= 6:
                out[key] = "****"
            else:
                out[key] = f"{s[:3]}****{s[-2:]}"
    return out


def merge_masked_secrets(new_cfg: dict, old_cfg: dict) -> dict:
    """Preserves original secrets from old_cfg when incoming new_cfg contains masked '****' placeholders."""
    out = copy.deepcopy(new_cfg) if isinstance(new_cfg, dict) else {}
    old = old_cfg if isinstance(old_cfg, dict) else {}
    for key in SENSITIVE_CONFIG_KEYS:
        if key in out:
            val = out.get(key)
            if isinstance(val, str) and "****" in val:
                out[key] = old.get(key, "")
    return out


def sync_windows_autostart(enable: bool) -> bool:
    """Registers or removes ACG Vault in Windows HKCU Run registry for auto-start."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "ACGVault"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}" --minimized'
                else:
                    pythonw = Path(sys.executable).with_name("pythonw.exe")
                    exe_to_use = str(pythonw) if pythonw.exists() else sys.executable
                    desktop_script = BASE_DIR / "desktop_app.py"
                    target_script = str(desktop_script if desktop_script.exists() else (BASE_DIR / "main.py"))
                    cmd = f'"{exe_to_use}" "{target_script}" --minimized'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"[Config] Windows autostart sync error: {e}")
        return False


def load_config() -> dict:
    """Loads configuration with thread-safe st_mtime memory caching and returns a deep copy."""
    global _CONFIG_CACHE, _CONFIG_MTIME
    with _CONFIG_LOCK:
        if CONFIG_FILE.exists():
            try:
                st_mtime = CONFIG_FILE.stat().st_mtime
                if _CONFIG_CACHE is not None and st_mtime == _CONFIG_MTIME:
                    return copy.deepcopy(_CONFIG_CACHE)
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                merged = copy.deepcopy(DEFAULT_CONFIG)
                if isinstance(cfg, dict):
                    merged.update(cfg)
                if isinstance(merged.get("game_directories"), list):
                    cleaned_dirs = [str(d).strip() for d in merged["game_directories"] if str(d).strip()]
                    merged["game_directories"] = cleaned_dirs or copy.deepcopy(DEFAULT_CONFIG["game_directories"])
                _CONFIG_CACHE = copy.deepcopy(merged)
                _CONFIG_MTIME = st_mtime
                return copy.deepcopy(merged)
            except Exception:
                if _CONFIG_CACHE is not None:
                    return copy.deepcopy(_CONFIG_CACHE)
        saved = save_config(DEFAULT_CONFIG)
        return copy.deepcopy(saved)


def save_config(cfg: dict) -> dict:
    """Atomically writes config via config.json.tmp -> os.replace and immediately updates memory cache."""
    global _CONFIG_CACHE, _CONFIG_MTIME
    with _CONFIG_LOCK:
        prev_cfg: Dict[str, Any] = {}
        if _CONFIG_CACHE is not None:
            prev_cfg = copy.deepcopy(_CONFIG_CACHE)
        elif CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        prev_cfg = loaded
            except Exception:
                pass

        prev_auto_start = prev_cfg.get("auto_start_windows")
        incoming = merge_masked_secrets(cfg if isinstance(cfg, dict) else {}, prev_cfg)

        merged = copy.deepcopy(DEFAULT_CONFIG)
        if prev_cfg:
            merged.update(prev_cfg)
        merged.update(incoming)

        if isinstance(merged.get("game_directories"), list):
            cleaned_dirs = [str(d).strip() for d in merged["game_directories"] if str(d).strip()]
            merged["game_directories"] = cleaned_dirs or copy.deepcopy(DEFAULT_CONFIG["game_directories"])

        try:
            merged["port"] = max(1024, min(65535, int(merged.get("port", 8000))))
        except Exception:
            merged["port"] = 8000

        try:
            merged["auto_backup_min_minutes"] = max(1, min(120, int(merged.get("auto_backup_min_minutes", 5))))
        except Exception:
            merged["auto_backup_min_minutes"] = 5

        try:
            merged["auto_backup_max_keep"] = max(1, min(30, int(merged.get("auto_backup_max_keep", 5))))
        except Exception:
            merged["auto_backup_max_keep"] = 5

        try:
            merged["gamepad_deadzone"] = max(0.05, min(0.9, float(merged.get("gamepad_deadzone", 0.35))))
        except Exception:
            merged["gamepad_deadzone"] = 0.35

        if not isinstance(merged.get("gamepad_bindings"), dict):
            merged["gamepad_bindings"] = {}
        if not isinstance(merged.get("gamepad_per_game"), dict):
            merged["gamepad_per_game"] = {}

        tmp_file = CONFIG_FILE.with_name("config.json.tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            os.replace(tmp_file, CONFIG_FILE)
        except Exception:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)

        try:
            _CONFIG_MTIME = CONFIG_FILE.stat().st_mtime
        except Exception:
            _CONFIG_MTIME = -1.0
        _CONFIG_CACHE = copy.deepcopy(merged)

        # Always ensure Windows registry path stays accurate when enabled or toggled
        if merged.get("auto_start_windows") or prev_auto_start != merged.get("auto_start_windows"):
            sync_windows_autostart(bool(merged.get("auto_start_windows")))

        return copy.deepcopy(merged)
