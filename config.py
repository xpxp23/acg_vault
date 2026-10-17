import os
import json
from pathlib import Path

APP_VERSION = "2.1.0"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("ACG_VAULT_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
COVERS_DIR = DATA_DIR / "covers"
COVERS_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = DATA_DIR / "config.json"
DB_PATH = DATA_DIR / "acg_vault.db"

DEFAULT_CONFIG = {
    "game_directories": [r"E:\ACG"],
    "archive_directory": r"E:\ACG\_Archive_Duplicates",
    "save_backup_directory": r"E:\ACG\_Save_Backups",
    "mtool_directory": r"E:\ACG\MTool",
    "leproc_path": "",  # e.g. "E:\\ACG\\Locale.Emulator\\LEProc.exe"
    "proxy": "",  # e.g. "http://127.0.0.1:7890"
    "auto_scrape": True,
    "scrape_source": "auto",  # "auto", "dlsite", "bangumi", "steam", "vndb"
    "cover_fit_mode": "smart",  # "smart" (blur backdrop + contain), "portrait" (3:4), "landscape" (4:3)
    "theme": "dark",
    "port": 8000
}


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
    merged = DEFAULT_CONFIG.copy()
    if isinstance(cfg, dict):
        merged.update(cfg)
    if isinstance(merged.get("game_directories"), list):
        cleaned_dirs = [str(d).strip() for d in merged["game_directories"] if str(d).strip()]
        merged["game_directories"] = cleaned_dirs or DEFAULT_CONFIG["game_directories"].copy()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return merged
