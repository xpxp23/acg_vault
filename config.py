import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
COVERS_DIR = DATA_DIR / "covers"
COVERS_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = DATA_DIR / "config.json"
DB_PATH = DATA_DIR / "acg_vault.db"

DEFAULT_CONFIG = {
    "game_directories": [r"E:\ACG"],
    "archive_directory": r"E:\ACG\_Archive_Duplicates",
    "mtool_directory": r"E:\ACG\MTool",
    "proxy": "",  # e.g. "http://127.0.0.1:7890"
    "auto_scrape": True,
    "scrape_source": "auto",  # "auto", "dlsite", "bangumi"
    "theme": "dark",
    "port": 8000
}

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                merged.update(cfg)
                return merged
        except Exception:
            pass
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict) -> dict:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg
