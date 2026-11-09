"""
Magpie integration (v3.2)

Magpie 是一款 GPLv3 的窗口放大/全屏工具，没有对外的"缩放指定窗口"命令行。
但它把全局热键注册在一个消息窗口（窗口类名 Magpie_Hotkey）上，而该窗口的
WndProc 处理 WM_HOTKEY 时只校验 wParam 的范围，不校验消息来源：

    PostMessage(Magpie_Hotkey, WM_HOTKEY, 0 /* Scale */, 0)

等价于用户按下了"缩放"热键，Magpie 会对**当前前台窗口**开始缩放。

因此这里的流程固定为：
    找游戏主窗口 -> 强制置前台 -> 校验前台确实是它 -> 投递热键 -> 检查是否出现缩放窗口

只调用用户本机已安装的 Magpie.exe，不打包、不分发其代码。
"""

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_IS_WIN = sys.platform == "win32"
IS_WINDOWS = _IS_WIN
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if _IS_WIN else 0

WM_HOTKEY = 0x0312
SHORTCUT_SCALE = 0
MAGPIE_HOTKEY_CLASS = "Magpie_Hotkey"
MAGPIE_PROCESS = "Magpie.exe"

SW_RESTORE = 9
TH32CS_SNAPPROCESS = 0x00000002

_exe_cache: Optional[str] = None
_exe_checked = False
_exe_cache_cfg: Optional[str] = None


# ---------------------------------------------------------------- win32 helpers
def _user32():
    return ctypes.windll.user32


def _iter_message_windows():
    """遍历 message-only 窗口（EnumWindows 看不到它们）。"""
    u = _user32()
    hwnd_message = ctypes.c_void_p(-3)
    h = 0
    while True:
        h = u.FindWindowExW(hwnd_message, ctypes.c_void_p(h), None, None)
        if not h:
            return
        yield h


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32().GetClassNameW(hwnd, buf, 256)
    return buf.value


def _window_pid(hwnd: int) -> int:
    pid = wt.DWORD()
    _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _rect(hwnd: int):
    r = wt.RECT()
    _user32().GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def find_hotkey_window() -> int:
    """返回 Magpie 热键消息窗口的 HWND，Magpie 未运行时返回 0。"""
    if not IS_WINDOWS:
        return 0
    try:
        for h in _iter_message_windows():
            if _class_name(h) == MAGPIE_HOTKEY_CLASS:
                return int(h)
    except Exception:
        pass
    return 0


def _magpie_pids() -> Set[int]:
    """
    微秒级纯内存枚举 Magpie.exe 进程 PID（优先使用 CreateToolhelp32Snapshot，
    彻底避免频繁拉起 tasklist.exe 子进程导致的阻塞与闪黑窗）。
    """
    pids: Set[int] = set()
    if not IS_WINDOWS:
        return pids
    h = find_hotkey_window()
    if h:
        pids.add(_window_pid(h))

    snap_ok = False
    try:
        from core.launcher import PROCESSENTRY32W, INVALID_HANDLE_VALUE
        k32 = ctypes.windll.kernel32
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap and snap != INVALID_HANDLE_VALUE:
            try:
                pe = PROCESSENTRY32W()
                pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                target_low = MAGPIE_PROCESS.lower()
                if k32.Process32FirstW(snap, ctypes.byref(pe)):
                    snap_ok = True
                    while True:
                        if pe.szExeFile.lower() == target_low:
                            pids.add(int(pe.th32ProcessID))
                        if not k32.Process32NextW(snap, ctypes.byref(pe)):
                            break
            finally:
                try:
                    k32.CloseHandle(snap)
                except Exception:
                    pass
    except Exception:
        pass

    if not snap_ok and not pids:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {MAGPIE_PROCESS}", "/FO", "CSV", "/NH"],
                capture_output=True,
                timeout=6,
                creationflags=_NO_WINDOW,
            ).stdout.decode("gbk", errors="ignore")
            for line in out.splitlines():
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) >= 2 and parts[1].isdigit():
                    pids.add(int(parts[1]))
        except Exception:
            pass
    return pids


