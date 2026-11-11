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
from typing import Dict, Any, Optional, List, Tuple, Set
import httpx

from db.database import get_game_by_id, record_game_launch, update_game_user_state
from core.scanner import fast_inspect_folder, choose_best_executable, is_valid_translation_json, IGNORE_EXE_PATTERNS
from core import mtool_link
from config import load_config

IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0

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
SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001
JobObjectBasicProcessIdList = 3

HOTKEY_VK_MAP = {
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
    "PRTSC": 0x2C,
    "INS": 0x2D
}

SHELL_WRAPPER_EXES = {
    "cmd.exe", "conhost.exe", "powershell.exe", "pwsh.exe",
    "explorer.exe", "leproc.exe", "inject.exe", "nw.exe"
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

    class JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):
        _fields_ = [
            ("NumberOfAssignedProcesses", wintypes.DWORD),
            ("NumberOfProcessIdsInList", wintypes.DWORD),
            ("ProcessIdList", ctypes.c_size_t * 256),
        ]

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("dwTime", wintypes.DWORD),
        ]

    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
        user32.GetLastInputInfo.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
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
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
        ]
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL
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


class AfkTracker:
    """
    ACG Vault v3.3.0 Win32 防挂机闲置跟踪器（双阈值宽限期扣除模型）：
    - 周期性调用 poll(known_tree_pids, active_pid)（限流每 1 秒采样一次）；
    - 借助 GetLastInputInfo 获取全系统无操作时长（键鼠无输入）；
    - 借助 GetForegroundWindow 与 PID 树判定游戏是否在前台；
    - 前台宽限阈值（默认 15 分钟），后台失焦宽限阈值（默认 5 分钟）；
    - 宽限期内视为合理剧情阅读停留；超出宽限期部分的闲置时间被视作挂机离开，从总时长中扣减；
    - 退出时调用 finish() 结算并返回累计扣减秒数 total_idle_deducted。
    """
    def __init__(self, enabled: bool = True, fg_threshold_sec: int = 900, bg_threshold_sec: int = 300):
        self.enabled = bool(enabled and IS_WINDOWS)
        self.fg_threshold_sec = max(60, int(fg_threshold_sec))
        self.bg_threshold_sec = max(30, int(bg_threshold_sec))
        self.total_idle_deducted = 0
        self._last_poll_ts = time.time()
        self._current_idle_run_sec = 0.0
        self._current_threshold_sec = self.fg_threshold_sec
        self._prev_system_idle_sec = 0.0

    def poll(self, known_tree_pids: Set[int], active_pid: Optional[int]) -> None:
        if not self.enabled:
            return
        now = time.time()
        if now - self._last_poll_ts < 0.95:
            return
        self._last_poll_ts = now

        try:
            # 1. 查询系统全局键鼠无输入毫秒数
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                return

            tick_now = ctypes.windll.kernel32.GetTickCount()
            idle_ms = (tick_now - lii.dwTime) & 0xFFFFFFFF
            system_idle_sec = max(0.0, idle_ms / 1000.0)

            # 2. 查询当前前台窗口 PID
            fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
            is_foreground = False
            if fg_hwnd:
                fg_pid = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(fg_pid))
                p = int(fg_pid.value)
                if p and (p in known_tree_pids or (active_pid and p == active_pid)):
                    is_foreground = True

            current_thresh = self.fg_threshold_sec if is_foreground else self.bg_threshold_sec

            # 3. 跟踪闲置状态与恢复
            if system_idle_sec < self._prev_system_idle_sec:
                # 用户活动恢复：若此前连续闲置超过宽限期，扣除超出部分
                if self._current_idle_run_sec > self._current_threshold_sec:
                    excess = int(self._current_idle_run_sec - self._current_threshold_sec)
                    if excess > 0:
                        self.total_idle_deducted += excess
                        print(f"[AFK] 恢复活动：前序闲置 {int(self._current_idle_run_sec)}s (门槛 {self._current_threshold_sec}s)，本次扣除闲置 {excess}s。累计已扣除: {self.total_idle_deducted}s")
                self._current_idle_run_sec = system_idle_sec
            else:
                self._current_idle_run_sec = system_idle_sec

            self._current_threshold_sec = current_thresh
            self._prev_system_idle_sec = system_idle_sec
        except Exception:
            pass

    def finish(self) -> int:
        """收尾阶段：如果游戏退出时用户正处于超额闲置状态，结算这最后一段挂机扣减。"""
        if not self.enabled:
            return 0
        try:
            if self._current_idle_run_sec > self._current_threshold_sec:
                excess = int(self._current_idle_run_sec - self._current_threshold_sec)
                if excess > 0:
                    self.total_idle_deducted += excess
                    print(f"[AFK] 退出时处于闲置状态 ({int(self._current_idle_run_sec)}s)，扣除末尾挂机 {excess}s。最终挂机扣除: {self.total_idle_deducted}s")
        except Exception:
            pass
        return max(0, int(self.total_idle_deducted))


def _create_tracking_job_object(hProcess: Optional[Any] = None, pid: Optional[int] = None) -> Optional[Any]:
    """
    Creates an unnamed Windows Job Object and assigns the target process to it so all
    child/grandchild processes spawned by a launcher shell remain tracked in kernel space.
    """
    if not IS_WINDOWS:
        return None
    try:
        k32 = ctypes.windll.kernel32
        hJob = k32.CreateJobObjectW(None, None)
        if not hJob or hJob == INVALID_HANDLE_VALUE:
            return None
        assigned = False
        if hProcess and hProcess != INVALID_HANDLE_VALUE:
            assigned = bool(k32.AssignProcessToJobObject(hJob, hProcess))
        if not assigned and pid and pid > 0:
            hOpen = k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, int(pid))
            if hOpen and hOpen != INVALID_HANDLE_VALUE:
                try:
                    assigned = bool(k32.AssignProcessToJobObject(hJob, hOpen))
                finally:
                    close_win32_handle(hOpen)
        if assigned:
            return hJob
        close_win32_handle(hJob)
    except Exception:
        pass
    return None


