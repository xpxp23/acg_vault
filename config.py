import os
import sys
import json
from pathlib import Path

APP_VERSION = "2.3.0"

BASE_DIR = Path(__file__).resolve().parent
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

DEFAULT_CONFIG = {
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
    "notes_default_layout": "split",  # "split", "reader", "editor"
    "notes_default_toc": True,
    "notes_sync_scroll": True,
    "notes_font_size": "md",  # "sm", "md", "lg"
    "clear_batch_on_filter": True,
    "theme": "dark",
    "port": 8000,
    # Desktop Native, Companion Overlay & Hotkey Settings
    "desktop_mode": "native",  # "native" (PyWebView / App window) or "browser"
    "minimize_to_tray": True,
    "auto_start_windows": False,
    "global_boss_hotkey": "Alt+Space",
    "global_overlay_hotkey": "Alt+G",
    "enable_ingame_screenshot": True,
    "screenshot_hotkey": "F12",
    # Auto Incremental Save Snapshot & WebDAV Cloud Backup (v2.3)
    "enable_auto_save_backup": True,
    "auto_backup_min_minutes": 5,
    "auto_backup_max_keep": 5,
    "webdav_enabled": False,
    "webdav_url": "",
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
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                if isinstance(cfg, dict):
                    merged.update(cfg)
                if isinstance(merged.get("game_directories"), list):
                    cleaned_dirs = [str(d).strip() for d in merged["game_directories"] if str(d).strip()]
                    merged["game_directories"] = cleaned_dirs or DEFAULT_CONFIG["game_directories"].copy()
                return merged
        except Exception:
            pass
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> dict:
    prev_auto_start = None
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                prev_auto_start = json.load(f).get("auto_start_windows")
        except Exception:
            pass

    merged = DEFAULT_CONFIG.copy()
    if isinstance(cfg, dict):
        merged.update(cfg)
    if isinstance(merged.get("game_directories"), list):
        cleaned_dirs = [str(d).strip() for d in merged["game_directories"] if str(d).strip()]
        merged["game_directories"] = cleaned_dirs or DEFAULT_CONFIG["game_directories"].copy()

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

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    # Always ensure Windows registry path stays accurate when enabled or toggled
    if merged.get("auto_start_windows") or prev_auto_start != merged.get("auto_start_windows"):
        sync_windows_autostart(bool(merged.get("auto_start_windows")))

    return merged
