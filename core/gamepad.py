"""
手柄支持 (v3.2) —— XInput → 键盘注入，面向 RPG Maker 系列优化。

为什么不是"游戏原生支持"
------------------------
RPG Maker MV/MZ 是 NW.js/Chromium 应用，只监听键盘事件（Z/X/Shift/方向键），
完全不认 Gamepad API；VX Ace / XP（RGSS）同样只读键盘。所以手柄要能用，
必须在系统层把它翻译成按键。

实现要点
--------
* **零依赖**：ctypes 直接调 XInput1_4.dll，不需要 pygame / vgamepad。
* **只喂给游戏**：仅当 ACG Vault 启动的游戏窗口在前台时才发键；切走/退出立即
  松开所有按键，不会在浏览器、聊天窗里乱按方向键。
* **按引擎换键位**：MV/MZ 用 Z/X，RGSS 用 C/B，各自有独立预设。
* **摇杆不粘滞**：0.35 死区，首次按下立即触发，按住走连续（RPG 走格子需要
  "按住即持续移动"，而不是反复点按）。
* **状态可观测**：实时按钮/摇杆状态供设置页自检，不用靠猜。
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------
# XInput
# ---------------------------------------------------------
XINPUT_GAMEPAD_DPAD_UP = 0x0001
XINPUT_GAMEPAD_DPAD_DOWN = 0x0002
XINPUT_GAMEPAD_DPAD_LEFT = 0x0004
XINPUT_GAMEPAD_DPAD_RIGHT = 0x0008
XINPUT_GAMEPAD_START = 0x0010
XINPUT_GAMEPAD_BACK = 0x0020
XINPUT_GAMEPAD_LEFT_THUMB = 0x0040
XINPUT_GAMEPAD_RIGHT_THUMB = 0x0080
XINPUT_GAMEPAD_LEFT_SHOULDER = 0x0100
XINPUT_GAMEPAD_RIGHT_SHOULDER = 0x0200
XINPUT_GAMEPAD_A = 0x1000
XINPUT_GAMEPAD_B = 0x2000
XINPUT_GAMEPAD_X = 0x4000
XINPUT_GAMEPAD_Y = 0x8000

BUTTON_BITS = {
    "up": XINPUT_GAMEPAD_DPAD_UP,
    "down": XINPUT_GAMEPAD_DPAD_DOWN,
    "left": XINPUT_GAMEPAD_DPAD_LEFT,
    "right": XINPUT_GAMEPAD_DPAD_RIGHT,
    "start": XINPUT_GAMEPAD_START,
    "back": XINPUT_GAMEPAD_BACK,
    "lthumb": XINPUT_GAMEPAD_LEFT_THUMB,
    "rthumb": XINPUT_GAMEPAD_RIGHT_THUMB,
    "lb": XINPUT_GAMEPAD_LEFT_SHOULDER,
    "rb": XINPUT_GAMEPAD_RIGHT_SHOULDER,
    "a": XINPUT_GAMEPAD_A,
    "b": XINPUT_GAMEPAD_B,
    "x": XINPUT_GAMEPAD_X,
    "y": XINPUT_GAMEPAD_Y,
}
BUTTON_ORDER = ["a", "b", "x", "y", "lb", "rb", "lt", "rt", "start", "back", "up", "down", "left", "right", "lthumb", "rthumb"]


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_ulong), ("Gamepad", XINPUT_GAMEPAD)]


def _load_xinput():
    if not IS_WINDOWS:
        return None, ""
    for dll in ("XInput1_4.dll", "XInput1_3.dll", "XInput9_1_0.dll"):
        try:
            lib = ctypes.WinDLL(dll)
            lib.XInputGetState.argtypes = [ctypes.c_ulong, ctypes.POINTER(XINPUT_STATE)]
            lib.XInputGetState.restype = ctypes.c_ulong
            return lib, dll
        except Exception:
            continue
    return None, ""


XINPUT, XINPUT_DLL = _load_xinput()
ERROR_DEVICE_NOT_CONNECTED = 1167
XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE = 7849  # 官方默认值，仅作参考


def _norm_stick(val: int) -> float:
    """对称归一化摇杆轴 (-32768 ~ 32767 -> -1.0 ~ 1.0)。"""
    v = int(val)
    if v >= 0:
        return max(-1.0, min(1.0, v / 32767.0))
    return max(-1.0, min(1.0, v / 32768.0))


# ---------------------------------------------------------
# 虚拟键
# ---------------------------------------------------------
VK = {
    "BACK": 0x08, "TAB": 0x09, "ENTER": 0x0D, "SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12,
    "ESC": 0x1B, "SPACE": 0x20, "PAGEUP": 0x21, "PAGEDOWN": 0x22, "END": 0x23, "HOME": 0x24,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28, "PRTSC": 0x2C, "INS": 0x2D, "DEL": 0x2E,
}
for _i in range(1, 13):
    VK[f"F{_i}"] = 0x6F + _i
for _ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
    VK[_ch] = ord(_ch)

KEY_LABELS = {
    "Z": "Z", "X": "X", "C": "C", "B": "B", "A": "A", "S": "S", "D": "D",
    "ENTER": "Enter", "ESC": "Esc", "SPACE": "空格", "TAB": "Tab",
    "SHIFT": "Shift(加速)", "CTRL": "Ctrl(跳过)", "ALT": "Alt",
    "UP": "↑", "DOWN": "↓", "LEFT": "←", "RIGHT": "→",
    "PAGEUP": "PageUp", "PAGEDOWN": "PageDown", "F12": "F12", "F11": "F11", "F10": "F10",
}

# ---------------------------------------------------------
# 动作与预设
# ---------------------------------------------------------
ACTIONS = ["up", "down", "left", "right", "confirm", "cancel", "dash", "menu",
           "pageup", "pagedown", "ff", "enter", "screenshot"]

ACTION_LABELS = {
    "up": "上", "down": "下", "left": "左", "right": "右",
    "confirm": "确定/互动", "cancel": "取消/返回", "dash": "加速(跑步)",
    "menu": "菜单", "pageup": "PageUp", "pagedown": "PageDown",
    "ff": "跳过/快进", "enter": "Enter", "screenshot": "游戏截图",
}

PROFILES: Dict[str, Dict[str, str]] = {
    "rm_mv_mz": {
        "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
        "confirm": "Z", "cancel": "X", "dash": "SHIFT", "menu": "ESC",
        "pageup": "PAGEUP", "pagedown": "PAGEDOWN", "ff": "CTRL",
        "enter": "ENTER", "screenshot": "F12",
    },
    "rm_rgss": {
        "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
        "confirm": "C", "cancel": "B", "dash": "SHIFT", "menu": "ESC",
        "pageup": "PAGEUP", "pagedown": "PAGEDOWN", "ff": "CTRL",
        "enter": "ENTER", "screenshot": "F12",
    },
    "wolf": {
        "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
        "confirm": "Z", "cancel": "X", "dash": "SHIFT", "menu": "ESC",
        "pageup": "PAGEUP", "pagedown": "PAGEDOWN", "ff": "CTRL",
        "enter": "ENTER", "screenshot": "F12",
    },
    "generic": {
        "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
        "confirm": "ENTER", "cancel": "ESC", "dash": "SHIFT", "menu": "ESC",
        "pageup": "PAGEUP", "pagedown": "PAGEDOWN", "ff": "CTRL",
        "enter": "ENTER", "screenshot": "F12",
    },
}
PROFILE_LABELS = {
    "rm_mv_mz": "RPG Maker MV / MZ（Z 确定 · X 取消）",
    "rm_rgss": "RPG Maker XP / VX / VX Ace（C 确定 · B 取消）",
    "wolf": "WOLF RPG Editor（Z / X）",
    "generic": "通用（Enter 确定 · Esc 取消）",
}

DEFAULT_BUTTONS = {
    "a": "confirm", "b": "cancel", "x": "dash", "y": "menu",
    "lb": "pageup", "rb": "ff", "lt": "dash", "rt": "ff",
    "start": "enter", "back": "screenshot",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "lthumb": "", "rthumb": "",
}

HOLD_ACTIONS = {"up", "down", "left", "right", "confirm", "cancel", "dash",
                "menu", "pageup", "pagedown", "ff", "enter"}
EDGE_ACTIONS = {"screenshot"}

DEFAULT_SETTINGS = {
    "gamepad_enabled": True,
    "gamepad_deadzone": 0.35,
    "gamepad_profile": "auto",
    "gamepad_back_screenshot": True,
    "gamepad_bindings": {},
    "gamepad_per_game": {},
}


def engine_to_profile(engine_type: Optional[str]) -> str:
    t = (engine_type or "").lower()
    if "wolf" in t:
        return "wolf"
    if any(k in t for k in ("vx", "xp", "rgss")):
        return "rm_rgss"
    if "mv" in t or "mz" in t or "rpg maker" in t:
        return "rm_mv_mz"
    return "generic"


# ---------------------------------------------------------
# SendInput
# ---------------------------------------------------------
if IS_WINDOWS:
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", ctypes.c_ulong),
            ("wParamL", ctypes.c_ushort),
            ("wParamH", ctypes.c_ushort),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTUNION)]

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1
    EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x2C}

    _user32 = ctypes.windll.user32
    _user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
    _user32.SendInput.restype = ctypes.c_uint


def _send_vk(vk: int, keyup: bool = False) -> None:
    if not IS_WINDOWS:
        return
    scan = _user32.MapVirtualKeyW(vk, 0)
    flags = KEYEVENTF_KEYUP if keyup else 0
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.u.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


# ---------------------------------------------------------
# 前台进程判定
# ---------------------------------------------------------
def _foreground_pid() -> Optional[int]:
    if not IS_WINDOWS:
        return None
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.c_ulong(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:
        return None


def _descendant_pids(root_pids: Set[int]) -> Set[int]:
    """把游戏进程派生的子进程也算作"游戏"，避免启动器把 PID 交给子进程后失焦。"""
    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    from core.launcher import PROCESSENTRY32W

    kernel32 = ctypes.windll.kernel32
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return set(root_pids)
    parents: Dict[int, int] = {}
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
            while True:
                parents[int(pe.th32ProcessID)] = int(pe.th32ParentProcessID)
                if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                    break
    finally:
        try:
            kernel32.CloseHandle(snap)
        except Exception:
            pass

    result = set(root_pids)
    changed = True
    while changed:
        changed = False
        for pid, ppid in parents.items():
            if ppid in result and pid not in result:
                result.add(pid)
                changed = True
    return result


# ---------------------------------------------------------
# 引擎
# ---------------------------------------------------------
class GamepadEngine:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._settings: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._pressed_vks: Set[int] = set()
        self._slot: Optional[int] = None
        self._packet: int = 0
        self._last_active: Optional[bool] = None
        self._pid_cache: Tuple[float, Set[int]] = (0.0, set())
        self._pid_map_cache: Tuple[float, Dict[int, Dict[str, Any]]] = (0.0, {})
        self._game_meta_cache: Dict[int, Tuple[float, str, str]] = {}
        self._target_cache: Tuple[float, Optional[Dict[str, Any]]] = (0.0, None)
        self._edge_state: Set[str] = set()
        self._target: Optional[Dict[str, Any]] = None
        self._state: Dict[str, Any] = {
            "enabled": True,
            "available": bool(XINPUT),
            "backend": XINPUT_DLL,
            "connected": False,
            "slot": None,
            "buttons": [],
            "axes": {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0, "lt": 0.0, "rt": 0.0},
            "active": False,
            "target_game": None,
            "profile": "generic",
            "profile_label": PROFILE_LABELS["generic"],
            "last_action": "",
            "message": "未检测到手柄" if not XINPUT else "等待手柄接入",
        }

    # ---------- 生命周期 ----------
    def start(self) -> None:
        if not IS_WINDOWS or not XINPUT:
            with self._lock:
                self._state["message"] = "当前系统不支持 XInput 手柄"
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="acg-gamepad", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._release_all()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=1.5)
        self._thread = None

    # ---------- 配置 ----------
    def apply_settings(self, cfg: Dict[str, Any]) -> None:
        with self._lock:
            merged = dict(DEFAULT_SETTINGS)
            for k in DEFAULT_SETTINGS:
                if k in cfg:
                    merged[k] = cfg[k]
            try:
                merged["gamepad_deadzone"] = max(0.05, min(0.9, float(merged.get("gamepad_deadzone", 0.35))))
            except Exception:
                merged["gamepad_deadzone"] = 0.35
            self._settings = merged
        if merged.get("gamepad_enabled"):
            self.start()
        else:
            self._release_all()
            with self._lock:
                self._state.update({
                    "enabled": False, "active": False, "buttons": [],
                    "target_game": None, "message": "手柄支持已关闭",
                })
            # 关闭状态下仍保留 4Hz 连接探测，设置页才能显示"已连接/未连接"
            self.start()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            state = dict(self._state)
            state["buttons"] = list(self._state.get("buttons") or [])
            state["axes"] = dict(self._state.get("axes") or {})
            state["bindings"] = dict(DEFAULT_BUTTONS)
            state["profile_buttons"] = dict(self._resolve_bindings())
            state["profiles"] = [{"id": k, "label": v} for k, v in PROFILE_LABELS.items()]
            state["button_labels"] = {b: ACTION_LABELS.get(a, a) for b, a in DEFAULT_BUTTONS.items() if a}
            state["action_labels"] = ACTION_LABELS
            state["settings"] = {"deadzone": self._settings.get("gamepad_deadzone", 0.35)}
            return state

    # ---------- 内部 ----------
    def _resolve_profile_id(self, engine_type: Optional[str], game_id: Optional[int] = None) -> str:
        # 单游戏覆盖优先
        if game_id is not None:
            per_game = self._settings.get("gamepad_per_game") or {}
            entry = per_game.get(str(game_id)) if isinstance(per_game, dict) else None
            if isinstance(entry, dict):
                p = str(entry.get("profile") or "auto")
                if p != "auto" and p in PROFILES:
                    return p
        pref = str(self._settings.get("gamepad_profile") or "auto")
        if pref != "auto" and pref in PROFILES:
            return pref
        return engine_to_profile(engine_type)

    def _game_disabled(self, game_id: Optional[int]) -> bool:
        if game_id is None:
            return False
        per_game = self._settings.get("gamepad_per_game") or {}
        entry = per_game.get(str(game_id)) if isinstance(per_game, dict) else None
        return bool(isinstance(entry, dict) and entry.get("enabled") is False)

    def _resolve_bindings(self) -> Dict[str, str]:
        """按钮 -> 动作；支持配置里的局部覆盖。"""
        buttons = dict(DEFAULT_BUTTONS)
        override = self._settings.get("gamepad_bindings") or {}
        if isinstance(override, dict):
            for b, action in override.items():
                if b in buttons and (action in ACTIONS or action in ("", None)):
                    buttons[b] = action or ""
        if not self._settings.get("gamepad_back_screenshot", True) and buttons.get("back") == "screenshot":
            buttons["back"] = ""
        return buttons

    def _get_cached_game_meta(self, gid: int) -> Tuple[str, str]:
        """Lightweight TTL cache for game_id -> (display_title, engine_type) to avoid frequent SQLite opens."""
        now = time.time()
        cached_item = self._game_meta_cache.get(gid)
        if cached_item and now - cached_item[0] < 30.0:
            return cached_item[1], cached_item[2]
        try:
            from core.launcher import get_game_by_id
            game = get_game_by_id(gid) or {}
            title = game.get("display_title") or game.get("clean_title") or game.get("folder_name") or ""
            eng = game.get("engine_type") or ""
            self._game_meta_cache[gid] = (now, title, eng)
            return title, eng
        except Exception:
            return "", ""

    def _pid_game_map(self) -> Dict[int, Dict[str, Any]]:
        """
        PID -> 游戏信息。包含每个游戏派生的子进程（启动器把 PID 交给子进程后
        前台窗口属于子进程，不能因此判定"不是在玩游戏"）。进程树快照 TTL 缓存 2.5 秒。
        """
        now = time.time()
        cached_ts, cached = self._pid_map_cache
        if now - cached_ts < 2.5:
            return cached

        mapping: Dict[int, Dict[str, Any]] = {}
        try:
            from core.launcher import get_running_games_info
            running = get_running_games_info()
            root_to_entry: Dict[int, Dict[str, Any]] = {}
            for gid, info in running.items():
                root = info.get("pid")
                if not root:
                    continue
                title, eng = self._get_cached_game_meta(int(gid))
                root_pid = int(root)
                entry = {
                    "game_id": int(gid),
                    "title": title,
                    "engine_type": eng,
                    "pid": root_pid,
                }
                root_to_entry[root_pid] = entry
                mapping[root_pid] = entry

            # 只在存在运行中游戏时做一次进程树快照
            for root_pid, entry in root_to_entry.items():
                for pid in _descendant_pids({root_pid}):
                    mapping[pid] = entry
        except Exception:
            pass

        self._pid_map_cache = (now, mapping)
        return mapping

    def _read_pad(self) -> Optional[Tuple[int, XINPUT_STATE]]:
        best: Optional[Tuple[int, XINPUT_STATE]] = None
        for slot in range(4):
            st = XINPUT_STATE()
            if XINPUT.XInputGetState(slot, ctypes.byref(st)) == 0:
                if self._slot == slot:
                    return slot, st
                if best is None:
                    best = (slot, st)
        return best

    def _release_all(self) -> None:
        with self._lock:
            pressed = list(self._pressed_vks)
            self._pressed_vks.clear()
        for vk in pressed:
            try:
                _send_vk(vk, keyup=True)
            except Exception:
                pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            interval = 0.01
            try:
                interval = self._tick()
            except Exception as e:
                with self._lock:
                    self._state["message"] = f"手柄线程异常: {e}"
                interval = 0.3
            self._stop.wait(interval)

    def _tick(self) -> float:
        enabled = bool(self._settings.get("gamepad_enabled", True))
        if not enabled:
            # 关闭时只保留低频连接探测，供设置页显示状态，不参与按键转发
            self._release_all()
            pad = self._read_pad() if XINPUT else None
            with self._lock:
                self._edge_state = set()
                self._state.update({
                    "enabled": False,
                    "connected": bool(pad),
                    "slot": pad[0] if pad else None,
                    "active": False,
                    "target_game": None,
                    "buttons": [],
                    "message": "手柄支持已关闭",
                })
            return 0.25

        pad = self._read_pad() if XINPUT else None

        if not pad:
            self._slot = None
            self._release_all()
            with self._lock:
                self._state.update({
                    "enabled": enabled,
                    "connected": False,
                    "slot": None,
                    "buttons": [],
                    "active": False,
                    "target_game": None,
                    "message": "等待手柄接入（XInput 0-3 号槽均无设备）",
                })
            return 0.35

        slot, st = pad
        self._slot = slot
        gp = st.Gamepad
        dz = float(self._settings.get("gamepad_deadzone", 0.35))

        pressed: Set[str] = {name for name, bit in BUTTON_BITS.items() if gp.wButtons & bit}
        lt = gp.bLeftTrigger / 255.0
        rt = gp.bRightTrigger / 255.0
        if lt > dz:
            pressed.add("lt")
        if rt > dz:
            pressed.add("rt")

        lx, ly = _norm_stick(gp.sThumbLX), _norm_stick(gp.sThumbLY)
        rx, ry = _norm_stick(gp.sThumbRX), _norm_stick(gp.sThumbRY)

        # 摇杆补方向（十字键优先）
        if not ({"up", "down", "left", "right"} & pressed):
            if abs(lx) >= dz or abs(ly) >= dz:
                if abs(lx) > abs(ly):
                    pressed.add("right" if lx > 0 else "left")
                else:
                    pressed.add("up" if ly > 0 else "down")

        with self._lock:
            bindings = self._resolve_bindings()
            self._target = self._resolve_target()
            target_gid = (self._target or {}).get("game_id")
            active = bool(enabled and self._target and not self._game_disabled(target_gid))
            profile_id = self._resolve_profile_id((self._target or {}).get("engine_type"), target_gid)

        desired_actions: Set[str] = set()
        for btn in pressed:
            action = bindings.get(btn)
            if action:
                desired_actions.add(action)

        if active:
            self._apply_actions(desired_actions, profile_id)
        else:
            self._release_all()
            with self._lock:
                self._edge_state = set()

        with self._lock:
            self._state.update({
                "enabled": enabled,
                "connected": True,
                "slot": slot,
                "buttons": [b for b in BUTTON_ORDER if b in pressed],
                "axes": {"lx": round(lx, 3), "ly": round(ly, 3), "rx": round(rx, 3),
                         "ry": round(ry, 3), "lt": round(lt, 2), "rt": round(rt, 2)},
                "active": active,
                "target_game": self._target,
                "profile": profile_id,
                "profile_label": PROFILE_LABELS.get(profile_id, profile_id),
                "message": "正在为游戏转发按键" if active else ("手柄已连接，等待通过本库启动游戏" if enabled else "手柄支持已关闭"),
            })
        return 0.016

    def _resolve_target(self) -> Optional[Dict[str, Any]]:
        now = time.time()
        cached_ts, cached = self._target_cache
        if now - cached_ts < 0.35:
            return cached
        pid = _foreground_pid()
        target = None
        if pid:
            target = self._pid_game_map().get(pid)
        self._target_cache = (now, target)
        return target

    def _trigger_screenshot_action(self, profile_id: str) -> None:
        """
        触发手柄截图：优先直接调用 capture_game_window_screenshot(target_gid, pid=target_pid)
        避免 200ms 轮询漏检；若直接抓图失败再回退读取用户自定义 screenshot_hotkey 发送按键。
        """
        target_info = self._target or {}
        target_gid = target_info.get("game_id")
        target_pid = _foreground_pid() or target_info.get("pid")

        captured = False
        if target_gid:
            try:
                from core.gallery_cg import capture_game_window_screenshot
                res = capture_game_window_screenshot(int(target_gid), pid=int(target_pid) if target_pid else None)
                captured = bool(res and res.get("success"))
            except Exception:
                captured = False

        if not captured:
            try:
                from config import load_config
                hk_name = str(load_config().get("screenshot_hotkey") or "F12").strip().upper()
            except Exception:
                hk_name = str(PROFILES.get(profile_id, PROFILES["generic"]).get("screenshot", "F12")).upper()
            vk = VK.get(hk_name) or VK.get("F12")
            if vk:
                try:
                    _send_vk(vk, keyup=False)
                    time.sleep(0.08)
                    _send_vk(vk, keyup=True)
                except Exception:
                    pass

        with self._lock:
            self._state["last_action"] = ACTION_LABELS.get("screenshot", "游戏截图")

    def _apply_actions(self, desired_actions: Set[str], profile_id: str) -> None:
        keys = PROFILES.get(profile_id, PROFILES["generic"])
        desired_vks: Set[int] = set()
        edge_actions: Set[str] = set()
        for action in desired_actions:
            if action in EDGE_ACTIONS:
                edge_actions.add(action)
                continue
            key_name = keys.get(action)
            vk = VK.get(str(key_name).upper()) if key_name else None
            if vk:
                desired_vks.add(vk)

        with self._lock:
            current = set(self._pressed_vks)
            to_press = desired_vks - current
            to_release = current - desired_vks
            self._pressed_vks = desired_vks
            prev_edges = getattr(self, "_edge_state", set())

        for vk in to_release:
            try:
                _send_vk(vk, keyup=True)
            except Exception:
                pass
        for vk in to_press:
            try:
                _send_vk(vk, keyup=False)
            except Exception:
                pass

        # 边沿动作（截图）只触发一次，避免按住连拍
        for action in edge_actions - prev_edges:
            if action == "screenshot":
                threading.Thread(
                    target=self._trigger_screenshot_action,
                    args=(profile_id,),
                    daemon=True,
                ).start()
                continue
            key_name = keys.get(action)
            vk = VK.get(str(key_name).upper()) if key_name else None
            if vk:
                try:
                    _send_vk(vk, keyup=False)
                    time.sleep(0.06)
                    _send_vk(vk, keyup=True)
                    with self._lock:
                        self._state["last_action"] = ACTION_LABELS.get(action, action)
                except Exception:
                    pass
        with self._lock:
            self._edge_state = set(edge_actions)


# 单例
ENGINE = GamepadEngine()


def start(cfg: Optional[Dict[str, Any]] = None) -> None:
    if cfg is not None:
        ENGINE.apply_settings(cfg)
    ENGINE.start()


def stop() -> None:
    ENGINE.stop()


def reload_config(cfg: Dict[str, Any]) -> None:
    ENGINE.apply_settings(cfg)


def get_status() -> Dict[str, Any]:
    return ENGINE.get_status()
