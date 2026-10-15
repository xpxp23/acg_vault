import os
import time
import subprocess
import threading
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Dict, Any, Optional
from db.database import get_game_by_id, record_game_launch
from core.scanner import fast_inspect_folder, choose_best_executable
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

def launch_game(game_id: int, mode: Optional[str] = None) -> Dict[str, Any]:
    """Launches the primary executable for a game with normal interactive window and tracks play session."""
    # Check if MTool launch is explicitly requested or smart-defaulted
    if mode == "mtool":
        return launch_game_with_mtool(game_id)
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

    # If exe_path is missing or invalid, try to rediscover it
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
        # Launch using ShellExecuteExW with SW_SHOWNORMAL (1) to guarantee foreground interactive window!
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
    """Inspects game folder to determine if MTool translation is available/supported."""
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

    folder = Path(folder_path)

    # Check for MTool bat files
    has_bat = False
    bat_file = None
    for cand in ["与工具一同启动.bat", "StartWithTool.bat"]:
        if (folder / cand).exists():
            has_bat = True
            bat_file = str(folder / cand)
            break

    # Check for translation JSON
    has_trs = False
    trs_file = None
    if (folder / "翻译文件.json").exists():
        has_trs = True
        trs_file = str(folder / "翻译文件.json")
    elif (folder / "lastLoadedTrsFile").exists():
        has_trs = True
        try:
            with open(folder / "lastLoadedTrsFile", "r", encoding="utf-8-sig") as f:
                ref = f.read().strip()
                if (folder / ref).exists():
                    trs_file = str(folder / ref)
                else:
                    trs_file = "lastLoadedTrsFile"
        except Exception:
            trs_file = "lastLoadedTrsFile"
    else:
        try:
            for f in os.listdir(folder):
                if f.endswith(".json") and f not in ("package.json", "packageV.json") and "config" not in f.lower():
                    has_trs = True
                    trs_file = str(folder / f)
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

    # Check if translation has already been baked into the game files (Decision 4A)
    is_baked = False
    if (folder / "data_original_backup").exists() or (folder / "index.html.original_bak").exists():
        is_baked = True

    # Supported if MTool is installed AND the game engine is supported by MTool
    supported = mtool_installed and is_mtool_engine
    has_translation = bool(has_bat or has_trs)

    # If already baked, default to native (Decision 4A); if unbaked and has translation, default to mtool
    if is_baked:
        launch_mode_default = "native"
    elif supported and has_translation:
        launch_mode_default = "mtool"
    else:
        launch_mode_default = "native"

    can_bake_patch = bool(supported and has_trs and not is_baked and ("MV" in engine_type or "MZ" in engine_type or "RPG Maker MV/MZ" in engine_type))

    return {
        "supported": supported,
        "mtool_installed": mtool_installed,
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

    # Ensure lastLoadedTrsFile exists if translation file exists
    if status.get("trs_file") and os.path.exists(status["trs_file"]):
        trs_name = os.path.basename(status["trs_file"])
        last_trs = os.path.join(working_dir, "lastLoadedTrsFile")
        try:
            with open(last_trs, "w", encoding="utf-8") as f:
                f.write(trs_name)
        except Exception:
            pass

    try:
        # Step 1: Launch game via inject.exe using ShellExecuteExW with SW_SHOWNORMAL (1) (Decision 1A)
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

        # Step 2: Launch MTool companion app nw.exe minimized to taskbar (SW_SHOWMINNOACTIVE = 7) (Decision 2A)
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

        # Step 3: Wait 1.0s to scan and lock the real Game.exe PID (Decision 3A)
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

