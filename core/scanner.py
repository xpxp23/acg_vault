import os
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable, Set
from datetime import datetime
from config import load_config

TOOL_KEYWORDS = [
    "agth", "dangotranslator", "团子翻译器", "misakatranslator", "lunatranslator",
    "mtool", "magpie", "locale.emulator", "locale_emulator", "转区工具",
    "renpythief", "解包", "vnr", "losslessscaling", "文字游戏_翻译君",
    "rpgvx", "rpgvxace", "nw.exe.lnk", "trans-"
]

IGNORE_EXE_PATTERNS = [
    re.compile(r"unitycrashhandler.*\.exe$", re.I),
    re.compile(r"unins\d*\.exe$", re.I),
    re.compile(r"uninstall\.exe$", re.I),
    re.compile(r"dxwebsetup\.exe$", re.I),
    re.compile(r"vcredist.*\.exe$", re.I),
    re.compile(r"crashreport.*\.exe$", re.I),
    re.compile(r"config\.exe$", re.I),
    re.compile(r"update.*\.exe$", re.I),
    re.compile(r"patch.*\.exe$", re.I),
    re.compile(r"setup\.exe$", re.I),
    re.compile(r"agth\.exe$", re.I),
    re.compile(r"mtool.*\.exe$", re.I),
    re.compile(r"leproc\.exe$", re.I),
    re.compile(r"leupdater\.exe$", re.I),
    re.compile(r"leinstaller\.exe$", re.I),
    re.compile(r"notification_helper\.exe$", re.I),
]

SKIP_WALK_DIRS = {
    "node_modules", ".git", "audio", "sound", "voice", "bgm", "se", "bgs",
    "img", "image", "images", "picture", "pictures", "cg", "movie", "movies", "video",
    "locales", "swiftshader", "monobleedingedge", "streamingassets", "plugins",
    "data_original_backup", "_archive_duplicates", "_save_backups"
}

KNOWN_TRS_FILENAMES = {
    "翻译文件.json", "translation.json", "trs.json", "zh_cn.json", "chs.json",
    "customtrs.json", "autotrans.json", "manualtransfile.json"
}

NON_TRS_JSON_NAMES = {
    "package.json", "packagev.json", "tsconfig.json", "jsconfig.json",
    "manifest.json", "settings.json", "config.json", "save.json", "system.json",
    "actors.json", "animations.json", "armors.json", "classes.json", "commonevents.json",
    "enemies.json", "items.json", "mapinfos.json", "skills.json", "states.json",
    "tilesets.json", "troops.json", "weapons.json", "credits.json", "options.json",
    "deps.json", "runtimeconfig.json", "global.json", "project.json"
}


def is_valid_translation_json(file_path: str) -> bool:
    """
    Validates whether a .json file is actually an external translation dictionary
    (key-value string mapping) rather than a game engine/plugin config file.
    """
    p = Path(file_path)
    name_low = p.name.lower()
    if name_low in KNOWN_TRS_FILENAMES:
        return True
    if name_low in NON_TRS_JSON_NAMES:
        return False
    if any(k in name_low for k in ("config", "setting", "manifest", "runtime", " map", "save", "plugin", "shader", "asset", "catalog", "bundle")):
        return False
    if re.match(r"^map\d+\.json$", name_low):
        return False

    try:
        st = p.stat()
        if st.st_size < 20 or st.st_size > 35 * 1024 * 1024:
            return False
        with open(p, "r", encoding="utf-8-sig", errors="ignore") as f:
            head = f.read(65536).strip()
            if not head.startswith("{"):
                return False
            f.seek(0)
            data = json.load(f)
        if not isinstance(data, dict) or len(data) < 3:
            return False
        sample_pairs = 0
        cjk_hits = 0
        for idx, (k, v) in enumerate(data.items()):
            if idx >= 15:
                break
            if isinstance(k, str) and isinstance(v, str):
                sample_pairs += 1
                if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", k) or re.search(r"[\u4e00-\u9fff]", v):
                    cjk_hits += 1
        return sample_pairs >= 3 and cjk_hits >= 1
    except Exception:
        return False


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def is_tool_folder(folder_name: str) -> bool:
    low = folder_name.lower()
    for kw in TOOL_KEYWORDS:
        if kw in low:
            return True
    return False


