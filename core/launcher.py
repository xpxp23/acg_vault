import os
import re
import time
import zipfile
import subprocess
import threading
import ctypes
from ctypes import wintypes
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from db.database import get_game_by_id, record_game_launch
from core.scanner import fast_inspect_folder, choose_best_executable, is_valid_translation_json
from config import load_config

# ---------------------------------------------------------
# Win32 Constants & ShellExecuteEx API
# ---------------------------------------------------------
SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
SW_SHOW = 5
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7

class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]

# ---------------------------------------------------------
# Win32 Toolhelp32 Process Scanning
# ---------------------------------------------------------
TH32CS_SNAPPROCESS = 0x00000002

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260)
    ]

def get_process_image_path(pid: int) -> str:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    buf = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(len(buf))
    res = ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    ctypes.windll.kernel32.CloseHandle(h)
    return buf.value if res else ""

def find_game_pid_in_folder(folder_path: str, exe_filename: Optional[str] = None) -> Optional[int]:
    """Finds the PID of a running game process inside a specific folder."""
    norm_folder = os.path.normpath(folder_path).lower()
    hSnap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if hSnap == -1:
        return None
    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    candidates = []
    if ctypes.windll.kernel32.Process32FirstW(hSnap, ctypes.byref(pe)):
        while True:
            pid = pe.th32ProcessID
            sz_name = pe.szExeFile
            if exe_filename is None or sz_name.lower() == exe_filename.lower():
                path = get_process_image_path(pid)
                if path and os.path.normpath(path).lower().startswith(norm_folder):
                    candidates.append((pid, sz_name))
            if not ctypes.windll.kernel32.Process32NextW(hSnap, ctypes.byref(pe)):
                break
    ctypes.windll.kernel32.CloseHandle(hSnap)
    if candidates:
        return candidates[0][0]
    return None

def shell_launch(exe_path: str, parameters: Optional[str] = None, working_dir: Optional[str] = None, show_cmd: int = SW_SHOWNORMAL):
    """Launches an executable via Windows Shell to guarantee interactive desktop presentation and visible window."""
    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS
    sei.hwnd = None
    sei.lpVerb = "open"
    sei.lpFile = str(exe_path)
    sei.lpParameters = str(parameters) if parameters else None
    sei.lpDirectory = str(working_dir) if working_dir else None
    sei.nShow = show_cmd

    success = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
    pid = None
    hProcess = None
    if success and sei.hProcess:
        hProcess = sei.hProcess
        pid = ctypes.windll.kernel32.GetProcessId(hProcess)
    return bool(success), pid, hProcess

# Map of running game processes: game_id -> {pid, start_time, exe, mode}
RUNNING_GAMES: Dict[int, Dict[str, Any]] = {}

def monitor_game_pid(game_id: int, target_pid: Optional[int], hProcess: Optional[Any], start_time: float, working_dir: Optional[str] = None, exe_name: Optional[str] = None):
    """Monitors the real game process until it closes and records play session duration."""
    try:
        SYNCHRONIZE = 0x00100000
        INFINITE = 0xFFFFFFFF

        if hProcess:
            ctypes.windll.kernel32.WaitForSingleObject(hProcess, INFINITE)
            ctypes.windll.kernel32.CloseHandle(hProcess)
        elif target_pid:
            h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, target_pid)
            if h:
                ctypes.windll.kernel32.WaitForSingleObject(h, INFINITE)
                ctypes.windll.kernel32.CloseHandle(h)
            else:
                while True:
                    time.sleep(2.0)
                    active_pid = find_game_pid_in_folder(working_dir, exe_name)
                    if not active_pid:
                        break
        else:
            time.sleep(2.0)
            while True:
                active_pid = find_game_pid_in_folder(working_dir, exe_name)
                if not active_pid:
                    break
                time.sleep(2.0)
    except Exception as e:
        print(f"[MONITOR ERROR] {e}")
    finally:
        duration = int(time.time() - start_time)
        if duration > 10:
            record_game_launch(game_id, duration_seconds=duration)
        if game_id in RUNNING_GAMES:
            del RUNNING_GAMES[game_id]