def _scaling_window_visible() -> bool:
    """Magpie 缩放窗口 = 可见 + 置顶 + 面积接近整个屏幕。"""
    if not IS_WINDOWS:
        return False
    pids = _magpie_pids()
    if not pids:
        return False
    try:
        screen_w = _user32().GetSystemMetrics(0)
        screen_h = _user32().GetSystemMetrics(1)
    except Exception:
        return False
    screen_area = max(1, screen_w * screen_h)
    found = [False]

    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def _cb(hwnd, _):
        try:
            if not _user32().IsWindowVisible(hwnd):
                return True
            if _window_pid(hwnd) not in pids:
                return True
            ex = _user32().GetWindowLongW(hwnd, -20)
            if not (ex & 0x00000008):  # WS_EX_TOPMOST
                return True
            _, _, w, h = _rect(hwnd)
            if w * h >= screen_area * 0.8:
                found[0] = True
                return False
        except Exception:
            pass
        return True

    try:
        _user32().EnumWindows(WNDENUMPROC(_cb), 0)
    except Exception:
        return False
    return found[0]


# ---------------------------------------------------------------- installation
def _candidate_dirs() -> List[Path]:
    dirs: List[Path] = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            dirs.append(Path(base) / "Magpie")
            dirs.append(Path(base) / "Programs" / "Magpie")

    # 用户习惯把工具和游戏放一起（例如 E:\ACG\Magpie_v0.10.2_2）
    try:
        from config import load_config
        for gd in (load_config().get("game_directories") or [])[:8]:
            base = Path(str(gd))
            for folder in (base, base.parent):
                try:
                    if not folder.is_dir():
                        continue
                    for child in folder.glob("Magpie*"):
                        if child.is_dir():
                            dirs.append(child)
                except Exception:
                    continue
    except Exception:
        pass
    return dirs


def detect_magpie(configured_path: str = "", refresh: bool = False) -> Optional[str]:
    """定位 Magpie.exe。configured_path 可以是 exe 或所在目录。当 configured_path 变化时自动刷新缓存。"""
    global _exe_cache, _exe_checked, _exe_cache_cfg
    norm_cfg = (configured_path or "").strip()
    if _exe_checked and not refresh and norm_cfg == _exe_cache_cfg:
        if _exe_cache and Path(_exe_cache).is_file():
            return _exe_cache
        return None
    _exe_checked = True
    _exe_cache_cfg = norm_cfg
    _exe_cache = None

    def _accept(p: Optional[Path]) -> Optional[str]:
        if not p:
            return None
        try:
            if p.is_dir():
                p = p / MAGPIE_PROCESS
            if p.is_file() and p.name.lower() == MAGPIE_PROCESS.lower():
                return str(p)
        except Exception:
            return None
        return None

    if norm_cfg:
        got = _accept(Path(norm_cfg))
        if got:
            _exe_cache = got
            return got

    got = _accept(Path(shutil_which("Magpie") or ""))
    if got:
        _exe_cache = got
        return got

    for d in _candidate_dirs():
        exe = d / MAGPIE_PROCESS
        try:
            if exe.is_file():
                _exe_cache = str(exe)
                return _exe_cache
        except Exception:
            continue
    return None


def shutil_which(name: str) -> Optional[str]:
    try:
        import shutil
        return shutil.which(name)
    except Exception:
        return None


# ---------------------------------------------------------------- operations
def get_status(refresh: bool = False) -> Dict[str, Any]:
    from config import load_config
    cfg = load_config()
    exe = detect_magpie(str(cfg.get("magpie_path") or ""), refresh=refresh)
    hwnd = find_hotkey_window()
    return {
        "installed": bool(exe),
        "path": exe or "",
        "running": bool(hwnd),
        "scaling": _scaling_window_visible(),
        "auto_scale": bool(cfg.get("magpie_auto_scale", False)),
        "auto_scope": cfg.get("magpie_auto_scope", "bigscreen"),
        "auto_delay": int(cfg.get("magpie_auto_delay", 8) or 8),
        "autostart": bool(cfg.get("magpie_autostart", True)),
    }