def _assign_pid_to_job(hJob: Optional[Any], pid: Optional[int]) -> bool:
    if not IS_WINDOWS or not hJob or not pid or pid <= 0:
        return False
    try:
        k32 = ctypes.windll.kernel32
        hOpen = k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, int(pid))
        if hOpen and hOpen != INVALID_HANDLE_VALUE:
            try:
                return bool(k32.AssignProcessToJobObject(hJob, hOpen))
            finally:
                close_win32_handle(hOpen)
    except Exception:
        pass
    return False


def _get_job_pids(hJob: Optional[Any], exclude_pids: Optional[Set[int]] = None) -> List[int]:
    """Queries active process IDs currently inside a Windows Job Object."""
    if not IS_WINDOWS or not hJob or hJob == INVALID_HANDLE_VALUE:
        return []
    excl = set(exclude_pids or set()) | {os.getpid()}
    try:
        info = JOBOBJECT_BASIC_PROCESS_ID_LIST()
        ret_len = wintypes.DWORD(0)
        ok = ctypes.windll.kernel32.QueryInformationJobObject(
            hJob,
            JobObjectBasicProcessIdList,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(ret_len)
        )
        if not ok:
            return []
        count = min(int(info.NumberOfProcessIdsInList), 256)
        pids: List[int] = []
        for i in range(count):
            p = int(info.ProcessIdList[i])
            if p <= 0 or p in excl or not is_pid_alive(p):
                continue
            img = get_process_image_path(p)
            if img:
                exe_low = Path(img).name.lower()
                if exe_low in SHELL_WRAPPER_EXES or any(pat.search(exe_low) for pat in IGNORE_EXE_PATTERNS):
                    continue
            pids.append(p)
        return pids
    except Exception:
        return []


def _find_descendant_pids(root_pids: Set[int]) -> List[int]:
    """
    Finds alive descendant processes of root_pids using a single Toolhelp32 process snapshot
    (via th32ParentProcessID tree traversal), filtering out shell/helper wrappers.
    """
    if not IS_WINDOWS or not root_pids:
        return []
    hSnap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not hSnap or hSnap == INVALID_HANDLE_VALUE:
        return []
    parent_map: Dict[int, int] = {}
    name_map: Dict[int, str] = {}
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if ctypes.windll.kernel32.Process32FirstW(hSnap, ctypes.byref(pe)):
            while True:
                pid = int(pe.th32ProcessID)
                parent_map[pid] = int(pe.th32ParentProcessID)
                name_map[pid] = pe.szExeFile
                if not ctypes.windll.kernel32.Process32NextW(hSnap, ctypes.byref(pe)):
                    break
    finally:
        close_win32_handle(hSnap)

    tree: Set[int] = set(int(p) for p in root_pids if p)
    changed = True
    while changed:
        changed = False
        for pid, ppid in parent_map.items():
            if ppid in tree and pid not in tree:
                tree.add(pid)
                changed = True

    own_pid = os.getpid()
    descendants: List[int] = []
    for pid in tree - set(root_pids):
        if pid == own_pid or not is_pid_alive(pid):
            continue
        sz_low = (name_map.get(pid) or "").lower()
        if sz_low in SHELL_WRAPPER_EXES:
            continue
        if any(pat.search(sz_low) for pat in IGNORE_EXE_PATTERNS):
            continue
        descendants.append(pid)
    return descendants


def find_game_pid_in_folder(
    folder_path: str,
    exe_filename: Optional[str] = None,
    fallback_by_name: bool = False
) -> Optional[int]:
    """
    Finds the PID of a running game process strictly inside a specific folder.

    fallback_by_name: 读不到进程镜像路径时按进程名兜底。MTool 以管理员权限注入时，
    提权进程的 QueryFullProcessImageNameW 可能失败，旧实现会直接判定"游戏没启动"，
    连带 playtime / 手柄转发 / F12 截图 / Alt+G 定位全部失靶。
    """
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
        name_candidates = []
        own_pid = os.getpid()
        if ctypes.windll.kernel32.Process32FirstW(hSnap, ctypes.byref(pe)):
            while True:
                pid = int(pe.th32ProcessID)
                sz_name = pe.szExeFile
                path = get_process_image_path(pid)
                if path and is_subpath(path, folder_path):
                    if exe_filename and sz_name.lower() == exe_filename.lower():
                        exact_candidates.append(pid)
                    elif not any(pat.search(sz_name) for pat in IGNORE_EXE_PATTERNS):
                        folder_candidates.append(pid)
                elif fallback_by_name and exe_filename and not path and pid != own_pid:
                    if sz_name.lower() == exe_filename.lower():
                        name_candidates.append(pid)
                if not ctypes.windll.kernel32.Process32NextW(hSnap, ctypes.byref(pe)):
                    break
        if exact_candidates:
            return exact_candidates[0]
        if folder_candidates:
            return folder_candidates[0]
        if name_candidates:
            return name_candidates[0]
        return None
    finally:
        close_win32_handle(hSnap)