def clean_title_from_folder(folder_name: str) -> str:
    """Cleans messy folder prefixes, tags, versions, suffixes to find raw game title."""
    title = folder_name.strip()

    # Remove leading RJ/VJ/BJ code prefixes like "RJ123456_" or "[RJ123456]"
    title = re.sub(r"^\s*([RVB]J\d{6,8})[\s_\-]+", "", title, flags=re.I)

    # Remove leading bracketed tags like 【PC官中SLG】, [NitroPlus], [RJxxxxxx]
    # Only strip if there is remaining text after the bracket!
    while True:
        prev = title
        for pat in (
            r"^\s*\[[^\]]+\]\s*(?=.+)",
            r"^\s*【[^】]+】\s*(?=.+)",
            r"^\s*\([^\)]+\)\s*(?=.+)",
            r"^\s*（[^）]+）\s*(?=.+)"
        ):
            title = re.sub(pat, "", title)
        if title == prev:
            break

    # Remove inner layer tag (内层)
    title = re.sub(r"[\(\（\[【]?内层[\)\）\]】]?", "", title, flags=re.I)

    # Remove trailing version markers only when preceded by non-letter boundary or explicit 'ver'
    trailing_patterns = [
        r"(?:^|(?<=[\s_\-\.\[\(【（\u4e00-\u9fff\u3040-\u30ff]))(?:ver\.?\s*|v\s*)\d+(?:\.\d+)*[a-zA-Z]?(?:[\s_\-\.\]\)]|$).*$",
        r"[\s_\-]*[\(\[【（]?(?:电脑|製品版|体验版|体験版|汉化(?:硬盘)?版|精翻汉化版|官中(?:无修)?版|官方中文(?:版)?|中文(?:动态)?版?|步兵版|繁中版|无修版|完整版|整合版)[\)\]】）]?.*$",
        r"[\s_\-]+(?:Steam|DLsite|挂载汉化|MTool汉化|内嵌汉化).*$",
        r"_\d{6,}$",
        r"[\s_\-]+(?:zh-CN|zh-TW|CHS|CHT|CN|JP)$"
    ]
    for pat in trailing_patterns:
        cleaned = re.sub(pat, "", title, flags=re.I).strip()
        if cleaned:
            title = cleaned

    # Clean whitespace and trailing symbols
    title = title.strip(" -_+=~()[]{}【】（）")
    return title if title else folder_name


def extract_rj_code(text: str) -> Optional[str]:
    """Extracts RJ/VJ/BJ code from folder name or file names."""
    m = re.search(r"([RVB]J\d{6,8})", text, re.I)
    if m:
        return m.group(1).upper()
    return None


def fast_inspect_folder(folder_path: str, max_depth: int = 2) -> Tuple[List[str], str, int, float, float, bool]:
    """
    Recursively inspects folder up to max_depth to find executables, engine, size, mtime, creation ctime, and translation presence.
    """
    exes: List[str] = []
    engine = "Unknown"
    total_size = 0
    latest_mtime = 0.0
    created_ctime = 0.0
    has_trs = False

    try:
        root_stat = os.stat(folder_path)
        created_ctime = root_stat.st_ctime
        latest_mtime = root_stat.st_mtime
    except Exception:
        pass

    def scan_level(p: str, depth: int):
        nonlocal engine, total_size, latest_mtime, has_trs
        try:
            with os.scandir(p) as it:
                for entry in it:
                    try:
                        st = entry.stat()
                        total_size += st.st_size
                        if st.st_mtime > latest_mtime:
                            latest_mtime = st.st_mtime

                        if entry.is_file():
                            name_low = entry.name.lower()
                            if name_low in ("翻译文件.json", "translation.json", "trs.json", "与工具一同启动.bat", "lastloadedtrsfile", "startwithtool.bat"):
                                has_trs = True
                            elif depth <= 1 and name_low.endswith(".json") and not has_trs:
                                if is_valid_translation_json(entry.path):
                                    has_trs = True

                            if name_low.endswith(".exe"):
                                if not any(pat.search(entry.name) for pat in IGNORE_EXE_PATTERNS):
                                    exes.append(entry.path)
                            elif name_low.endswith(".xp3") or name_low.endswith(".kagex"):
                                if engine == "Unknown":
                                    engine = "Kirikiri (吉里吉里)"
                            elif name_low in ("package.json", "rpg_core.js", "rmmz_core.js"):
                                if engine == "Unknown":
                                    engine = "RPG Maker MV/MZ"
                            elif name_low.endswith(".rgss3a"):
                                engine = "RPG Maker VX Ace"
                            elif name_low.endswith(".rgss2a"):
                                engine = "RPG Maker VX"
                            elif name_low.endswith(".rgssad"):
                                engine = "RPG Maker XP"
                            elif name_low.endswith(".wolf"):
                                engine = "Wolf RPG"
                            elif name_low in ("unityplayer.dll", "gameassembly.dll"):
                                engine = "Unity"
                            elif name_low.endswith(".pck"):
                                engine = "Godot"
                            elif name_low in ("siglusengine.exe", "reallive.exe"):
                                engine = "Siglus / Key"
                        elif entry.is_dir():
                            dname_low = entry.name.lower()
                            if dname_low == "data_original_backup":
                                has_trs = True
                            if depth < max_depth and dname_low not in SKIP_WALK_DIRS:
                                if dname_low == "www" and engine == "Unknown":
                                    engine = "RPG Maker MV/MZ"
                                elif dname_low.endswith("_data") and engine == "Unknown":
                                    engine = "Unity"
                                elif dname_low in ("renpy", "game") and engine == "Unknown":
                                    engine = "Ren'Py"
                                elif dname_low == "engine" and engine == "Unknown":
                                    engine = "Unreal Engine"
                                elif dname_low == "gamedata" and engine == "Unknown":
                                    engine = "Siglus / Key"
                                scan_level(entry.path, depth + 1)
                    except Exception:
                        pass
        except Exception:
            pass

    scan_level(folder_path, 0)
    if engine == "Unknown" and exes:
        engine = "Native PC"

    return exes, engine, total_size, latest_mtime, created_ctime, has_trs