def resolve_leproc_path() -> Optional[str]:
    """Resolves Locale Emulator (LEProc.exe) path from config or common installation locations."""
    cfg = load_config()
    custom_le = (cfg.get("leproc_path") or "").strip()
    if custom_le and os.path.exists(custom_le):
        return custom_le

    candidates = [
        r"E:\ACG\Locale.Emulator\LEProc.exe",
        r"E:\ACG\Locale_Emulator\LEProc.exe",
        r"E:\ACG\转区工具\LEProc.exe",
        r"C:\Locale.Emulator\LEProc.exe",
        r"D:\Locale.Emulator\LEProc.exe",
    ]
    for gdir in cfg.get("game_directories", []):
        if gdir and os.path.exists(gdir):
            candidates.append(os.path.join(gdir, "Locale.Emulator", "LEProc.exe"))
            candidates.append(os.path.join(gdir, "LEProc.exe"))

    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def launch_game(game_id: int, mode: Optional[str] = None) -> Dict[str, Any]:
    """Launches the primary executable for a game with normal interactive window and tracks play session."""
    if mode == "mtool":
        return launch_game_with_mtool(game_id)
    elif mode == "le":
        return launch_game_with_le(game_id)
    elif mode is None:
        try:
            mstatus = get_game_mtool_status(game_id)
            if mstatus.get("supported") and mstatus.get("launch_mode_default") == "mtool":
                return launch_game_with_mtool(game_id)
        except Exception:
            pass

    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏记录不存在"}

    exe_path = game.get("executable_path")
    folder_path = game.get("folder_path")

    if not exe_path or not os.path.exists(exe_path):
        if folder_path and os.path.exists(folder_path):
            exes, *rest = fast_inspect_folder(folder_path, max_depth=2)
            exe_path = choose_best_executable(folder_path, exes)

    if not exe_path or not os.path.exists(exe_path):
        if folder_path and os.path.exists(folder_path):
            os.startfile(folder_path)
            return {"success": True, "message": "未找到主程序，已为您打开游戏目录"}
        return {"success": False, "message": "游戏主程序与目录均不存在"}

    working_dir = os.path.dirname(os.path.abspath(exe_path))
    exe_name = Path(exe_path).name

    try:
        success, pid, hProcess = shell_launch(exe_path, working_dir=working_dir, show_cmd=SW_SHOWNORMAL)
        if not success:
            os.startfile(exe_path)
            time.sleep(1.0)
            pid = find_game_pid_in_folder(working_dir, exe_name)
            hProcess = None

        start_time = time.time()
        record_game_launch(game_id, duration_seconds=0)

        RUNNING_GAMES[game_id] = {
            "pid": pid,
            "start_time": start_time,
            "exe": exe_name,
            "mode": "native"
        }

        t = threading.Thread(
            target=monitor_game_pid,
            args=(game_id, pid, hProcess, start_time, working_dir, exe_name),
            daemon=True
        )
        t.start()

        return {
            "success": True,
            "pid": pid,
            "message": f"成功启动: {exe_name}"
        }
    except Exception as e:
        return {"success": False, "message": f"启动失败: {str(e)}"}

def launch_game_with_le(game_id: int) -> Dict[str, Any]:
    """Launches game via Locale Emulator (LEProc.exe) for Japanese Shift-JIS locale emulation."""
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏记录不存在"}

    le_exe = resolve_leproc_path()
    if not le_exe:
        return {
            "success": False,
            "message": "未找到 Locale Emulator (LEProc.exe)，请在【系统设置】中配置 LEProc.exe 路径"
        }

    folder_path = game.get("folder_path")
    exe_path = game.get("executable_path")
    if not exe_path or not os.path.exists(exe_path):
        if folder_path and os.path.exists(folder_path):
            exes, *rest = fast_inspect_folder(folder_path, max_depth=2)
            exe_path = choose_best_executable(folder_path, exes)

    if not exe_path or not os.path.exists(exe_path):
        return {"success": False, "message": "未找到游戏主程序"}

    working_dir = os.path.dirname(os.path.abspath(exe_path))
    exe_name = Path(exe_path).name

    try:
        success, _, _ = shell_launch(
            exe_path=le_exe,
            parameters=f'-run "{exe_path}"',
            working_dir=working_dir,
            show_cmd=SW_SHOWNORMAL
        )
        if not success:
            subprocess.Popen([le_exe, "-run", exe_path], cwd=working_dir)

        time.sleep(1.0)
        real_pid = find_game_pid_in_folder(working_dir, exe_name)
        start_time = time.time()
        record_game_launch(game_id, duration_seconds=0)

        RUNNING_GAMES[game_id] = {
            "pid": real_pid,
            "start_time": start_time,
            "exe": exe_name,
            "mode": "le"
        }

        t = threading.Thread(
            target=monitor_game_pid,
            args=(game_id, real_pid, None, start_time, working_dir, exe_name),
            daemon=True
        )
        t.start()

        return {
            "success": True,
            "pid": real_pid,
            "message": f"已通过 Locale Emulator 转区启动: {exe_name}"
        }
    except Exception as e:
        return {"success": False, "message": f"LE 转区启动失败: {str(e)}"}