def _iter_process_snapshot() -> List[Tuple[int, str, str]]:
    """一次 Toolhelp 快照，返回 (pid, exe 文件名, 完整路径)；路径读不到时为空串。"""
    if not IS_WINDOWS:
        return []
    hSnap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not hSnap or hSnap == INVALID_HANDLE_VALUE:
        return []
    out: List[Tuple[int, str, str]] = []
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if ctypes.windll.kernel32.Process32FirstW(hSnap, ctypes.byref(pe)):
            while True:
                out.append((int(pe.th32ProcessID), pe.szExeFile, get_process_image_path(int(pe.th32ProcessID))))
                if not ctypes.windll.kernel32.Process32NextW(hSnap, ctypes.byref(pe)):
                    break
    finally:
        close_win32_handle(hSnap)
    return out


def find_game_pid_multi(
    exe_names: List[str],
    search_roots: Optional[List[str]] = None,
    allow_name_only: bool = True
) -> Optional[int]:
    """
    按「多个候选 exe 名 + 多个候选目录」查找游戏进程。

    MTool 的联动方式会让进程名和路径同时偏离游戏目录：
      1. 软链/复制到 C:\\Users\\Public\\MTool_Game_Tmp\\<hash>\\ 下运行 MTool_Game.exe；
      2. 勾选「复制工具到游戏」后直接在游戏目录跑 MTool_Game.exe；
      3. 没改名的原始 exe（GamePro.exe / Game.exe）。
    只按「游戏目录 + DB 里的 executable_path」找必然失配，这里同时接受名字与目录的多种组合。
    """
    wanted = {str(n).lower() for n in (exe_names or []) if n}
    if not wanted:
        return None
    roots = [r for r in (search_roots or []) if r]
    own_pid = os.getpid()
    exact: List[int] = []
    named: List[int] = []
    for pid, name, path in _iter_process_snapshot():
        if pid == own_pid or name.lower() not in wanted:
            continue
        if path and any(is_subpath(path, root) for root in roots):
            exact.append(pid)
        else:
            named.append(pid)
    if exact:
        return exact[0]
    if allow_name_only and named:
        return named[0]
    return None


def parse_mtool_launch_target(bat_path: Optional[str]) -> Optional[Tuple[str, str]]:
    """
    从 MTool 生成的「与工具一同启动.bat」解析真正被注入的 exe。
      inject.exe "C:\\Users\\Public\\MTool_Game_Tmp\\<hash>\\MTool_Game.exe" "wolfHook3.dll"
    返回 (目录, exe 文件名)；解析失败返回 None。
    """
    if not bat_path or not os.path.exists(bat_path):
        return None
    text = ""
    for enc in ("utf-8-sig", "utf-8", "gbk", "cp936"):
        try:
            with open(bat_path, "r", encoding=enc, errors="ignore") as f:
                text = f.read()
        except Exception:
            continue
        if text:
            break
    if not text:
        return None
    m = re.search(r'inject(?:\.exe)?"?\s+"([^"]+?\.exe)"', text, re.I)
    if not m:
        m = re.search(r'inject(?:\.exe)?"?\s+([^\s"]+?\.exe)', text, re.I)
    if not m:
        return None
    target = m.group(1).strip().strip('"')
    base_dir = str(Path(bat_path).parent) + os.sep
    target = target.replace("%~dp0", base_dir).replace("%%", "%")
    folder, name = os.path.dirname(target), os.path.basename(target)
    if not folder or not name:
        return None
    return folder, name


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
            tracker = info.get("afk_tracker")
            idle_sec = tracker.total_idle_deducted if tracker else 0
            net_elapsed = max(0, elapsed - idle_sec)
            active[gid] = {
                "game_id": gid,
                "pid": info.get("pid"),
                "start_time": info.get("start_time", now),
                "exe": info.get("exe", ""),
                "mode": info.get("mode", "native"),
                "phase": info.get("phase") or ("running" if info.get("pid") else "attaching"),
                "attached": bool(info.get("pid")),
                "elapsed_seconds": max(0, elapsed),
                "net_elapsed_seconds": max(0, net_elapsed),
                "idle_deducted_seconds": max(0, int(idle_sec)),
                "hook_dll": info.get("hook_dll"),
                "exe_bitness": info.get("exe_bitness"),
                "launch_method": info.get("launch_method"),
                "mtool_associated": info.get("mtool_associated"),
                "mtool_detail": info.get("mtool_detail"),
            }
    return active


def _try_reserve_game_launch(game_id: int, mode: str) -> Optional[Dict[str, Any]]:
    """
    Atomically checks RUNNING_GAMES under RUNNING_LOCK and reserves a 'starting' slot
    to prevent double-click race conditions from spawning duplicate instances.
    Returns an 'already_running' response dict if already active/starting, or None if reserved.
    """
    now = time.time()
    with RUNNING_LOCK:
        existing = RUNNING_GAMES.get(game_id)
        if existing is not None:
            return {
                "success": False,
                "already_running": True,
                "pid": existing.get("pid"),
                "message": "该游戏已在运行或启动中，无需重复启动"
            }
        RUNNING_GAMES[game_id] = {
            "pid": None,
            "start_time": now,
            "exe": "",
            "mode": mode,
            "phase": "starting",
            "folder_path": ""
        }
    return None


def _release_game_launch_reservation(game_id: int) -> None:
    with RUNNING_LOCK:
        info = RUNNING_GAMES.get(game_id)
        if info and info.get("phase") == "starting":
            RUNNING_GAMES.pop(game_id, None)


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


def _wait_handle_with_hotkey_poll(
    hProc: Any,
    game_id: int,
    pid: Optional[int],
    search_root: Optional[str],
    afk_tracker: Optional[Any] = None,
    known_tree_pids: Optional[Set[int]] = None
):
    """Waits on a Win32 process handle in 200ms intervals so F12 screenshot hotkeys respond in real time, and polls AFK tracker."""
    last_shot = 0.0
    while True:
        res = ctypes.windll.kernel32.WaitForSingleObject(hProc, 200)
        if res != WAIT_TIMEOUT:
            break
        last_shot = _poll_screenshot_hotkey_if_needed(game_id, pid, search_root, last_shot)
        if afk_tracker is not None:
            afk_tracker.poll(known_tree_pids or set(), pid)