def ensure_running(configured_path: str = "", timeout: float = 12.0) -> Dict[str, Any]:
    """确保 Magpie 在托盘里运行（-st 启动）。"""
    if not IS_WINDOWS:
        return {"success": False, "message": "仅支持 Windows"}

    hwnd = find_hotkey_window()
    if hwnd:
        return {"success": True, "started": False, "message": "Magpie 已在运行"}

    exe = detect_magpie(configured_path, refresh=True)
    if not exe:
        return {
            "success": False,
            "message": "未找到 Magpie.exe，请在设置中指定路径",
        }

    try:
        proc = subprocess.Popen(
            [exe, "-st"],
            cwd=str(Path(exe).parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=_NO_WINDOW,
        )
    except Exception as e:
        return {"success": False, "message": f"启动 Magpie 失败: {e}"}

    deadline = time.time() + max(3.0, timeout)
    while time.time() < deadline:
        if find_hotkey_window():
            return {"success": True, "started": True, "message": "已启动 Magpie（托盘）"}
        if proc.poll() is not None:
            return {
                "success": False,
                "message": "Magpie 启动后立即退出，可能缺少 .NET / WebView2 运行时",
            }
        time.sleep(0.3)

    return {"success": False, "message": "Magpie 启动超时"}


def _all_pids(pid: int) -> Set[int]:
    pids = {int(pid)}
    try:
        from core.gamepad import _descendant_pids  # pylint: disable=import-outside-toplevel
        pids |= set(_descendant_pids({int(pid)}))
    except Exception:
        pass
    return pids


def find_game_window(pid: int) -> int:
    """按 PID（含子进程）找面积最大的可见顶层窗口。"""
    if not IS_WINDOWS or not pid:
        return 0
    pids = _all_pids(pid)
    best = [0, 0]

    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def _cb(hwnd, _):
        try:
            if not _user32().IsWindowVisible(hwnd):
                return True
            if _window_pid(hwnd) not in pids:
                return True
            ex = _user32().GetWindowLongW(hwnd, -20)
            if ex & 0x00000080:  # WS_EX_TOOLWINDOW
                return True
            _, _, w, h = _rect(hwnd)
            area = w * h
            if area > best[1]:
                best[0], best[1] = int(hwnd), area
        except Exception:
            pass
        return True

    try:
        _user32().EnumWindows(WNDENUMPROC(_cb), 0)
    except Exception:
        return 0
    return best[0]


def _wait_foreground(hwnd: int, timeout: float = 1.2) -> bool:
    """SetForegroundWindow 是异步生效的，轮询确认真正的焦点。"""
    u = _user32()
    end = time.time() + timeout
    while time.time() < end:
        if u.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.05)
    return False


def focus_window(hwnd: int) -> bool:
    """把窗口拉到前台，成功返回 True。使用 try...finally 保证 AttachThreadInput 必然解绑。"""
    if not hwnd:
        return False
    u = _user32()
    k = ctypes.windll.kernel32
    try:
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.15)
        if u.GetForegroundWindow() == hwnd:
            return True

        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
        if _wait_foreground(hwnd, 0.8):
            return True

        # 前台锁：临时把当前前台线程附加到本线程
        fg = u.GetForegroundWindow()
        tid_fg = u.GetWindowThreadProcessId(fg, None)
        tid_cur = k.GetCurrentThreadId()
        if tid_fg and tid_fg != tid_cur:
            attached = bool(u.AttachThreadInput(tid_cur, tid_fg, True))
            try:
                u.BringWindowToTop(hwnd)
                u.SetForegroundWindow(hwnd)
            finally:
                if attached:
                    u.AttachThreadInput(tid_cur, tid_fg, False)

        return _wait_foreground(hwnd, 1.0)
    except Exception:
        return False


def trigger_scale() -> Dict[str, Any]:
    """向 Magpie 投递一次「缩放」热键（作用于当前前台窗口）。"""
    hwnd = find_hotkey_window()
    if not hwnd:
        return {"success": False, "message": "Magpie 未运行"}
    try:
        ok = bool(_user32().PostMessageW(hwnd, WM_HOTKEY, SHORTCUT_SCALE, 0))
    except Exception as e:
        return {"success": False, "message": f"投递热键失败: {e}"}
    if not ok:
        return {"success": False, "message": "投递热键被系统拒绝"}
    return {"success": True, "message": "已请求 Magpie 缩放"}