def open_game_folder(folder_path: str) -> bool:
    if os.path.exists(folder_path):
        try:
            os.startfile(folder_path)
            return True
        except Exception:
            subprocess.Popen(["explorer.exe", folder_path])
            return True
    return False

def reveal_in_explorer(file_or_dir_path: str) -> bool:
    if os.path.exists(file_or_dir_path):
        try:
            subprocess.Popen(["explorer.exe", f'/select,"{file_or_dir_path}"'])
            return True
        except Exception:
            return open_game_folder(file_or_dir_path)
    return False

def get_game_mtool_status(game_id: int) -> Dict[str, Any]:
    """Inspects game folder to determine if MTool translation or Locale Emulator is available/supported."""
    game = get_game_by_id(game_id)
    if not game:
        return {"supported": False, "message": "游戏不存在"}

    folder_path = game.get("folder_path")
    if not folder_path or not os.path.exists(folder_path):
        return {"supported": False, "message": "游戏目录不存在"}

    cfg = load_config()
    mtool_dir = cfg.get("mtool_directory", r"E:\ACG\MTool")
    inject_exe = Path(mtool_dir) / "Tool" / "loaders" / "inject.exe"
    mtool_installed = os.path.exists(mtool_dir) and inject_exe.exists()
    leproc_path = resolve_leproc_path()

    folder = Path(folder_path)

    # Check for MTool bat files
    has_bat = False
    bat_file = None
    for cand in ["与工具一同启动.bat", "StartWithTool.bat"]:
        if (folder / cand).exists():
            has_bat = True
            bat_file = str(folder / cand)
            break

    # Check for validated translation JSON
    has_trs = False
    trs_file = None
    for cand in ["翻译文件.json", "translation.json", "trs.json"]:
        if (folder / cand).exists():
            has_trs = True
            trs_file = str(folder / cand)
            break

    if not has_trs and (folder / "lastLoadedTrsFile").exists():
        try:
            with open(folder / "lastLoadedTrsFile", "r", encoding="utf-8-sig") as f:
                ref = f.read().strip()
                if ref and (folder / ref).exists() and is_valid_translation_json(str(folder / ref)):
                    has_trs = True
                    trs_file = str(folder / ref)
        except Exception:
            pass

    if not has_trs:
        try:
            for f in os.listdir(folder):
                full_p = folder / f
                if full_p.is_file() and f.lower().endswith(".json") and is_valid_translation_json(str(full_p)):
                    has_trs = True
                    trs_file = str(full_p)
                    break
        except Exception:
            pass

    engine_type = game.get("engine_type", "") or ""
    is_mtool_engine = False
    hook_dll_name = "mzHook.dll"
    if "Wolf" in engine_type:
        is_mtool_engine = True
        hook_dll_name = "wolfHook.dll"
    elif any(k in engine_type for k in ["VX", "XP", "RGSS"]):
        is_mtool_engine = True
        hook_dll_name = "RGSSHook.dll"
    elif "MV" in engine_type or "MZ" in engine_type or "RPG Maker" in engine_type:
        is_mtool_engine = True
        hook_dll_name = "mzHook.dll"

    # Check if translation has already been baked into the game files
    is_baked = False
    if (
        (folder / "data_original_backup").exists()
        or (folder / "www" / "data_original_backup").exists()
        or (folder / "index.html.original_bak").exists()
    ):
        is_baked = True

    supported = mtool_installed and is_mtool_engine
    has_translation = bool(has_bat or has_trs or is_baked)

    if is_baked:
        launch_mode_default = "native"
    elif supported and (has_bat or has_trs):
        launch_mode_default = "mtool"
    else:
        launch_mode_default = "native"

    can_bake_patch = bool(has_trs and not is_baked and ("MV" in engine_type or "MZ" in engine_type or "RPG Maker MV/MZ" in engine_type))

    return {
        "supported": supported,
        "mtool_installed": mtool_installed,
        "le_installed": bool(leproc_path),
        "leproc_path": leproc_path or "",
        "is_mtool_engine": is_mtool_engine,
        "mtool_dir": str(mtool_dir),
        "has_bat": has_bat,
        "bat_file": bat_file,
        "has_trs": has_trs,
        "trs_file": trs_file,
        "has_translation": has_translation,
        "is_baked": is_baked,
        "launch_mode_default": launch_mode_default,
        "can_bake_patch": can_bake_patch,
        "engine_type": engine_type,
        "hook_dll": hook_dll_name
    }