def choose_best_executable(root_path: str, exes: List[str]) -> Optional[str]:
    if not exes:
        return None
    root_stem = Path(root_path).name.lower()

    # 1. Match folder name
    for exe in exes:
        stem = Path(exe).stem.lower()
        if len(stem) >= 2 and (stem in root_stem or root_stem in stem):
            return exe

    # 2. Match Game.exe, Start.exe
    for exe in exes:
        name = Path(exe).name.lower()
        if name in ("game.exe", "gamepro.exe", "start.exe", "play.exe", "launch.exe"):
            return exe

    # 3. Choose the shortest depth relative to root
    exes_sorted = sorted(exes, key=lambda x: (len(Path(x).relative_to(root_path).parts), -os.path.getsize(x) if os.path.exists(x) else 0))
    return exes_sorted[0]


def get_excluded_scan_paths() -> Set[str]:
    """Returns normalized lowercase paths that must never be scanned as game folders."""
    cfg = load_config()
    excluded: Set[str] = set()
    for key in ("archive_directory", "save_backup_directory", "mtool_directory"):
        val = cfg.get(key)
        if val and isinstance(val, str) and val.strip():
            excluded.add(os.path.normcase(os.path.normpath(val.strip())))
    return excluded


def scan_directory(
    dir_path_str: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[Dict[str, Any]]:
    """Scans a root directory (e.g. E:\\ACG) and returns parsed game items."""
    results: List[Dict[str, Any]] = []
    root = Path(dir_path_str)
    if not root.exists() or not root.is_dir():
        return results

    excluded_paths = get_excluded_scan_paths()

    try:
        with os.scandir(str(root)) as it:
            entries = []
            for e in it:
                if not e.is_dir():
                    continue
                if e.name.startswith(".") or e.name.startswith("_"):
                    continue
                norm_p = os.path.normcase(os.path.normpath(e.path))
                if norm_p in excluded_paths:
                    continue
                entries.append(e)
    except Exception as e:
        print(f"Error reading directory {dir_path_str}: {e}")
        return results

    entries.sort(key=lambda x: x.name)
    total_entries = len(entries)

    for idx, entry in enumerate(entries):
        folder_name = entry.name
        folder_path = entry.path
        if progress_callback:
            try:
                progress_callback(idx + 1, total_entries, folder_name)
            except Exception:
                pass

        is_tool = is_tool_folder(folder_name)
        rj_code = extract_rj_code(folder_name)
        clean_title = clean_title_from_folder(folder_name)

        exes, engine_type, size_bytes, latest_mtime, created_ctime, has_trs = fast_inspect_folder(folder_path, max_depth=2)
        best_exe = choose_best_executable(folder_path, exes)

        if not rj_code and best_exe:
            rj_code = extract_rj_code(Path(best_exe).name)

        mtime_str = datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M") if latest_mtime > 0 else ""
        ctime_str = datetime.fromtimestamp(created_ctime).strftime("%Y-%m-%d %H:%M") if created_ctime > 0 else ""

        game_item = {
            "folder_name": folder_name,
            "folder_path": folder_path,
            "clean_title": clean_title,
            "display_title": clean_title,
            "rj_code": rj_code or "",
            "engine_type": engine_type,
            "executable_path": best_exe or "",
            "folder_size_bytes": size_bytes,
            "folder_size_str": format_size(size_bytes),
            "folder_modified_at": mtime_str,
            "downloaded_at": ctime_str,
            "is_tool": 1 if is_tool else 0,
            "has_translation": 1 if has_trs else 0,
            "play_status": "unplayed",
        }
        results.append(game_item)

    return results