def _bind_running_pid(game_id: int, pid: Optional[int], phase: str = "running", reset_start_time: bool = False) -> Optional[float]:
    """把最新发现的真实游戏 PID 写回会话表，供手柄转发 / 截图 / 悬浮窗定位共用。"""
    new_ts = time.time() if reset_start_time else None
    with RUNNING_LOCK:
        info = RUNNING_GAMES.get(game_id)
        if info is not None:
            if pid:
                info["pid"] = int(pid)
            info["phase"] = phase
            if new_ts is not None:
                info["start_time"] = new_ts
    return new_ts


def _await_game_process(
    search_root: str,
    exe_name: Optional[str],
    timeout: float,
    poll: float = 0.5,
    resolver: Optional[Any] = None
) -> Optional[int]:
    """
    柔性等待游戏进程出现。

    MTool 的 inject.exe 先起注入器、再拉起游戏本体；首次注入、需要人工点确认、
    或 32 位 hook 加载较慢时，进程出现时间可能晚于 10 秒。
    """
    deadline = time.time() + max(3.0, timeout)
    while time.time() < deadline:
        pid = resolver() if resolver else find_game_pid_in_folder(search_root, exe_name, fallback_by_name=True)
        if pid:
            return pid
        time.sleep(poll)
    return None


def _watch_until_exit(
    game_id: int,
    pid: Optional[int],
    search_root: str,
    exe_name: Optional[str],
    last_shot: float = 0.0,
    resolver: Optional[Any] = None,
    hJob: Optional[Any] = None,
    known_tree_pids: Optional[Set[int]] = None,
    afk_tracker: Optional[Any] = None
) -> float:
    """
    当目标进程由于权限原因无法打开 SYNCHRONIZE 句柄时的兜底守候：
    一旦拿到了新的可打开 SYNCHRONIZE 句柄的 PID，优先切回内核级等待。
    """
    miss = 0
    tracked_roots = set(known_tree_pids or set())
    if pid:
        tracked_roots.add(int(pid))
    while True:
        time.sleep(0.4)
        last_shot = _poll_screenshot_hotkey_if_needed(game_id, pid, search_root, last_shot)
        if afk_tracker is not None:
            afk_tracker.poll(tracked_roots, pid)
        if pid and is_pid_alive(pid):
            miss = 0
            continue
        # 当前 PID 已退出，尝试从 Job Object -> 子孙树 -> 目录/名字解析器寻找接管进程
        job_pids = _get_job_pids(hJob, exclude_pids=tracked_roots)
        desc_pids = _find_descendant_pids(tracked_roots)
        pid_now = (
            (job_pids[0] if job_pids else None)
            or (desc_pids[0] if desc_pids else None)
            or (resolver() if resolver else find_game_pid_in_folder(search_root, exe_name, fallback_by_name=True))
        )
        if pid_now:
            miss = 0
            if pid_now != pid:
                pid = int(pid_now)
                tracked_roots.add(pid)
                _bind_running_pid(game_id, pid, "running")
                if IS_WINDOWS:
                    h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                    if h and h != INVALID_HANDLE_VALUE:
                        _wait_handle_with_hotkey_poll(h, game_id, pid, search_root, afk_tracker=afk_tracker, known_tree_pids=tracked_roots)
                        close_win32_handle(h)
        else:
            miss += 1
            if miss >= 3:
                return last_shot


