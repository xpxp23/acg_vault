import os
import sys
import re
import time
import shutil
import zipfile
import subprocess
import threading
import ctypes
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
import httpx

from db.database import get_game_by_id, record_game_launch, update_game_user_state
from core.scanner import fast_inspect_folder, choose_best_executable, is_valid_translation_json, IGNORE_EXE_PATTERNS
from config import load_config

IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------
# Win32 Constants, Explicit 64-bit Signatures & ShellExecuteEx
# ---------------------------------------------------------
SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
SW_SHOW = 5
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7
TH32CS_SNAPPROCESS = 0x00000002
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102

HOTKEY_VK_MAP = {
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
    "PRTSC": 0x2C,
    "INS": 0x2D
}

if IS_WINDOWS:
    from ctypes import wintypes

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

    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
        kernel32.GetProcessId.restype = wintypes.DWORD
        ctypes.windll.shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
        ctypes.windll.shell32.ShellExecuteExW.restype = wintypes.BOOL
    except Exception:
        pass
else:
    INVALID_HANDLE_VALUE = -1


def is_subpath(child_path: str, parent_path: str) -> bool:
    """
    Strictly verifies whether child_path is equal to or inside parent_path.
    Prevents sibling prefix false positives (e.g. 'E:\\ACG\\Game2' matching 'E:\\ACG\\Game').
    """
    if not child_path or not parent_path:
        return False
    try:
        c = Path(os.path.normcase(os.path.abspath(os.path.normpath(child_path))))
        p = Path(os.path.normcase(os.path.abspath(os.path.normpath(parent_path))))
        return c == p or c.is_relative_to(p)
    except Exception:
        c_str = os.path.normcase(os.path.abspath(os.path.normpath(child_path))).rstrip("\\/") + os.sep
        p_str = os.path.normcase(os.path.abspath(os.path.normpath(parent_path))).rstrip("\\/") + os.sep
        return c_str.startswith(p_str)


def close_win32_handle(h: Any):
    if IS_WINDOWS and h and h != INVALID_HANDLE_VALUE:
        try:
            ctypes.windll.kernel32.CloseHandle(h)
        except Exception:
            pass


def is_pid_alive(pid: Optional[int]) -> bool:
    if not pid or pid <= 0:
        return False
    if not IS_WINDOWS:
        try:
            os.kill(int(pid), 0)
            return True
        except Exception:
            return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h or h == INVALID_HANDLE_VALUE:
        return False
    try:
        exit_code = wintypes.DWORD()
        if ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code)):
            return exit_code.value == STILL_ACTIVE
        return True
    finally:
        close_win32_handle(h)


def get_process_image_path(pid: int) -> str:
    if not IS_WINDOWS:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h or h == INVALID_HANDLE_VALUE:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        res = ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        return buf.value if res else ""
    finally:
        close_win32_handle(h)


def find_game_pid_in_folder(folder_path: str, exe_filename: Optional[str] = None) -> Optional[int]:
    """Finds the PID of a running game process strictly inside a specific folder."""
    if not IS_WINDOWS or not folder_path:
        return None
    hSnap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not hSnap or hSnap == INVALID_HANDLE_VALUE:
        return None
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        exact_candidates = []
        folder_candidates = []
        if ctypes.windll.kernel32.Process32FirstW(hSnap, ctypes.byref(pe)):
            while True:
                pid = pe.th32ProcessID
                sz_name = pe.szExeFile
                path = get_process_image_path(pid)
                if path and is_subpath(path, folder_path):
                    if exe_filename and sz_name.lower() == exe_filename.lower():
                        exact_candidates.append(pid)
                    elif not any(pat.search(sz_name) for pat in IGNORE_EXE_PATTERNS):
                        folder_candidates.append(pid)
                if not ctypes.windll.kernel32.Process32NextW(hSnap, ctypes.byref(pe)):
                    break
        if exact_candidates:
            return exact_candidates[0]
        if folder_candidates:
            return folder_candidates[0]
        return None
    finally:
        close_win32_handle(hSnap)


def shell_launch(exe_path: str, parameters: Optional[str] = None, working_dir: Optional[str] = None, show_cmd: int = SW_SHOWNORMAL):
    """Launches an executable via Windows Shell to guarantee interactive desktop presentation and visible window."""
    if not IS_WINDOWS:
        return False, None, None
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


# Map of running game processes: game_id -> {pid, start_time, exe, mode, folder_path}
RUNNING_GAMES: Dict[int, Dict[str, Any]] = {}
RUNNING_LOCK = threading.Lock()
LAST_ACTIVE_GAME_ID: Optional[int] = None


def set_last_active_game_id(game_id: int):
    global LAST_ACTIVE_GAME_ID
    if game_id:
        LAST_ACTIVE_GAME_ID = int(game_id)


def get_last_active_game_id() -> Optional[int]:
    running = get_running_games_info()
    if running:
        return next(iter(running.keys()))
    return LAST_ACTIVE_GAME_ID


def get_running_games_info() -> Dict[int, Dict[str, Any]]:
    """
    Returns currently active running games with live elapsed seconds in O(1) memory time.
    Never performs expensive Win32 process tree snapshots while holding RUNNING_LOCK;
    process liveness and child PID handoffs are maintained asynchronously by monitor_game_pid.
    """
    now = time.time()
    active: Dict[int, Dict[str, Any]] = {}
    with RUNNING_LOCK:
        for gid, info in RUNNING_GAMES.items():
            elapsed = int(now - info.get("start_time", now))
            active[gid] = {
                "game_id": gid,
                "pid": info.get("pid"),
                "exe": info.get("exe", ""),
                "mode": info.get("mode", "native"),
                "elapsed_seconds": max(0, elapsed)
            }
    return active