def launch_game_with_mtool(game_id: int) -> Dict[str, Any]:
    """Launches game with MTool injection attached and normal visible window."""
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏记录不存在"}

    status = get_game_mtool_status(game_id)
    if not status.get("mtool_installed"):
        return {
            "success": False,
            "message": f"未检测到 MTool 安装目录，请在设置中配置有效路径 (当前: {status.get('mtool_dir')})"
        }

    folder_path = game.get("folder_path")
    exe_path = game.get("executable_path")
    if not exe_path or not os.path.exists(exe_path):
        if folder_path and os.path.exists(folder_path):
            exes, *rest = fast_inspect_folder(folder_path, max_depth=2)
            exe_path = choose_best_executable(folder_path, exes)

    if not exe_path or not os.path.exists(exe_path):
        return {"success": False, "message": "未找到游戏主程序"}

    working_dir = os.path.dirname(os.path.abspath(exe_path))
    exe_name = Path(exe_path).name
    mtool_dir = Path(status["mtool_dir"])
    inject_exe = mtool_dir / "Tool" / "loaders" / "inject.exe"
    hook_dll = mtool_dir / "Tool" / "loaders" / status["hook_dll"]
    nw_exe = mtool_dir / "Tool" / "nw.exe"
    tool_dir = mtool_dir / "Tool"

    if status.get("trs_file") and os.path.exists(status["trs_file"]):
        trs_name = os.path.basename(status["trs_file"])
        last_trs = os.path.join(working_dir, "lastLoadedTrsFile")
        try:
            with open(last_trs, "w", encoding="utf-8") as f:
                f.write(trs_name)
        except Exception:
            pass

    try:
        if inject_exe.exists() and hook_dll.exists():
            success, _, _ = shell_launch(
                exe_path=str(inject_exe),
                parameters=f'"{exe_path}" "{hook_dll}"',
                working_dir=working_dir,
                show_cmd=SW_SHOWNORMAL
            )
            if not success:
                subprocess.run(
                    f'cmd.exe /c start "" "{inject_exe}" "{exe_path}" "{hook_dll}"',
                    cwd=working_dir,
                    shell=True
                )
        elif status.get("has_bat") and status.get("bat_file"):
            os.startfile(status["bat_file"])
        else:
            return {"success": False, "message": "缺少 MTool inject.exe 或 hook DLL，无法注入"}

        if nw_exe.exists():
            try:
                shell_launch(
                    exe_path=str(nw_exe),
                    parameters=f'"{tool_dir}"',
                    working_dir=str(tool_dir),
                    show_cmd=SW_SHOWMINNOACTIVE
                )
            except Exception:
                pass

        time.sleep(1.0)
        real_game_pid = find_game_pid_in_folder(working_dir, exe_name)

        start_time = time.time()
        record_game_launch(game_id, duration_seconds=0)

        RUNNING_GAMES[game_id] = {
            "pid": real_game_pid,
            "start_time": start_time,
            "exe": exe_name,
            "mode": "mtool"
        }

        t = threading.Thread(
            target=monitor_game_pid,
            args=(game_id, real_game_pid, None, start_time, working_dir, exe_name),
            daemon=True
        )
        t.start()

        mode_name = "汉化" if status.get("has_translation") else "辅助"
        return {
            "success": True,
            "pid": real_game_pid,
            "message": f"成功以 MTool {mode_name}模式启动: {exe_name}"
        }
    except Exception as e:
        return {"success": False, "message": f"MTool 启动失败: {str(e)}"}

# ---------------------------------------------------------
# Save Data Detection & Snapshot Backup Manager
# ---------------------------------------------------------
SAVE_DIR_CANDIDATES = [
    "save",
    os.path.join("www", "save"),
    "Save",
    "SaveData",
    "savedata",
    "Saves",
    "saves",
    os.path.join("game", "saves"),
    os.path.join("UserData", "save"),
    os.path.join("Data", "Save"),
    os.path.join("contents", "save"),
    os.path.join("contents", "www", "save"),
]

SAVE_FILE_EXTENSIONS = (
    ".rpgsave", ".rmmzsave", ".rvdata2", ".rvdata", ".rxdata",
    ".sav", ".save", ".lsd", ".ksd", ".dat"
)