def monitor_game_pid(
    game_id: int,
    target_pid: Optional[int],
    hProcess: Optional[Any],
    start_time: float,
    working_dir: Optional[str] = None,
    exe_name: Optional[str] = None,
    game_folder: Optional[str] = None,
    attach_timeout: float = 120.0,
    resolver: Optional[Any] = None,
    hJob: Optional[Any] = None
):
    """
    Monitors the real game process until it closes using Windows Job Objects, parent-child
    process tree tracking, and kernel-level SYNCHRONIZE handle waiting.
    Records play duration & play_count only when session >= 3s (preventing 0s crash pollution),
    and triggers automatic incremental save backup + WebDAV sync on exit.
    """
    search_root = game_folder or working_dir or ""
    last_shot = 0.0
    attached = False
    known_tree_pids: Set[int] = set()
    if target_pid and target_pid > 0:
        known_tree_pids.add(int(target_pid))

    cfg = load_config()
    afk_enabled = bool(cfg.get("enable_afk_detection", True))
    afk_fg = int(cfg.get("afk_timeout_foreground", 15)) * 60
    afk_bg = int(cfg.get("afk_timeout_background", 5)) * 60
    min_play_dur = int(cfg.get("min_play_duration_seconds", 120))
    afk_tracker = AfkTracker(enabled=afk_enabled, fg_threshold_sec=afk_fg, bg_threshold_sec=afk_bg)

    def _find() -> Optional[int]:
        if resolver is not None:
            try:
                return resolver()
            except Exception:
                return None
        return find_game_pid_in_folder(search_root, exe_name, fallback_by_name=True)

    def _find_handoff_child(exited_pid: Optional[int]) -> Optional[int]:
        if exited_pid and exited_pid > 0:
            known_tree_pids.add(int(exited_pid))
        # Check immediately and up to 6 times (3.0s window) for child process handoff
        for attempt in range(7):
            if attempt > 0:
                time.sleep(0.5)
            job_pids = _get_job_pids(hJob, exclude_pids=known_tree_pids)
            if job_pids:
                return job_pids[0]
            desc_pids = _find_descendant_pids(known_tree_pids)
            if desc_pids:
                return desc_pids[0]
            cand = _find()
            if cand and cand not in known_tree_pids and is_pid_alive(cand):
                return int(cand)
            # Also accept an alive PID returned by _find() even if it was seen earlier
            if cand and cand != exited_pid and is_pid_alive(cand):
                return int(cand)
        return None

    try:
        active_pid = target_pid
        if not active_pid and not (hProcess and IS_WINDOWS):
            _bind_running_pid(game_id, None, "attaching")
            active_pid = _await_game_process(search_root, exe_name, attach_timeout, resolver=_find)

        if not active_pid and not (hProcess and IS_WINDOWS):
            # 等到超时也没等到进程 → 游戏没真正起来，不计时，直接收尾
            with RUNNING_LOCK:
                RUNNING_GAMES.pop(game_id, None)
            return

        # 真正附着到进程时重置精确计时起点，排除启动器/注入器前置等待时间
        attached = True
        reset_ts = _bind_running_pid(game_id, active_pid, "running", reset_start_time=True)
        if reset_ts is not None:
            start_time = reset_ts

        with RUNNING_LOCK:
            if game_id in RUNNING_GAMES:
                RUNNING_GAMES[game_id]["afk_tracker"] = afk_tracker

        if active_pid and active_pid > 0:
            known_tree_pids.add(int(active_pid))

        if IS_WINDOWS and hJob is None:
            hJob = _create_tracking_job_object(hProcess=hProcess, pid=active_pid)
        elif IS_WINDOWS and hJob and active_pid:
            _assign_pid_to_job(hJob, active_pid)

        # Wait on initial process handle if provided
        if hProcess and IS_WINDOWS:
            # Capture initial descendants before hProcess exits if possible
            for dp in _find_descendant_pids(known_tree_pids):
                known_tree_pids.add(dp)
            _wait_handle_with_hotkey_poll(hProcess, game_id, active_pid, search_root, afk_tracker=afk_tracker, known_tree_pids=known_tree_pids)
            close_win32_handle(hProcess)
            hProcess = None
            active_pid = _find_handoff_child(active_pid)

        # Loop over active_pid and any subsequent child handoffs using kernel SYNCHRONIZE wait
        while active_pid and is_pid_alive(active_pid):
            known_tree_pids.add(int(active_pid))
            _bind_running_pid(game_id, active_pid, "running")
            if IS_WINDOWS:
                if hJob is None:
                    hJob = _create_tracking_job_object(pid=active_pid)
                else:
                    _assign_pid_to_job(hJob, active_pid)

                hSync = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(active_pid))
                if hSync and hSync != INVALID_HANDLE_VALUE:
                    _wait_handle_with_hotkey_poll(hSync, game_id, active_pid, search_root, afk_tracker=afk_tracker, known_tree_pids=known_tree_pids)
                    close_win32_handle(hSync)
                    active_pid = _find_handoff_child(active_pid)
                else:
                    last_shot = _watch_until_exit(
                        game_id, active_pid, search_root, exe_name, last_shot, _find,
                        hJob=hJob, known_tree_pids=known_tree_pids, afk_tracker=afk_tracker
                    )
                    break
            else:
                last_shot = _watch_until_exit(
                    game_id, active_pid, search_root, exe_name, last_shot, _find,
                    hJob=hJob, known_tree_pids=known_tree_pids, afk_tracker=afk_tracker
                )
                break
    except Exception as e:
        print(f"[MONITOR ERROR] {e}")
    finally:
        if hProcess:
            close_win32_handle(hProcess)
        if hJob:
            close_win32_handle(hJob)

        idle_deducted = afk_tracker.finish()
        gross_duration = int(time.time() - start_time)
        net_duration = max(0, gross_duration - idle_deducted)
        if attached and net_duration >= min_play_dur:
            start_iso = datetime.fromtimestamp(start_time).isoformat()
            record_game_launch(
                game_id,
                duration_seconds=net_duration,
                increment_count=True,
                start_time=start_iso,
                idle_seconds=idle_deducted,
                min_duration_seconds=min_play_dur
            )
        elif attached:
            print(f"[PLAYTIME] Game {game_id} 运行时长 {gross_duration}s (剔除挂机 {idle_deducted}s，净时长 {net_duration}s) 不足 {min_play_dur}s 门槛，已忽略不计入时长与次数。")

        # v2.4: Automatic incremental save snapshot + optional WebDAV cloud backup when session >= threshold
        try:
            if cfg.get("enable_auto_save_backup", True):
                min_minutes = max(1, int(cfg.get("auto_backup_min_minutes", 5)))
                max_keep = max(1, int(cfg.get("auto_backup_max_keep", 5)))
                if net_duration >= min_minutes * 60:
                    backup_game_saves(
                        game_id,
                        label=f"自动快照_{net_duration // 60}m",
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

    conflict = _try_reserve_game_launch(game_id, "native")
    if conflict is not None:
        return conflict

    try:
        game = get_game_by_id(game_id)
        if not game:
            _release_game_launch_reservation(game_id)
            return {"success": False, "message": "游戏记录不存在"}

        exe_path = game.get("executable_path")
        folder_path = game.get("folder_path")

        if not exe_path or not os.path.exists(exe_path):
            if folder_path and os.path.exists(folder_path):
                exes, *rest = fast_inspect_folder(folder_path, max_depth=2)
                exe_path = choose_best_executable(folder_path, exes)

        if not exe_path or not os.path.exists(exe_path):
            _release_game_launch_reservation(game_id)
            if folder_path and os.path.exists(folder_path):
                open_game_folder(folder_path)
                return {"success": True, "message": "未找到主程序，已为您打开游戏目录"}
            return {"success": False, "message": "游戏主程序与目录均不存在"}

        working_dir = os.path.dirname(os.path.abspath(exe_path))
        exe_name = Path(exe_path).name

        success, pid, hProcess = shell_launch(exe_path, working_dir=working_dir, show_cmd=SW_SHOWNORMAL)
        if not success:
            if IS_WINDOWS:
                os.startfile(exe_path)
            time.sleep(1.0)
            pid = find_game_pid_in_folder(folder_path or working_dir, exe_name)
            hProcess = None

        hJob = _create_tracking_job_object(hProcess=hProcess, pid=pid) if IS_WINDOWS else None
        start_time = time.time()
        with RUNNING_LOCK:
            RUNNING_GAMES[game_id] = {
                "pid": pid,
                "start_time": start_time,
                "exe": exe_name,
                "mode": "native",
                "phase": "running" if pid else "attaching",
                "folder_path": folder_path or working_dir
            }

        t = threading.Thread(
            target=monitor_game_pid,
            args=(game_id, pid, hProcess, start_time, working_dir, exe_name, folder_path),
            kwargs={"hJob": hJob},
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
        _release_game_launch_reservation(game_id)
        return {"success": False, "message": f"启动失败: {str(e)}"}


def launch_game_with_le(game_id: int) -> Dict[str, Any]:
    """Launches game via Locale Emulator (LEProc.exe) for Japanese Shift-JIS locale emulation."""
    set_last_active_game_id(game_id)
    conflict = _try_reserve_game_launch(game_id, "le")
    if conflict is not None:
        return conflict

    try:
        game = get_game_by_id(game_id)
        if not game:
            _release_game_launch_reservation(game_id)
            return {"success": False, "message": "游戏记录不存在"}

        le_exe = resolve_leproc_path()
        if not le_exe:
            _release_game_launch_reservation(game_id)
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
            _release_game_launch_reservation(game_id)
            return {"success": False, "message": "未找到游戏主程序"}

        working_dir = os.path.dirname(os.path.abspath(exe_path))
        exe_name = Path(exe_path).name

        success, le_pid, hLeProc = shell_launch(
            exe_path=le_exe,
            parameters=f'-run "{exe_path}"',
            working_dir=working_dir,
            show_cmd=SW_SHOWNORMAL
        )
        hJob = _create_tracking_job_object(hProcess=hLeProc, pid=le_pid) if IS_WINDOWS and success else None
        close_win32_handle(hLeProc)
        if not success:
            proc = subprocess.Popen(
                [le_exe, "-run", exe_path],
                cwd=working_dir,
                creationflags=CREATE_NO_WINDOW
            )
            hJob = _create_tracking_job_object(pid=proc.pid) if IS_WINDOWS else None

        time.sleep(1.0)
        job_pids = _get_job_pids(hJob)
        real_pid = (job_pids[0] if job_pids else None) or find_game_pid_in_folder(folder_path or working_dir, exe_name)
        start_time = time.time()

        with RUNNING_LOCK:
            RUNNING_GAMES[game_id] = {
                "pid": real_pid,
                "start_time": start_time,
                "exe": exe_name,
                "mode": "le",
                "phase": "running" if real_pid else "attaching",
                "folder_path": folder_path or working_dir
            }

        t = threading.Thread(
            target=monitor_game_pid,
            args=(game_id, real_pid, None, start_time, working_dir, exe_name, folder_path),
            kwargs={"hJob": hJob},
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
        _release_game_launch_reservation(game_id)
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
                subprocess.Popen(["explorer.exe", folder_path], creationflags=CREATE_NO_WINDOW)
                return True
    return False


def reveal_in_explorer(file_or_dir_path: str) -> bool:
    if file_or_dir_path and os.path.exists(file_or_dir_path):
        try:
            if IS_WINDOWS:
                subprocess.Popen(["explorer.exe", f'/select,"{file_or_dir_path}"'], creationflags=CREATE_NO_WINDOW)
                return True
            return open_game_folder(os.path.dirname(file_or_dir_path))
        except Exception:
            return open_game_folder(file_or_dir_path)
    return False


def _resolve_safe_last_loaded_trs(folder: Path) -> Optional[str]:
    """Reads lastLoadedTrsFile and validates path boundary + valid .json/.trs extension."""
    last_trs_path = folder / "lastLoadedTrsFile"
    if not last_trs_path.is_file():
        return None
    try:
        ref = last_trs_path.read_text(encoding="utf-8-sig", errors="ignore").strip()
        if not ref:
            return None
        cand = (folder / ref).resolve()
        folder_resolved = folder.resolve()
        if not is_subpath(str(cand), str(folder_resolved)):
            return None
        if not cand.is_file() or cand.suffix.lower() not in (".json", ".trs"):
            return None
        if cand.suffix.lower() == ".json" and not is_valid_translation_json(str(cand)):
            return None
        return str(cand)
    except Exception:
        return None


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

    if not has_trs:
        safe_trs = _resolve_safe_last_loaded_trs(folder)
        if safe_trs:
            has_trs = True
            trs_file = safe_trs

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
    is_mtool_engine = mtool_link.detect_engine_key(engine_type) is not None

    # v2.5: hook 必须与游戏主程序位数一致。
    _exe_for_bits = game.get("executable_path") or ""
    hook_path, exe_bitness, bitness_source = mtool_link.choose_hook(
        str(mtool_dir), engine_type, _exe_for_bits
    )
    hook_dll_name = hook_path.name
    hook_dll_exists = hook_path.is_file()

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
        "hook_dll": hook_dll_name,
        "hook_dll_exists": hook_dll_exists,
        "exe_bitness": exe_bitness,
        "bitness_source": bitness_source,
        "hook_label": mtool_link.describe_hook(engine_type, hook_path, exe_bitness)
    }


def _verify_mtool_binding(game_id: int, hook_name: str, game_folder: str, exe_name: str,
                          record_path: str, record_mtime_before: float,
                          resolver: Optional[Any] = None) -> None:
    """
    启动后校验 MTool 是否真的"关联"上了：
    首选判据 = hook DLL 是否加载进游戏进程（唯一可靠）；
    权限不足无法枚举时，退回看 Tool\\gameLaunchs 记录是否被 MTool 刷新。
    """
    def current_pid() -> Optional[int]:
        with RUNNING_LOCK:
            info = RUNNING_GAMES.get(game_id)
            pid = info.get("pid") if info else None
        if pid:
            return pid
        if resolver is not None:
            try:
                return resolver()
            except Exception:
                return None
        return find_game_pid_in_folder(game_folder, exe_name)

    try:
        loaded = mtool_link.wait_dll_loaded(current_pid, hook_name, timeout=30.0)
        associated = loaded
        detail = "hook 已载入游戏进程" if loaded else ""
        if loaded is None:
            try:
                mtime_now = os.path.getmtime(record_path) if os.path.exists(record_path) else 0.0
                associated = bool(mtime_now > record_mtime_before + 0.5)
                detail = "MTool 启动记录已刷新" if associated else "无法枚举模块，记录未刷新"
            except Exception:
                associated = None
                detail = "无法判定"
        elif loaded is False:
            detail = "hook 未载入游戏进程（注入失败）"

        with RUNNING_LOCK:
            if game_id in RUNNING_GAMES:
                RUNNING_GAMES[game_id]["mtool_associated"] = associated
                RUNNING_GAMES[game_id]["mtool_detail"] = detail
    except Exception as e:
        with RUNNING_LOCK:
            if game_id in RUNNING_GAMES:
                RUNNING_GAMES[game_id]["mtool_detail"] = f"校验异常: {e}"


def launch_game_with_mtool(game_id: int) -> Dict[str, Any]:
    """Launches game with MTool injection attached and normal visible window."""
    set_last_active_game_id(game_id)
    conflict = _try_reserve_game_launch(game_id, "mtool")
    if conflict is not None:
        return conflict

    try:
        game = get_game_by_id(game_id)
        if not game:
            _release_game_launch_reservation(game_id)
            return {"success": False, "message": "游戏记录不存在"}

        status = get_game_mtool_status(game_id)
        if not status.get("mtool_installed"):
            _release_game_launch_reservation(game_id)
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
            _release_game_launch_reservation(game_id)
            return {"success": False, "message": "未找到游戏主程序"}

        working_dir = os.path.dirname(os.path.abspath(exe_path))
        exe_name = Path(exe_path).name
        mtool_dir = Path(status["mtool_dir"])
        inject_exe = mtool_dir / "Tool" / "loaders" / "inject.exe"
        nw_exe = mtool_dir / "Tool" / "nw.exe"
        tool_dir = mtool_dir / "Tool"
        engine_type = game.get("engine_type", "") or ""

        if status.get("trs_file") and os.path.exists(status["trs_file"]):
            trs_name = os.path.basename(status["trs_file"])
            last_trs = os.path.join(working_dir, "lastLoadedTrsFile")
            try:
                with open(last_trs, "w", encoding="utf-8") as f:
                    f.write(trs_name)
            except Exception:
                pass

        # ---- v2.5：位数感知 hook + 复用/生成「与工具一同启动.bat」 ----
        game_folder = folder_path or working_dir
        hook_path, exe_bits, bitness_source = mtool_link.choose_hook(str(mtool_dir), engine_type, exe_path)
        bat_res = mtool_link.ensure_launch_bat(game_folder, exe_path, str(mtool_dir), engine_type)
        effective_hook = Path(bat_res.get("hook") or hook_path)
        hook_for_verify = effective_hook.name
        rec_path = mtool_link.launch_record_path(str(mtool_dir), exe_path)
        record_mtime_before = rec_path.stat().st_mtime if rec_path.is_file() else 0.0
        rec_res = mtool_link.ensure_launch_record(
            str(mtool_dir), exe_path, str(effective_hook), int(bat_res.get("bits") or exe_bits)
        )

        launch_method = ""
        launch_note = ""
        hJob = None

        if bat_res.get("action") != "failed" and bat_res.get("path"):
            if mtool_link.run_launch_bat(bat_res["path"], game_folder):
                launch_method = "bat"
                launch_note = {
                    "existing": "复用联动脚本",
                    "created": "已生成联动脚本",
                    "repaired": "已重建联动脚本",
                }.get(bat_res.get("action", ""), "联动脚本")
            else:
                bat_res["action"] = "failed"

        if launch_method != "bat":
            # 兜底：直接 inject（hook 已按位数选对）+ 拉起 MTool 面板
            if not (inject_exe.exists() and effective_hook.exists()):
                _release_game_launch_reservation(game_id)
                reason = bat_res.get("reason") or "缺少 inject.exe 或 hook DLL"
                return {"success": False, "message": f"无法启动 MTool 联动：{reason}"}

            success, inject_pid, hInject = shell_launch(
                exe_path=str(inject_exe),
                parameters=f'"{exe_path}" "{effective_hook}"',
                working_dir=working_dir,
                show_cmd=SW_SHOWNORMAL
            )
            if IS_WINDOWS and success:
                hJob = _create_tracking_job_object(hProcess=hInject, pid=inject_pid)
            close_win32_handle(hInject)
            if not success:
                proc = subprocess.Popen(
                    [str(inject_exe), str(exe_path), str(effective_hook)],
                    cwd=working_dir,
                    creationflags=CREATE_NO_WINDOW,
                    close_fds=True
                )
                if IS_WINDOWS:
                    hJob = _create_tracking_job_object(pid=proc.pid)
            launch_method = "inject"
            launch_note = f"直接注入（{bat_res.get('reason') or '无联动脚本'}）"

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

        # ---- 解析 MTool 真正注入的进程（可能被软链/复制到 Public 临时目录并改名）----
        launch_dir, launch_exe = game_folder, exe_name
        parsed_target = parse_mtool_launch_target(bat_res.get("path"))
        if parsed_target:
            launch_dir, launch_exe = parsed_target

        launch_names: List[str] = []
        for n in (launch_exe, exe_name, "MTool_Game.exe"):
            if n and n.lower() not in {x.lower() for x in launch_names}:
                launch_names.append(n)

        launch_roots: List[str] = []
        for d in (launch_dir, game_folder, working_dir):
            if d and d not in launch_roots:
                launch_roots.append(d)

        def _resolve_mtool_pid() -> Optional[int]:
            jp = _get_job_pids(hJob)
            if jp:
                return jp[0]
            return find_game_pid_multi(launch_names, launch_roots, allow_name_only=True)

        start_time = time.time()
        real_game_pid = _await_game_process(launch_dir, launch_exe, 3.0, resolver=_resolve_mtool_pid)

        with RUNNING_LOCK:
            RUNNING_GAMES[game_id] = {
                "pid": real_game_pid,
                "start_time": start_time,
                "exe": launch_exe,
                "mode": "mtool",
                "phase": "running" if real_game_pid else "attaching",
                "folder_path": game_folder,
                "launch_dir": launch_dir,
                "launch_exe": launch_exe,
                "hook_dll": hook_for_verify,
                "exe_bitness": int(bat_res.get("bits") or exe_bits),
                "launch_method": launch_method,
                "mtool_associated": None,
            }

        t = threading.Thread(
            target=monitor_game_pid,
            kwargs=dict(
                game_id=game_id,
                target_pid=real_game_pid,
                hProcess=None,
                start_time=start_time,
                working_dir=working_dir,
                exe_name=exe_name,
                game_folder=folder_path,
                attach_timeout=120.0,
                resolver=_resolve_mtool_pid,
                hJob=hJob,
            ),
            daemon=True
        )
        t.start()

        vt = threading.Thread(
            target=_verify_mtool_binding,
            args=(game_id, hook_for_verify, game_folder, exe_name, str(rec_path), record_mtime_before, _resolve_mtool_pid),
            daemon=True
        )
        vt.start()

        mode_name = "汉化" if status.get("has_translation") else "辅助"
        bits_txt = f"{int(bat_res.get('bits') or exe_bits)} 位"
        wait_note = "" if real_game_pid else "（注入中，进程出现后自动接管计时）"
        return {
            "success": True,
            "pid": real_game_pid,
            "mode": "mtool",
            "launch_method": launch_method,
            "hook_dll": hook_for_verify,
            "exe_bitness": int(bat_res.get("bits") or exe_bits),
            "bat_action": bat_res.get("action"),
            "record_written": rec_res.get("written"),
            "pending": not bool(real_game_pid),
            "message": f"成功以 MTool {mode_name}模式启动: {exe_name}（{bits_txt} · {hook_for_verify} · {launch_note}）{wait_note}"
        }
    except Exception as e:
        _release_game_launch_reservation(game_id)
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

SAVE_BACKUP_EXCLUDED_DIRS = {
    "unity", "crashes", "logs", "il2cpp",
    "shadercache", "assetbundles", "unitywebdata",
    "temp", "cache", "caches", "gpucache", "code cache"
}

MAX_NON_SAVE_BACKUP_FILE_BYTES = 64 * 1024 * 1024  # 64 MB


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
                    dirs[:] = [d for d in dirs if d.lower() not in SAVE_BACKUP_EXCLUDED_DIRS]
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
        excluded_dirs = SAVE_BACKUP_EXCLUDED_DIRS
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(save_dir):
                if is_root_save:
                    dirs.clear()
                else:
                    dirs[:] = [d for d in dirs if d.lower() not in excluded_dirs]
                for fn in files:
                    low = fn.lower()
                    if low in skip_unity_logs or low.endswith((".log", ".tmp", ".bak")):
                        continue
                    if is_root_save:
                        if not (low.startswith("save") and low.endswith(SAVE_FILE_EXTENSIONS)):
                            continue
                    fp = Path(root) / fn
                    try:
                        fsize = fp.stat().st_size
                    except Exception:
                        continue
                    # Skip non-save giant files (> 64MB) such as uncategorized bundles/caches
                    if fsize > MAX_NON_SAVE_BACKUP_FILE_BYTES and not low.endswith(SAVE_FILE_EXTENSIONS):
                        continue
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
        from config import merge_masked_secrets
        cfg.update(merge_masked_secrets(custom_cfg, cfg))
    base_url = (cfg.get("webdav_url") or "").strip().rstrip("/")
    root_sub = (cfg.get("webdav_root_path") or "").strip().strip("/")
    if base_url and root_sub and not base_url.lower().endswith("/" + root_sub.lower()):
        base_url = f"{base_url}/{root_sub}"
    username = (cfg.get("webdav_username") or "").strip()
    password = (cfg.get("webdav_password") or "").strip()
    auth = (username, password) if username or password else None
    client = httpx.Client(auth=auth, timeout=30.0, follow_redirects=True)
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
    """Uploads a local save backup ZIP file to the configured WebDAV directory via streaming file handle."""
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
                r = client.put(target_url, content=f, headers={"Content-Type": "application/zip"})
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
