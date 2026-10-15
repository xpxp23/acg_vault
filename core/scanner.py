import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

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
]

SKIP_WALK_DIRS = {
    "node_modules", ".git", "audio", "sound", "voice", "bgm", "se", "bgs",
    "img", "image", "images", "picture", "pictures", "cg", "movie", "movies", "video",
    "locales", "swiftshader", "monobleedingedge", "streamingassets", "plugins"
}

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
    title = folder_name
    
    # Remove leading tags like 【PC官中SLG】, [NitroPlus], [RJxxxxxx]
    title = re.sub(r"^\[[^\]]+\]", "", title)
    title = re.sub(r"^【[^】]+】", "", title)
    title = re.sub(r"^\([^\)]+\)", "", title)
    
    # Remove inner layer tag (内层)
    title = re.sub(r"\(内层\)", "", title, flags=re.I)
    title = re.sub(r"\(ڲ\)", "", title)
    
    # Remove trailing common words
    trailing_patterns = [
        r"电脑$",
        r"製品版.*$",
        r"製品版$",
        r"汉化(硬盘)?版.*$",
        r"精翻汉化版.*$",
        r"官中无修版.*$",
        r"官方中文.*$",
        r"中文动态.*$",
        r"步兵版.*$",
        r"繁中版.*$",
        r"Steam.*$",
        r"Ver\.?\s*\d+(\.\d+)*.*$",
        r"v\d+(\.\d+)*.*$",
        r"V\d+(\.\d+)*.*$",
        r"_\d{6,}$",
        r"zh-CN$",
        r"zh-TW$",
        r"CHS$",
        r"Chs$"
    ]
    for pat in trailing_patterns:
        title = re.sub(pat, "", title, flags=re.I).strip()
    
    # Clean whitespace and trailing symbols
    title = title.strip(" -_+=~()[]{}【】")
    return title if title else folder_name

def extract_rj_code(text: str) -> Optional[str]:
    """Extracts RJ/VJ/BJ code from folder name or file names."""
    m = re.search(r"\b([R|V|B]J\d{6,8})\b", text, re.I)
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
                            if name_low in ("翻译文件.json", "与工具一同启动.bat", "lastloadedtrsfile", "startwithtool.bat"):
                                has_trs = True
                            elif name_low.endswith(".json") and name_low not in ("package.json", "packagev.json") and "config" not in name_low:
                                has_trs = True

                            if name_low.endswith(".exe"):
                                if not any(pat.search(entry.name) for pat in IGNORE_EXE_PATTERNS):
                                    exes.append(entry.path)
                            elif name_low.endswith(".xp3") or name_low.endswith(".kagex"):
                                if engine == "Unknown":
                                    engine = "Kirikiri (吉里吉里)"
                            elif name_low in ("package.json", "rpg_core.js"):
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
                        elif entry.is_dir() and depth < max_depth:
                            dname_low = entry.name.lower()
                            if dname_low not in SKIP_WALK_DIRS:
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
        if stem in root_stem or root_stem in stem:
            return exe
            
    # 2. Match Game.exe, Start.exe
    for exe in exes:
        name = Path(exe).name.lower()
        if name in ("game.exe", "start.exe", "play.exe", "launch.exe"):
            return exe

    # 3. Choose the shortest depth relative to root
    exes_sorted = sorted(exes, key=lambda x: (len(Path(x).relative_to(root_path).parts), -os.path.getsize(x) if os.path.exists(x) else 0))
    return exes_sorted[0]

def scan_directory(dir_path_str: str) -> List[Dict[str, Any]]:
    """Scans a root directory (e.g. E:\\ACG) and returns parsed game items."""
    results: List[Dict[str, Any]] = []
    root = Path(dir_path_str)
    if not root.exists() or not root.is_dir():
        return results

    try:
        with os.scandir(str(root)) as it:
            entries = [e for e in it if e.is_dir()]
    except Exception as e:
        print(f"Error reading directory {dir_path_str}: {e}")
        return results

    entries.sort(key=lambda x: x.name)

    for entry in entries:
        folder_name = entry.name
        folder_path = entry.path
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