def _poll_screenshot_hotkey_if_needed(game_id: int, active_pid: Optional[int], search_root: Optional[str], last_shot_ts: float) -> float:
    """Checks if the configured in-game screenshot hotkey (e.g. F12) is pressed while the game window is focused."""
    if not IS_WINDOWS:
        return last_shot_ts
    now = time.time()
    if now - last_shot_ts < 1.2:
        return last_shot_ts
    try:
        cfg = load_config()
        if not cfg.get("enable_ingame_screenshot", True):
            return last_shot_ts
        hk = (cfg.get("screenshot_hotkey") or "F12").strip().upper()
        vk = HOTKEY_VK_MAP.get(hk, 0x7B)
        state = ctypes.windll.user32.GetAsyncKeyState(vk)
        if state & 0x8000:
            from core.gallery_cg import is_pid_foreground, capture_game_window_screenshot
            if is_pid_foreground(active_pid, search_root):
                capture_game_window_screenshot(game_id, pid=active_pid)
                return time.time()
    except Exception:
        pass
    return last_shot_ts


def _wait_handle_with_hotkey_poll(hProc: Any, game_id: int, pid: Optional[int], search_root: Optional[str]):
    """Waits on a Win32 process handle in 200ms intervals so F12 screenshot hotkeys respond in real time."""
    last_shot = 0.0
    while True:
        res = ctypes.windll.kernel32.WaitForSingleObject(hProc, 200)
        if res != WAIT_TIMEOUT:
            break
        last_shot = _poll_screenshot_hotkey_if_needed(game_id, pid, search_root, last_shot)


def monitor_game_pid(
    game_id: int,
    target_pid: Optional[int],
    hProcess: Optional[Any],
    start_time: float,
    working_dir: Optional[str] = None,
    exe_name: Optional[str] = None,
    game_folder: Optional[str] = None
):
    """
    Monitors the real game process until it closes, listens for screenshot hotkeys,
    records play duration & play_count only when session >= 3s (preventing 0s crash pollution),
    and triggers automatic incremental save backup + WebDAV sync on exit.
    """
    search_root = game_folder or working_dir
    last_shot = 0.0
    try:
        SYNCHRONIZE = 0x00100000

        if hProcess and IS_WINDOWS:
            _wait_handle_with_hotkey_poll(hProcess, game_id, target_pid, search_root)
            close_win32_handle(hProcess)
            hProcess = None
            # Retry child process detection across a 6-second window for unpacked / NW.js / Unity launcher wrappers
            child_pid = None
            for _ in range(6):
                time.sleep(1.0)
                child_pid = find_game_pid_in_folder(search_root, exe_name)
                if child_pid:
                    break
            if child_pid:
                with RUNNING_LOCK:
                    if game_id in RUNNING_GAMES:
                        RUNNING_GAMES[game_id]["pid"] = child_pid
                while True:
                    for _ in range(10):
                        time.sleep(0.2)
                        last_shot = _poll_screenshot_hotkey_if_needed(game_id, child_pid, search_root, last_shot)
                    child_pid = find_game_pid_in_folder(search_root, exe_name)
                    if not child_pid:
                        break
                    with RUNNING_LOCK:
                        if game_id in RUNNING_GAMES:
                            RUNNING_GAMES[game_id]["pid"] = child_pid
        else:
            if hProcess:
                close_win32_handle(hProcess)
                hProcess = None

            active_pid = target_pid
            if not active_pid:
                for _ in range(6):
                    time.sleep(1.0)
                    active_pid = find_game_pid_in_folder(search_root, exe_name)
                    if active_pid:
                        with RUNNING_LOCK:
                            if game_id in RUNNING_GAMES:
                                RUNNING_GAMES[game_id]["pid"] = active_pid
                        break

            if active_pid and IS_WINDOWS:
                h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, active_pid)
                if h and h != INVALID_HANDLE_VALUE:
                    _wait_handle_with_hotkey_poll(h, game_id, active_pid, search_root)
                    close_win32_handle(h)
                else:
                    while True:
                        for _ in range(10):
                            time.sleep(0.2)
                            last_shot = _poll_screenshot_hotkey_if_needed(game_id, active_pid, search_root, last_shot)
                        active_pid = find_game_pid_in_folder(search_root, exe_name)
                        if not active_pid:
                            break
            else:
                while True:
                    time.sleep(2.0)
                    if not find_game_pid_in_folder(search_root, exe_name):
                        break
    except Exception as e:
        print(f"[MONITOR ERROR] {e}")
    finally:
        if hProcess:
            close_win32_handle(hProcess)
        duration = int(time.time() - start_time)
        if duration >= 3:
            record_game_launch(game_id, duration_seconds=duration, increment_count=True)

        # v2.4: Automatic incremental save snapshot + optional WebDAV cloud backup when session >= threshold
        try:
            cfg = load_config()
            if cfg.get("enable_auto_save_backup", True):
                min_minutes = max(1, int(cfg.get("auto_backup_min_minutes", 5)))
                max_keep = max(1, int(cfg.get("auto_backup_max_keep", 5)))
                if duration >= min_minutes * 60:
                    backup_game_saves(
                        game_id,
                        label=f"自动快照_{duration // 60}m",
                        is_auto=True,
                        max_auto_keep=max_keep
                    )
        except Exception as e:
            print(f"[AutoSaveBackup] Failed on exit for game {game_id}: {e}")

        with RUNNING_LOCK:
            RUNNING_GAMES.pop(game_id, None)


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
    set_last_active_game_id(game_id)
    running = get_running_games_info()
    if game_id in running:
        return {
            "success": False,
            "already_running": True,
            "pid": running[game_id].get("pid"),
            "message": "该游戏已在运行中，无需重复启动"
        }

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
            open_game_folder(folder_path)
            return {"success": True, "message": "未找到主程序，已为您打开游戏目录"}
        return {"success": False, "message": "游戏主程序与目录均不存在"}

    working_dir = os.path.dirname(os.path.abspath(exe_path))
    exe_name = Path(exe_path).name

    try:
        success, pid, hProcess = shell_launch(exe_path, working_dir=working_dir, show_cmd=SW_SHOWNORMAL)
        if not success:
            if IS_WINDOWS:
                os.startfile(exe_path)
            time.sleep(1.0)
            pid = find_game_pid_in_folder(folder_path or working_dir, exe_name)
            hProcess = None

        start_time = time.time()
        with RUNNING_LOCK:
            RUNNING_GAMES[game_id] = {
                "pid": pid,
                "start_time": start_time,
                "exe": exe_name,
                "mode": "native",
                "folder_path": folder_path or working_dir
            }

        t = threading.Thread(
            target=monitor_game_pid,
            args=(game_id, pid, hProcess, start_time, working_dir, exe_name, folder_path),
            daemon=True
        )
        t.start()

        return {
            "success": True,
            "pid": pid,
            "mode": "native",
            "message": f"成功启动: {exe_name}"
        }
    except Exception as e:
        return {"success": False, "message": f"启动失败: {str(e)}"}