def scale_game(game_id: int, wait_window: float = 20.0, settle: float = 0.0) -> Dict[str, Any]:
    """
    对指定游戏发起 Magpie 全屏。返回:
      success   流程是否走完
      scaled    是否检测到 Magpie 缩放窗口
      message   给用户看的一句话
    """
    from config import load_config
    cfg = load_config()

    if not bool(cfg.get("magpie_enabled", True)):
        return {"success": False, "scaled": False, "message": "Magpie 集成已在设置中关闭"}

    pid = 0
    try:
        from core.launcher import get_running_games_info
        info = get_running_games_info().get(game_id) or {}
        pid = int(info.get("pid") or 0)
    except Exception:
        pid = 0

    if not pid:
        return {"success": False, "scaled": False, "message": "游戏未在运行，无法全屏"}

    deadline = time.time() + max(2.0, wait_window)
    hwnd = 0
    while time.time() < deadline:
        hwnd = find_game_window(pid)
        if hwnd:
            break
        time.sleep(0.5)

    if not hwnd:
        return {"success": False, "scaled": False, "message": "还没找到游戏窗口"}

    if not focus_window(hwnd):
        return {
            "success": False,
            "scaled": False,
            "message": "无法把游戏窗口切到前台（可能有管理员权限差异）",
        }

    time.sleep(0.35)
    if _user32().GetForegroundWindow() != hwnd:
        # 有可能刚被别的窗口抢了焦点，再抢一次；仍失败才放弃，避免误缩放别的窗口
        if not focus_window(hwnd):
            return {"success": False, "scaled": False, "message": "游戏窗口未处于前台，已取消缩放"}
        time.sleep(0.2)

    auto_start = bool(cfg.get("magpie_autostart", True))
    if not find_hotkey_window():
        if not auto_start:
            return {"success": False, "scaled": False, "message": "Magpie 未运行，请先启动它"}
        started = ensure_running(str(cfg.get("magpie_path") or ""))
        if not started.get("success"):
            return {"success": False, "scaled": False, "message": started.get("message", "Magpie 启动失败")}
        time.sleep(0.8)
        if not focus_window(hwnd):
            return {"success": False, "scaled": False, "message": "Magpie 启动后游戏窗口失去前台"}

    if settle > 0:
        time.sleep(settle)

    res = trigger_scale()
    if not res.get("success"):
        return {"success": False, "scaled": False, "message": res.get("message", "缩放失败")}

    # 给 Magpie 一点时间创建缩放窗口
    scaled = False
    for _ in range(12):
        time.sleep(0.25)
        if _scaling_window_visible():
            scaled = True
            break

    if scaled:
        return {"success": True, "scaled": True, "message": "已用 Magpie 全屏"}
    return {
        "success": True,
        "scaled": False,
        "message": "已发送缩放请求，但未检测到 Magpie 全屏（游戏可能已是独占全屏）",
    }


def auto_scale_after_launch(game_id: int, delay: int = 8, pid_timeout: float = 90.0) -> Dict[str, Any]:
    """
    启动游戏后自动 Magpie 全屏：
      等 PID 出现 -> 等窗口出现（最多 30s）-> 再等 delay 秒 -> 缩放
    延迟放在"窗口出现"之后，MTool 注入慢也不会踩空。
    """
    from core.launcher import get_running_games_info

    deadline = time.time() + max(10.0, pid_timeout)
    pid = 0
    while time.time() < deadline:
        info = get_running_games_info().get(game_id) or {}
        pid = int(info.get("pid") or 0)
        if pid:
            break
        time.sleep(0.5)

    if not pid:
        return {"success": False, "scaled": False, "message": "等待游戏进程超时"}

    win_deadline = time.time() + 30.0
    while time.time() < win_deadline:
        if find_game_window(pid):
            break
        time.sleep(0.5)

    if delay > 0:
        time.sleep(float(delay))

    return scale_game(game_id, wait_window=10.0)