def find_game_save_dir(folder_path: str) -> Optional[str]:
    if not folder_path or not os.path.exists(folder_path):
        return None
    root = Path(folder_path)
    for rel in SAVE_DIR_CANDIDATES:
        cand = root / rel
        if cand.exists() and cand.is_dir():
            return str(cand)
    # Check loose save files in root
    try:
        for f in os.listdir(root):
            low = f.lower()
            if low.startswith("save") and low.endswith(SAVE_FILE_EXTENSIONS):
                return str(root)
    except Exception:
        pass
    return None

def get_game_save_status(game_id: int) -> Dict[str, Any]:
    """Inspects local game save folder and existing backup snapshots."""
    game = get_game_by_id(game_id)
    if not game:
        return {"has_save_dir": False, "save_count": 0, "backups": []}

    folder_path = game.get("folder_path", "")
    save_dir = find_game_save_dir(folder_path)
    save_files: List[str] = []
    latest_save_time = ""

    if save_dir and os.path.exists(save_dir):
        latest_ts = 0.0
        try:
            for root, _, files in os.walk(save_dir):
                # If save_dir is the game root itself, only check top-level save files
                if os.path.normpath(root) != os.path.normpath(save_dir) and os.path.normpath(save_dir) == os.path.normpath(folder_path):
                    continue
                for fn in files:
                    low = fn.lower()
                    if low.endswith(SAVE_FILE_EXTENSIONS) or "save" in low or "file" in low or "global" in low:
                        fp = os.path.join(root, fn)
                        save_files.append(fp)
                        st = os.stat(fp)
                        if st.st_mtime > latest_ts:
                            latest_ts = st.st_mtime
        except Exception:
            pass
        if latest_ts > 0:
            latest_save_time = datetime.fromtimestamp(latest_ts).strftime("%Y-%m-%d %H:%M")

    # Find backups in save_backup_directory
    cfg = load_config()
    backup_root = Path(cfg.get("save_backup_directory", r"E:\ACG\_Save_Backups"))
    backups = []
    if backup_root.exists():
        prefix = f"game_{game_id}_"
        for bf in sorted(backup_root.glob(f"{prefix}*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
            st = bf.stat()
            backups.append({
                "filename": bf.name,
                "path": str(bf),
                "size_kb": round(st.st_size / 1024, 1),
                "created_at": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })

    return {
        "has_save_dir": bool(save_dir),
        "save_dir": save_dir or "",
        "save_count": len(save_files),
        "latest_save_at": latest_save_time,
        "backups": backups[:10]
    }

def open_game_save_folder(game_id: int) -> Dict[str, Any]:
    status = get_game_save_status(game_id)
    if status.get("has_save_dir") and status.get("save_dir"):
        open_game_folder(status["save_dir"])
        return {"success": True, "message": "已打开游戏存档目录"}
    game = get_game_by_id(game_id)
    if game and game.get("folder_path") and os.path.exists(game["folder_path"]):
        open_game_folder(game["folder_path"])
        return {"success": True, "message": "未检测到独立 save 文件夹，已为您打开游戏根目录"}
    return {"success": False, "message": "游戏目录不存在"}

def backup_game_saves(game_id: int) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    status = get_game_save_status(game_id)
    if not status.get("has_save_dir") or not status.get("save_dir"):
        return {"success": False, "message": "未在该游戏目录内检测到存档文件夹"}

    save_dir = Path(status["save_dir"])
    cfg = load_config()
    backup_root = Path(cfg.get("save_backup_directory", r"E:\ACG\_Save_Backups"))
    backup_root.mkdir(parents=True, exist_ok=True)

    safe_title = re.sub(r'[\\/*?:"<>|\s]+', "_", (game.get("clean_title") or game.get("folder_name") or "game"))[:30]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"game_{game_id}_{safe_title}_{ts}.zip"
    zip_path = backup_root / zip_name

    try:
        file_count = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(save_dir):
                if os.path.normpath(root) != os.path.normpath(save_dir) and os.path.normpath(save_dir) == os.path.normpath(game["folder_path"]):
                    continue
                for fn in files:
                    fp = Path(root) / fn
                    rel_p = fp.relative_to(save_dir)
                    zf.write(fp, arcname=str(rel_p))
                    file_count += 1
        if file_count == 0:
            if zip_path.exists():
                zip_path.unlink()
            return {"success": False, "message": "存档目录为空，暂无可备份的存档文件"}
        return {
            "success": True,
            "zip_path": str(zip_path),
            "file_count": file_count,
            "message": f"已成功备份 {file_count} 个存档文件至 {zip_name}",
            "save_status": get_game_save_status(game_id)
        }
    except Exception as e:
        return {"success": False, "message": f"存档备份失败: {str(e)}"}