def launch_game_with_le(game_id: int) -> Dict[str, Any]:
    """Launches game via Locale Emulator (LEProc.exe) for Japanese Shift-JIS locale emulation."""
    set_last_active_game_id(game_id)
    running = get_running_games_info()
    if game_id in running:
        return {
            "success": False,
            "already_running": True,
            "pid": running[game_id].get("pid"),
            "message": "该游戏已在运行中，无需重复启动"
        }

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
        success, _, hLeProc = shell_launch(
            exe_path=le_exe,
            parameters=f'-run "{exe_path}"',
            working_dir=working_dir,
            show_cmd=SW_SHOWNORMAL
        )
        close_win32_handle(hLeProc)
        if not success:
            subprocess.Popen([le_exe, "-run", exe_path], cwd=working_dir)

        time.sleep(1.0)
        real_pid = find_game_pid_in_folder(folder_path or working_dir, exe_name)
        start_time = time.time()

        with RUNNING_LOCK:
            RUNNING_GAMES[game_id] = {
                "pid": real_pid,
                "start_time": start_time,
                "exe": exe_name,
                "mode": "le",
                "folder_path": folder_path or working_dir
            }

        t = threading.Thread(
            target=monitor_game_pid,
            args=(game_id, real_pid, None, start_time, working_dir, exe_name, folder_path),
            daemon=True
        )
        t.start()

        return {
            "success": True,
            "pid": real_pid,
            "mode": "le",
            "message": f"已通过 Locale Emulator 转区启动: {exe_name}"
        }
    except Exception as e:
        return {"success": False, "message": f"LE 转区启动失败: {str(e)}"}


def open_game_folder(folder_path: str) -> bool:
    if folder_path and os.path.exists(folder_path):
        try:
            if IS_WINDOWS:
                os.startfile(folder_path)
            else:
                subprocess.Popen(["xdg-open", folder_path])
            return True
        except Exception:
            if IS_WINDOWS:
                subprocess.Popen(["explorer.exe", folder_path])
                return True
    return False