def auto_scale_async(game_id: int, delay: int = 8) -> None:
    def _run():
        try:
            res = auto_scale_after_launch(game_id, delay=delay)
            print(f"[Magpie] auto scale game {game_id}: {res.get('message')}")
        except Exception as e:
            print(f"[Magpie] auto scale error: {e}")

    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------- presets (v2.8)
# Magpie 只在启动时读取配置，运行中改文件不会生效（实测），
# 所以切换预设 = 停掉 Magpie -> 写配置 -> 重新拉起 -> 如果之前在缩放就恢复现场。
MAGPIE_PRESETS = [
    {
        "id": "anime",
        "name": "动画 / 立绘",
        "desc": "Anime4K · 线条干净，2D 立绘与动画风首选",
        "mode": "Anime4K",
        "capture": 0,
        "three_d": False,
        "direct_flip_off": False,
    },
    {
        "id": "pixel",
        "name": "像素 / RPG",
        "desc": "整数倍 2x · 像素游戏不糊边，RPG Maker 最稳",
        "mode": "Integer Scale 2x",
        "capture": 0,
        "three_d": False,
        "direct_flip_off": False,
    },
    {
        "id": "sharp",
        "name": "通用锐利",
        "desc": "Lanczos · 传统插值，擅长保留锐利边缘",
        "mode": "Lanczos",
        "capture": 0,
        "three_d": False,
        "direct_flip_off": False,
    },
    {
        "id": "threed",
        "name": "3D / 性能",
        "desc": "FSR · 3D 游戏放大，开销低、帧率友好",
        "mode": "FSR",
        "capture": 0,
        "three_d": True,
        "direct_flip_off": False,
    },
    {
        "id": "crt",
        "name": "复古 CRT",
        "desc": "CRT-Geom · 扫描线与曲面，老游戏味道",
        "mode": "CRT-Geom",
        "capture": 0,
        "three_d": False,
        "direct_flip_off": False,
    },
    {
        "id": "compat",
        "name": "兼容捕获",
        "desc": "Desktop Duplication + Lanczos · 抓不到画面时用",
        "mode": "Lanczos",
        "capture": 1,
        "three_d": False,
        "direct_flip_off": True,
    },
]


def magpie_config_path() -> Optional[str]:
    """Magpie 配置路径：%LOCALAPPDATA%\\Magpie\\config\\v<N>\\config.json（取最高版本）。"""
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Magpie" / "config"
    try:
        if not base.is_dir():
            return None
        versions = []
        for d in base.iterdir():
            if d.is_dir() and d.name.startswith("v") and d.name[1:].isdigit():
                versions.append((int(d.name[1:]), d))
        for _, d in sorted(versions, reverse=True):
            f = d / "config.json"
            if f.is_file():
                return str(f)
    except Exception:
        pass
    return None


def log_magpie_error(message: str) -> None:
    try:
        from config import DATA_DIR
        with open(DATA_DIR / "magpie.log", "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


def _read_magpie_config() -> Optional[Dict[str, Any]]:
    path = magpie_config_path()
    if not path:
        return None
    try:
        import json
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_magpie_config(cfg: Dict[str, Any]) -> bool:
    import json
    path = magpie_config_path()
    if not path:
        return False
    try:
        p = Path(path)
        try:
            p.with_suffix(".json.bak").write_bytes(p.read_bytes())
        except Exception:
            pass
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=4), encoding="utf-8")
        return True
    except Exception as e:
        log_magpie_error("write config failed: %s" % e)
        return False


def stop_magpie(timeout: float = 8.0) -> bool:
    """强制结束 Magpie，并等它真正退出（否则退出时会用内存里的旧配置覆盖文件）。"""
    if not IS_WINDOWS:
        return False
    try:
        subprocess.run(
            ["taskkill", "/IM", MAGPIE_PROCESS, "/F"],
            capture_output=True,
            timeout=6,
            creationflags=_NO_WINDOW,
        )
    except Exception:
        pass
    end = time.time() + timeout
    while time.time() < end:
        if not find_hotkey_window() and not _magpie_pids():
            return True
        time.sleep(0.25)
    return not find_hotkey_window()


def restart_tray(configured_path: str = "", timeout: float = 10.0) -> Dict[str, Any]:
    """重启 Magpie 托盘进程（先无窗口终止旧进程再以 -st 拉起）。"""
    stop_magpie(timeout=min(6.0, timeout))
    return ensure_running(configured_path=configured_path, timeout=timeout)


def get_presets() -> Dict[str, Any]:
    cfg = _read_magpie_config()
    modes: List[str] = []
    current = None
    if cfg:
        modes = [str(m.get("name", "")) for m in (cfg.get("scalingModes") or [])]
        profiles = cfg.get("profiles") or []
        if profiles:
            current = profiles[0].get("scalingMode")

    mode_name = ""
    if isinstance(current, int) and 0 <= current < len(modes):
        mode_name = modes[current]

    active = "custom"
    if mode_name:
        for p in MAGPIE_PRESETS:
            if p["mode"].lower() == mode_name.lower():
                active = p["id"]
                break

    available = {m.lower() for m in modes}
    presets = []
    for p in MAGPIE_PRESETS:
        item = dict(p)
        item["available"] = p["mode"].lower() in available
        presets.append(item)

    return {
        "presets": presets,
        "active": active,
        "mode_name": mode_name,
        "config_path": magpie_config_path() or "",
    }


def _latest_running_game_id() -> int:
    try:
        from core.launcher import get_running_games_info
        running = get_running_games_info()
        if running:
            return int(max(running.items(), key=lambda kv: kv[1].get("start_time", 0))[0])
    except Exception:
        pass
    return 0


def apply_preset(preset_id: str) -> Dict[str, Any]:
    """切换 Magpie 全局缩放预设（会重启 Magpie，必要时恢复当前的全屏状态）。"""
    from config import load_config, save_config

    preset = next((p for p in MAGPIE_PRESETS if p["id"] == preset_id), None)
    if not preset:
        return {"success": False, "message": "未知预设: %s" % preset_id}

    cfg = _read_magpie_config()
    if not cfg:
        return {"success": False, "message": "未找到 Magpie 配置，请先运行一次 Magpie"}

    modes = [str(m.get("name", "")) for m in (cfg.get("scalingModes") or [])]
    idx = next((i for i, n in enumerate(modes) if n.lower() == preset["mode"].lower()), -1)
    if idx < 0:
        return {"success": False, "message": "Magpie 中没有「%s」缩放模式" % preset["mode"]}

    profiles = cfg.get("profiles") or []
    if not profiles:
        return {"success": False, "message": "Magpie 配置里没有默认 profile"}

    was_scaling = _scaling_window_visible()
    was_running = bool(find_hotkey_window())

    if was_running:
        if not stop_magpie():
            return {"success": False, "message": "无法停止 Magpie，请手动退出后重试"}
        time.sleep(0.5)

    default = profiles[0]
    default["scalingMode"] = idx
    default["captureMethod"] = int(preset.get("capture", 0))
    default["3DGameMode"] = bool(preset.get("three_d", False))
    default["disableDirectFlip"] = bool(preset.get("direct_flip_off", False))

    # 顺手的"妥善配置"：最大化窗口也允许缩放；不要假装独占全屏（会让部分游戏起不来）
    cfg["allowScalingMaximized"] = True
    cfg["simulateExclusiveFullscreen"] = False
    cfg["showNotifyIcon"] = True

    if not _write_magpie_config(cfg):
        return {"success": False, "message": "写入 Magpie 配置失败"}

    try:
        c = load_config()
        c["magpie_active_preset"] = preset_id
        save_config(c)
    except Exception:
        pass

    restarted = False
    if was_running:
        r = ensure_running(str(load_config().get("magpie_path") or ""))
        restarted = bool(r.get("success"))
        if restarted:
            time.sleep(0.8)
            if was_scaling:
                gid = _latest_running_game_id()
                if gid:
                    scale_game(gid, wait_window=6.0)

    return {
        "success": True,
        "restarted": restarted,
        "preset": preset,
        "mode_name": preset["mode"],
        "message": "已切换到「%s」%s" % (preset["name"], "，Magpie 已重启" if restarted else ""),
    }