def reveal_in_explorer(file_or_dir_path: str) -> bool:
    if file_or_dir_path and os.path.exists(file_or_dir_path):
        try:
            if IS_WINDOWS:
                subprocess.Popen(["explorer.exe", f'/select,"{file_or_dir_path}"'])
                return True
            return open_game_folder(os.path.dirname(file_or_dir_path))
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

    has_bat = False
    bat_file = None
    for cand in ["与工具一同启动.bat", "StartWithTool.bat"]:
        if (folder / cand).exists():
            has_bat = True
            bat_file = str(folder / cand)
            break

    has_trs = False
    trs_file = None
    search_dirs = [folder]
    if (folder / "www").is_dir():
        search_dirs.append(folder / "www")

    for d in search_dirs:
        for cand in ["翻译文件.json", "translation.json", "trs.json"]:
            if (d / cand).exists():
                has_trs = True
                trs_file = str(d / cand)
                break
        if has_trs:
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
        for d in search_dirs:
            try:
                for f in os.listdir(d):
                    full_p = d / f
                    if full_p.is_file() and f.lower().endswith(".json") and is_valid_translation_json(str(full_p)):
                        has_trs = True
                        trs_file = str(full_p)
                        break
            except Exception:
                pass
            if has_trs:
                break

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

    is_baked = False
    if (
        (folder / "data_original_backup").exists()
        or (folder / "www" / "data_original_backup").exists()
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
    set_last_active_game_id(game_id)
    running = get_running_games_info()
    if game_id in running:
        return {
            "success": False,
            "already_running": True,
            "pid": running[game_id].get("pid"),
            "message": "该游戏已在运行中，无需重复启动"
        }

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
            success, _, hInject = shell_launch(
                exe_path=str(inject_exe),
                parameters=f'"{exe_path}" "{hook_dll}"',
                working_dir=working_dir,
                show_cmd=SW_SHOWNORMAL
            )
            close_win32_handle(hInject)
            if not success:
                subprocess.run(
                    f'cmd.exe /c start "" "{inject_exe}" "{exe_path}" "{hook_dll}"',
                    cwd=working_dir,
                    shell=True
                )
        elif status.get("has_bat") and status.get("bat_file"):
            if IS_WINDOWS:
                os.startfile(status["bat_file"])
        else:
            return {"success": False, "message": "缺少 MTool inject.exe 或 hook DLL，无法注入"}

        if nw_exe.exists():
            try:
                _, _, hNw = shell_launch(
                    exe_path=str(nw_exe),
                    parameters=f'"{tool_dir}"',
                    working_dir=str(tool_dir),
                    show_cmd=SW_SHOWMINNOACTIVE
                )
                close_win32_handle(hNw)
            except Exception:
                pass

        time.sleep(1.0)
        real_game_pid = find_game_pid_in_folder(folder_path or working_dir, exe_name)

        start_time = time.time()
        with RUNNING_LOCK:
            RUNNING_GAMES[game_id] = {
                "pid": real_game_pid,
                "start_time": start_time,
                "exe": exe_name,
                "mode": "mtool",
                "folder_path": folder_path or working_dir
            }

        t = threading.Thread(
            target=monitor_game_pid,
            args=(game_id, real_game_pid, None, start_time, working_dir, exe_name, folder_path),
            daemon=True
        )
        t.start()

        mode_name = "汉化" if status.get("has_translation") else "辅助"
        return {
            "success": True,
            "pid": real_game_pid,
            "mode": "mtool",
            "message": f"成功以 MTool {mode_name}模式启动: {exe_name}"
        }
    except Exception as e:
        return {"success": False, "message": f"MTool 启动失败: {str(e)}"}


# ---------------------------------------------------------
# Multi-Engine Save Data Detection (Local + Unity LocalLow + Ren'Py + Kirikiri) (v2.4)
# ---------------------------------------------------------
SAVE_DIR_CANDIDATES = [
    "save",
    os.path.join("www", "save"),
    "Save",
    "SaveData",
    "savedata",
    "Saves",
    "saves",
    "krkrsave",
    os.path.join("data", "save"),
    os.path.join("game", "saves"),
    os.path.join("UserData", "save"),
    os.path.join("Data", "Save"),
    os.path.join("contents", "save"),
    os.path.join("contents", "www", "save"),
]

SAVE_FILE_EXTENSIONS = (
    ".rpgsave", ".rmmzsave", ".rvdata2", ".rvdata", ".rxdata",
    ".sav", ".save", ".lsd", ".ksd", ".dat", ".sol", ".json"
)


def _discover_unity_appdata_save_dir(folder_path: str, game: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Discovers Unity's AppData/LocalLow/<CompanyName>/<ProductName> save directory:
    1. Reads <ExeName>_Data/app.info (line 1 = CompanyName, line 2 = ProductName) inside the game folder.
    2. Falls back to matching circle_name / clean_title / original_title in %USERPROFILE%/AppData/LocalLow.
    """
    user_profile = os.environ.get("USERPROFILE") or str(Path.home())
    locallow = Path(user_profile) / "AppData" / "LocalLow"
    if not locallow.exists() or not locallow.is_dir():
        return None

    # 1. Exact resolution via Unity's <Game>_Data/app.info
    if folder_path and os.path.exists(folder_path):
        root = Path(folder_path)
        app_infos = list(root.glob("*_Data/app.info")) + list(root.glob("*/*_Data/app.info"))
        for info_file in app_infos:
            try:
                lines = [l.strip() for l in info_file.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
                if len(lines) >= 2:
                    company, product = lines[0], lines[1]
                    cand = locallow / company / product
                    if cand.exists() and cand.is_dir():
                        return str(cand)
                elif len(lines) == 1:
                    for sub in locallow.iterdir():
                        if sub.is_dir() and (sub / lines[0]).is_dir():
                            return str(sub / lines[0])
            except Exception:
                pass

    # 2. Fuzzy match Company / Product folder names against game metadata
    if game:
        tokens = set()
        for k in ("clean_title", "original_title", "display_title", "folder_name"):
            v = (game.get(k) or "").strip()
            if v and len(v) >= 2:
                tokens.add(v.lower())
        if folder_path and os.path.exists(folder_path):
            for d in Path(folder_path).glob("*_Data"):
                stem = d.name[:-5].strip()
                if len(stem) >= 2:
                    tokens.add(stem.lower())
        if tokens:
            try:
                for comp_dir in locallow.iterdir():
                    if not comp_dir.is_dir():
                        continue
                    for prod_dir in comp_dir.iterdir():
                        if not prod_dir.is_dir():
                            continue
                        pname = prod_dir.name.lower()
                        if any(pname == t or (len(t) >= 4 and t in pname) for t in tokens):
                            return str(prod_dir)
            except Exception:
                pass
    return None


def _discover_renpy_appdata_save_dir(folder_path: str, game: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Discovers Ren'Py's %APPDATA%/RenPy/<save_directory> folder by inspecting game/options.rpy
    or matching the game's folder/exe stem.
    """
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    renpy_root = Path(appdata) / "RenPy"
    if not renpy_root.exists() or not renpy_root.is_dir():
        return None

    if folder_path and os.path.exists(folder_path):
        root = Path(folder_path)
        for opt_rpy in [root / "game" / "options.rpy", root / "options.rpy"]:
            if opt_rpy.exists():
                try:
                    txt = opt_rpy.read_text(encoding="utf-8", errors="ignore")
                    m = re.search(r'config\.save_directory\s*=\s*["\']([^"\']+)["\']', txt)
                    if m:
                        cand = renpy_root / m.group(1).strip()
                        if cand.exists() and cand.is_dir():
                            return str(cand)
                except Exception:
                    pass

    stems = set()
    if folder_path:
        stems.add(Path(folder_path).name.lower())
    if game:
        for k in ("clean_title", "original_title", "executable_path"):
            v = (game.get(k) or "").strip()
            if v:
                stems.add(Path(v).stem.lower())
    try:
        for sub in renpy_root.iterdir():
            if sub.is_dir():
                s_low = sub.name.lower()
                if any(st and len(st) >= 3 and (s_low.startswith(st) or st in s_low) for st in stems):
                    return str(sub)
    except Exception:
        pass
    return None


def find_game_save_info(folder_path: str, game: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    Resolves the save directory across Local Game Folder, Unity AppData/LocalLow,
    Ren'Py AppData/Roaming/RenPy, and Kirikiri/System directories.
    Returns {"save_dir": str, "save_source_type": str, "save_source_label": str}.
    """
    # 1. Check inside the local game directory first
    if folder_path and os.path.exists(folder_path):
        root = Path(folder_path)
        for rel in SAVE_DIR_CANDIDATES:
            cand = root / rel
            if cand.exists() and cand.is_dir():
                return {
                    "save_dir": str(cand),
                    "save_source_type": "local",
                    "save_source_label": f"游戏内目录 ({rel})"
                }
        try:
            for f in os.listdir(root):
                low = f.lower()
                if low.startswith("save") and low.endswith(SAVE_FILE_EXTENSIONS):
                    return {
                        "save_dir": str(root),
                        "save_source_type": "local",
                        "save_source_label": "游戏根目录"
                    }
        except Exception:
            pass

    engine_type = (game.get("engine_type") if game else "") or ""

    # 2. Check Unity AppData/LocalLow
    if "Unity" in engine_type or (folder_path and os.path.exists(folder_path) and list(Path(folder_path).glob("*_Data"))):
        unity_dir = _discover_unity_appdata_save_dir(folder_path, game=game)
        if unity_dir:
            rel_tail = "/".join(Path(unity_dir).parts[-2:])
            return {
                "save_dir": unity_dir,
                "save_source_type": "appdata_unity",
                "save_source_label": f"Unity 系统目录 (LocalLow/{rel_tail})"
            }

    # 3. Check Ren'Py %APPDATA%/RenPy
    if "Ren'Py" in engine_type or (folder_path and os.path.exists(folder_path) and (Path(folder_path) / "renpy").is_dir()):
        renpy_dir = _discover_renpy_appdata_save_dir(folder_path, game=game)
        if renpy_dir:
            return {
                "save_dir": renpy_dir,
                "save_source_type": "appdata_renpy",
                "save_source_label": f"Ren'Py 系统目录 (AppData/RenPy/{Path(renpy_dir).name})"
            }

    return {"save_dir": "", "save_source_type": "none", "save_source_label": ""}


def find_game_save_dir(folder_path: str, game: Optional[Dict[str, Any]] = None) -> Optional[str]:
    info = find_game_save_info(folder_path, game=game)
    return info["save_dir"] if info.get("save_dir") else None


def get_game_save_status(game_id: int) -> Dict[str, Any]:
    """Inspects local/AppData game save folder, editable RPG Maker slots, and existing backup snapshots."""
    game = get_game_by_id(game_id)
    if not game:
        return {"has_save_dir": False, "save_count": 0, "backups": [], "can_unlock_cg": False, "can_edit_save": False}

    folder_path = game.get("folder_path", "")
    save_info = find_game_save_info(folder_path, game=game)
    save_dir = save_info.get("save_dir") or ""
    save_files: List[str] = []
    editable_rpg_saves = 0
    latest_save_time = ""

    if save_dir and os.path.exists(save_dir):
        latest_ts = 0.0
        is_root_save = bool(folder_path and os.path.normcase(os.path.normpath(save_dir)) == os.path.normcase(os.path.normpath(folder_path)))
        skip_unity_logs = {"player.log", "player-prev.log", "output_log.txt"}
        try:
            for root, dirs, files in os.walk(save_dir):
                if is_root_save:
                    dirs.clear()
                else:
                    dirs[:] = [d for d in dirs if d.lower() not in ("unity", "crashes", "logs", "il2cpp")]
                for fn in files:
                    low = fn.lower()
                    if low in skip_unity_logs or low.endswith(".log"):
                        continue
                    if is_root_save:
                        if not (low.startswith("save") and low.endswith(SAVE_FILE_EXTENSIONS)):
                            continue
                    if (
                        save_info.get("save_source_type") in ("appdata_unity", "appdata_renpy")
                        or low.endswith(SAVE_FILE_EXTENSIONS)
                        or "save" in low or "file" in low or "global" in low
                    ):
                        fp = os.path.join(root, fn)
                        save_files.append(fp)
                        if low.endswith((".rpgsave", ".rmmzsave")) and low not in ("global.rpgsave", "config.rpgsave", "global.rmmzsave", "config.rmmzsave"):
                            editable_rpg_saves += 1
                        st = os.stat(fp)
                        if st.st_mtime > latest_ts:
                            latest_ts = st.st_mtime
        except Exception:
            pass
        if latest_ts > 0:
            latest_save_time = datetime.fromtimestamp(latest_ts).strftime("%Y-%m-%d %H:%M")

    cfg = load_config()
    backup_root = Path(cfg.get("save_backup_directory", r"E:\ACG\_Save_Backups"))
    backups = []
    if backup_root.exists():
        prefix = f"game_{game_id}_"
        for bf in sorted(backup_root.glob(f"{prefix}*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
            st = bf.stat()
            is_auto = "_auto_" in bf.name or "自动快照" in bf.name or "改档前备份" in bf.name
            backups.append({
                "filename": bf.name,
                "path": str(bf),
                "size_kb": round(st.st_size / 1024, 1),
                "is_auto": is_auto,
                "created_at": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })

    engine_type = game.get("engine_type", "") or ""
    can_unlock_cg = bool(
        "MV" in engine_type or "MZ" in engine_type or "RPG Maker" in engine_type
        or (folder_path and ((Path(folder_path) / "data" / "System.json").exists() or (Path(folder_path) / "www" / "data" / "System.json").exists()))
    )

    return {
        "has_save_dir": bool(save_dir),
        "save_dir": save_dir,
        "save_source_type": save_info.get("save_source_type", "none"),
        "save_source_label": save_info.get("save_source_label", ""),
        "save_count": len(save_files),
        "editable_save_count": editable_rpg_saves,
        "can_edit_save": editable_rpg_saves > 0 or can_unlock_cg,
        "latest_save_at": latest_save_time,
        "backup_root": str(backup_root),
        "backups": backups[:25],
        "can_unlock_cg": can_unlock_cg,
        "cg_unlocked": int(game.get("cg_unlocked") or 0),
        "auto_backup_enabled": bool(cfg.get("enable_auto_save_backup", True)),
        "webdav_enabled": bool(cfg.get("webdav_enabled", False) and (cfg.get("webdav_url") or "").strip())
    }


def open_game_save_folder(game_id: int) -> Dict[str, Any]:
    status = get_game_save_status(game_id)
    if status.get("has_save_dir") and status.get("save_dir"):
        open_game_folder(status["save_dir"])
        return {"success": True, "message": f"已打开存档目录 ({status.get('save_source_label') or 'Save'})"}
    game = get_game_by_id(game_id)
    if game and game.get("folder_path") and os.path.exists(game["folder_path"]):
        open_game_folder(game["folder_path"])
        return {"success": True, "message": "未检测到独立 save 文件夹，已为您打开游戏根目录"}
    return {"success": False, "message": "游戏目录不存在"}


def open_save_backup_folder(game_id: int) -> Dict[str, Any]:
    cfg = load_config()
    backup_root = Path(cfg.get("save_backup_directory", r"E:\ACG\_Save_Backups"))
    backup_root.mkdir(parents=True, exist_ok=True)
    open_game_folder(str(backup_root))
    return {"success": True, "message": "已打开存档快照备份目录"}


def _prune_old_auto_backups(backup_root: Path, game_id: int, max_keep: int = 5):
    """Retains only the latest max_keep automatic snapshots for game_id, never touching manual snapshots."""
    try:
        prefix = f"game_{game_id}_"
        auto_files = [
            bf for bf in backup_root.glob(f"{prefix}*.zip")
            if "_auto_" in bf.name or "自动快照" in bf.name
        ]
        auto_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        for old_bf in auto_files[max_keep:]:
            try:
                old_bf.unlink()
            except Exception:
                pass
    except Exception:
        pass


def backup_game_saves(
    game_id: int,
    label: str = "",
    is_auto: bool = False,
    max_auto_keep: Optional[int] = None
) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    status = get_game_save_status(game_id)
    if not status.get("has_save_dir") or not status.get("save_dir"):
        return {"success": False, "message": "未在该游戏目录或系统 AppData 内检测到存档文件夹"}

    save_dir = Path(status["save_dir"])
    cfg = load_config()
    backup_root = Path(cfg.get("save_backup_directory", r"E:\ACG\_Save_Backups"))
    backup_root.mkdir(parents=True, exist_ok=True)

    safe_title = re.sub(r'[\\/*?:"<>|\s]+', "_", (game.get("clean_title") or game.get("folder_name") or "game"))[:24]
    auto_tag = "_auto" if is_auto else ""
    safe_label = "_" + re.sub(r'[\\/*?:"<>|\s]+', "_", label.strip())[:14] if label and label.strip() else ""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"game_{game_id}_{safe_title}{auto_tag}{safe_label}_{ts}.zip"
    zip_path = backup_root / zip_name

    try:
        file_count = 0
        folder_p = game.get("folder_path") or ""
        is_root_save = bool(folder_p and os.path.normcase(os.path.normpath(str(save_dir))) == os.path.normcase(os.path.normpath(folder_p)))
        skip_unity_logs = {"player.log", "player-prev.log", "output_log.txt"}
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(save_dir):
                if is_root_save:
                    dirs.clear()
                else:
                    dirs[:] = [d for d in dirs if d.lower() not in ("unity", "crashes", "logs", "il2cpp")]
                for fn in files:
                    low = fn.lower()
                    if low in skip_unity_logs or low.endswith(".log"):
                        continue
                    if is_root_save:
                        if not (low.startswith("save") and low.endswith(SAVE_FILE_EXTENSIONS)):
                            continue
                    fp = Path(root) / fn
                    rel_p = fp.relative_to(save_dir)
                    zf.write(fp, arcname=str(rel_p))
                    file_count += 1
        if file_count == 0:
            if zip_path.exists():
                zip_path.unlink()
            return {"success": False, "message": "存档目录为空，暂无可备份的存档文件"}

        if is_auto:
            keep_n = max_auto_keep or int(cfg.get("auto_backup_max_keep", 5))
            _prune_old_auto_backups(backup_root, game_id, max_keep=max(1, keep_n))

        # Trigger non-blocking WebDAV cloud upload if enabled
        webdav_synced = False
        if cfg.get("webdav_enabled") and cfg.get("webdav_auto_sync", True) and (cfg.get("webdav_url") or "").strip():
            threading.Thread(target=upload_backup_to_webdav, args=(zip_path, cfg), daemon=True).start()
            webdav_synced = True

        msg = f"已成功备份 {file_count} 个存档文件至 {zip_name}"
        if webdav_synced:
            msg += "（已触发 WebDAV 云端同步）"

        return {
            "success": True,
            "zip_path": str(zip_path),
            "filename": zip_name,
            "file_count": file_count,
            "webdav_triggered": webdav_synced,
            "message": msg,
            "save_status": get_game_save_status(game_id)
        }
    except Exception as e:
        return {"success": False, "message": f"存档备份失败: {str(e)}"}


def restore_game_saves(game_id: int, filename: str) -> Dict[str, Any]:
    """Restores a save backup zip into the game's save directory (local or AppData) with strict ZipSlip protection."""
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    safe_name = Path(filename).name
    if not safe_name.startswith(f"game_{game_id}_") or not safe_name.endswith(".zip"):
        return {"success": False, "message": "非法的存档备份文件名"}

    cfg = load_config()
    backup_root = Path(cfg.get("save_backup_directory", r"E:\ACG\_Save_Backups"))
    zip_path = backup_root / safe_name
    if not zip_path.exists() or not zip_path.is_file():
        return {"success": False, "message": "指定的存档备份文件不存在"}

    folder_path = game.get("folder_path", "")
    save_dir_str = find_game_save_dir(folder_path, game=game)
    if not save_dir_str:
        if not folder_path or not os.path.exists(folder_path):
            return {"success": False, "message": "游戏本地目录不存在，无法还原存档"}
        if (Path(folder_path) / "www").is_dir():
            save_dir = Path(folder_path) / "www" / "save"
        else:
            save_dir = Path(folder_path) / "save"
        save_dir.mkdir(parents=True, exist_ok=True)
    else:
        save_dir = Path(save_dir_str)
        save_dir.mkdir(parents=True, exist_ok=True)

    try:
        target_root = save_dir.resolve()
        restored_count = 0
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                dest_path = (target_root / member.filename).resolve()
                if not is_subpath(str(dest_path), str(target_root)):
                    continue
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, open(dest_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                restored_count += 1

        return {
            "success": True,
            "restored_count": restored_count,
            "message": f"已成功从快照【{safe_name}】还原 {restored_count} 个存档文件！",
            "save_status": get_game_save_status(game_id)
        }
    except Exception as e:
        return {"success": False, "message": f"还原存档失败: {str(e)}"}


def delete_game_save_backup(game_id: int, filename: str) -> Dict[str, Any]:
    safe_name = Path(filename).name
    if not safe_name.startswith(f"game_{game_id}_") or not safe_name.endswith(".zip"):
        return {"success": False, "message": "非法的存档备份文件名"}

    cfg = load_config()
    backup_root = Path(cfg.get("save_backup_directory", r"E:\ACG\_Save_Backups"))
    zip_path = backup_root / safe_name
    if zip_path.exists() and zip_path.is_file():
        try:
            zip_path.unlink()
        except Exception as e:
            return {"success": False, "message": f"删除快照失败: {str(e)}"}
    return {
        "success": True,
        "message": f"已删除存档备份: {safe_name}",
        "save_status": get_game_save_status(game_id)
    }


# ---------------------------------------------------------
# WebDAV Cloud Save Sync Engine (Nutstore / Alist / Nextcloud)
# ---------------------------------------------------------
def _get_webdav_client_and_url(custom_cfg: Optional[Dict[str, Any]] = None):
    cfg = load_config()
    if custom_cfg:
        cfg.update(custom_cfg)
    base_url = (cfg.get("webdav_url") or "").strip().rstrip("/")
    root_sub = (cfg.get("webdav_root_path") or "").strip().strip("/")
    if base_url and root_sub and not base_url.lower().endswith("/" + root_sub.lower()):
        base_url = f"{base_url}/{root_sub}"
    username = (cfg.get("webdav_username") or "").strip()
    password = (cfg.get("webdav_password") or "").strip()
    auth = (username, password) if username or password else None
    client = httpx.Client(auth=auth, timeout=15.0, follow_redirects=True)
    return client, base_url


def test_webdav_connection(custom_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Tests WebDAV server connectivity, credentials, and auto-creates target directory if needed."""
    client, base_url = _get_webdav_client_and_url(custom_cfg)
    if not base_url or not (base_url.startswith("http://") or base_url.startswith("https://")):
        client.close()
        return {"success": False, "message": "请填写合法的 WebDAV 目录 URL（以 http:// 或 https:// 开头）"}

    t0 = time.time()
    try:
        with client:
            r = client.request("PROPFIND", base_url + "/", headers={"Depth": "0"})
            ms = int((time.time() - t0) * 1000)
            if r.status_code in (200, 207):
                return {"success": True, "latency_ms": ms, "message": f"WebDAV 连接成功 ({ms}ms) · 远端存档库已就绪 ({base_url})"}
            elif r.status_code == 404:
                mk = client.request("MKCOL", base_url + "/")
                if mk.status_code in (200, 201, 204):
                    return {"success": True, "latency_ms": ms, "message": f"WebDAV 连接成功 ({ms}ms) · 已自动创建远端备份目录 ({base_url})"}
                return {"success": False, "message": f"远端目录不存在且自动创建失败 (HTTP {mk.status_code})"}
            elif r.status_code in (401, 403):
                return {"success": False, "message": f"WebDAV 认证失败 (HTTP {r.status_code})，请检查账号或应用专用密码"}
            else:
                return {"success": False, "message": f"WebDAV 响应异常: HTTP {r.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"无法连接至 WebDAV 服务器: {str(e)[:80]}"}


def upload_backup_to_webdav(zip_path: Path, custom_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Uploads a local save backup ZIP file to the configured WebDAV directory."""
    if not zip_path.exists() or not zip_path.is_file():
        return {"success": False, "message": "本地备份文件不存在"}

    client, base_url = _get_webdav_client_and_url(custom_cfg)
    if not base_url:
        client.close()
        return {"success": False, "message": "尚未配置 WebDAV 服务器地址"}

    try:
        with client:
            # Ensure target folder exists on WebDAV
            try:
                chk = client.request("PROPFIND", base_url + "/", headers={"Depth": "0"})
                if chk.status_code == 404:
                    client.request("MKCOL", base_url + "/")
            except Exception:
                pass

            encoded_name = urllib.parse.quote(zip_path.name)
            target_url = f"{base_url}/{encoded_name}"
            with open(zip_path, "rb") as f:
                content = f.read()
            r = client.put(target_url, content=content, headers={"Content-Type": "application/zip"})
            if r.status_code in (200, 201, 204):
                return {
                    "success": True,
                    "filename": zip_path.name,
                    "remote_url": target_url,
                    "message": f"已同步至 WebDAV 云端: {zip_path.name}"
                }
            return {"success": False, "message": f"WebDAV 上传失败 (HTTP {r.status_code})"}
    except Exception as e:
        return {"success": False, "message": f"WebDAV 上传异常: {str(e)[:80]}"}


def sync_game_saves_with_webdav(game_id: int) -> Dict[str, Any]:
    """
    One-click WebDAV Save Sync for a game:
    1. If local save directory has files and no recent backup exists, creates a fresh snapshot.
    2. Uploads the latest local snapshot for game_id to WebDAV.
    3. Also checks WebDAV via PROPFIND to pull any remote snapshots for game_id that are missing locally.
    """
    cfg = load_config()
    if not (cfg.get("webdav_url") or "").strip():
        return {"success": False, "message": "请先在【系统设置 -> 自动快照与 WebDAV】中配置 WebDAV 地址与账号"}

    backup_root = Path(cfg.get("save_backup_directory", r"E:\ACG\_Save_Backups"))
    backup_root.mkdir(parents=True, exist_ok=True)
    prefix = f"game_{game_id}_"

    local_zips = sorted(backup_root.glob(f"{prefix}*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not local_zips:
        bak_res = backup_game_saves(game_id, label="云同步快照")
        if bak_res.get("success"):
            local_zips = sorted(backup_root.glob(f"{prefix}*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)

    uploaded_name = ""
    if local_zips:
        up_res = upload_backup_to_webdav(local_zips[0], cfg)
        if up_res.get("success"):
            uploaded_name = local_zips[0].name
        else:
            return {
                "success": False,
                "message": up_res.get("message", "WebDAV 云端上传失败"),
                "save_status": get_game_save_status(game_id)
            }

    downloaded_count = 0
    client, base_url = _get_webdav_client_and_url(cfg)
    try:
        with client:
            r = client.request("PROPFIND", base_url + "/", headers={"Depth": "1"})
            if r.status_code in (200, 207) and r.text:
                root_el = ET.fromstring(r.text)
                for elem in root_el.iter():
                    if elem.tag.endswith("href") and elem.text:
                        href_decoded = urllib.parse.unquote(elem.text.strip())
                        fname = Path(href_decoded.rstrip("/")).name
                        if fname.startswith(prefix) and fname.endswith(".zip"):
                            local_target = backup_root / fname
                            if not local_target.exists():
                                dl_url = f"{base_url}/{urllib.parse.quote(fname)}"
                                dl_resp = client.get(dl_url)
                                if dl_resp.status_code == 200 and dl_resp.content.startswith(b"PK\x03\x04"):
                                    with open(local_target, "wb") as f:
                                        f.write(dl_resp.content)
                                    downloaded_count += 1
    except Exception:
        pass

    parts = []
    if uploaded_name:
        parts.append(f"已上传最新快照 ({uploaded_name})")
    if downloaded_count > 0:
        parts.append(f"从云端拉取了 {downloaded_count} 份历史快照")
    if not parts:
        parts.append("WebDAV 云端存档已是最新状态")

    return {
        "success": True,
        "uploaded": uploaded_name,
        "downloaded_count": downloaded_count,
        "save_status": get_game_save_status(game_id),
        "message": "WebDAV 同步完成：" + "，".join(parts)
    }
