# -*- coding: utf-8 -*-
"""
ACG Vault v2.4 Native Desktop Wrapper, In-Game Companion Overlay & System Tray Daemon.
Provides:
1. Standalone Native Desktop Window via PyWebView (with automatic Edge/Chrome --app mode fallback)
2. Always-on-Top In-Game Companion Overlay Window (default Alt+G) with Win32 Click-Through HUD mode (Alt+T)
3. Windows System Tray Icon & Context Menu (Minimize to tray, companion overlay, click-through toggle, quick scan, clean exit)
4. Global Boss/Summon Hotkey (Alt+Space), Global Overlay Hotkey (Alt+G) & Click-Through Toggle (Alt+T) via Win32 RegisterHotKey
"""

import os
import sys
import time
import shutil
import subprocess
import threading
import webbrowser
import ctypes
import functools
import traceback
from pathlib import Path
from typing import Optional, Dict, Any

from config import APP_VERSION, BASE_DIR, RESOURCE_DIR, DATA_DIR, load_config, save_config

IS_WINDOWS = sys.platform == "win32"
APP_USER_MODEL_ID = "ACGVault.Desktop.1"
APP_ICON_PATH = RESOURCE_DIR / "static" / "icon.ico"


class _CappedLogStream:
    """按大小自动截断的日志流：某个循环刷屏时不至于把磁盘写爆。"""

    def __init__(self, path, limit: int = 8 * 1024 * 1024):
        self.path = path
        self.limit = limit
        self._f = open(path, "a", encoding="utf-8", buffering=1)
        self._pending = 0

    def write(self, data):
        try:
            self._f.write(data)
        except Exception:
            return 0
        self._pending += len(data)
        if self._pending > 256 * 1024:
            self._pending = 0
            try:
                if self._f.tell() > self.limit:
                    self._f.seek(0)
                    self._f.truncate(0)
            except Exception:
                pass
        return len(data)

    def flush(self):
        try:
            self._f.flush()
        except Exception:
            pass

    def isatty(self):
        return False

    def fileno(self):
        return self._f.fileno()


def _ensure_std_streams() -> None:
    """pythonw / PyInstaller --windowed 下 sys.stdout 是 None，任何 print 都会抛异常。
    统一重定向到 data/desktop.log，既避免崩溃又能事后排查。"""
    try:
        if sys.stdout is not None and sys.stderr is not None:
            return
        log_path = DATA_DIR / "desktop.log"
        try:
            if log_path.exists() and log_path.stat().st_size > 8 * 1024 * 1024:
                log_path.unlink()
        except Exception:
            pass
        f = _CappedLogStream(log_path)
        if sys.stdout is None:
            sys.stdout = f
        if sys.stderr is None:
            sys.stderr = f
    except Exception:
        try:
            devnull = open(os.devnull, "w")
            sys.stdout = sys.stdout or devnull
            sys.stderr = sys.stderr or devnull
        except Exception:
            pass


def _init_taskbar_identity() -> None:
    """让任务栏把本进程当成独立应用（自定义图标/名称），而不是 python.exe。"""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


# ---------------------------------------------------------
# CRITICAL: 单实例模块别名
# ---------------------------------------------------------
# 用 `python desktop_app.py` 启动时，本文件是 `__main__`；而 main.py 里
# `from desktop_app import show_or_toggle_overlay_window` 会把同一个文件再导入
# 一份全新的模块副本 —— 那份副本的 _overlay_window / _webview_window 永远是 None。
# 结果就是：按 Alt+G 永远走 Edge 回退、窗口最小化恢复永远是假成功、穿透作用在错误的 HWND 上。
# 这里把 `desktop_app` 指向 `__main__`，保证全进程只有一份窗口状态。
if __name__ == "__main__":
    sys.modules.setdefault("desktop_app", sys.modules["__main__"])

_webview_window = None
_overlay_window = None
_main_api = None
_overlay_api = None
_server_should_exit = False
_shutting_down = False
_overlay_opacity = 0.92
_unlock_window = None
_overlay_click_through = False
_hotkey_thread_id: Optional[int] = None

OVERLAY_WINDOW_TITLE = "ACG Vault 伴侣悬浮窗 (Alt+G)"
UNLOCK_WINDOW_TITLE = "ACG Vault 穿透解锁条"


# ---------------------------------------------------------
# Window geometry persistence & frameless window bridge (v2.6.2)
# ---------------------------------------------------------
def log_desktop_error(message: str) -> None:
    """把窗口层/前端桥的异常落盘，方便出问题时直接看 data/desktop_error.log。"""
    try:
        with open(DATA_DIR / "desktop_error.log", "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


def _safe_api(fn):
    """任何窗口 API 都不允许把异常抛回 JS（否则前端会弹未处理异常横幅）。"""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as e:
            log_desktop_error("%s.%s failed: %s\n%s" % (self._role, fn.__name__, e, traceback.format_exc()))
            return False
    return wrapper


def _bounds_cfg(key: str) -> Dict[str, Any]:
    try:
        cfg = load_config()
        b = cfg.get(key)
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


def _save_bounds_cfg(key: str, x, y, width, height, maximized=None) -> None:
    try:
        cfg = load_config()
        b = dict(cfg.get(key) or {})
        b["x"] = int(x)
        b["y"] = int(y)
        b["width"] = max(360, int(width))
        b["height"] = max(280, int(height))
        if maximized is not None:
            b["maximized"] = bool(maximized)
        cfg[key] = b
        save_config(cfg)
    except Exception as e:
        print(f"[Window] persist bounds failed: {e}")


class WindowBridge:
    """
    Exposed to the page as ``window.pywebview.api``.

    A frameless window has no native title bar, so dragging / minimizing / maximizing /
    closing all have to be driven from the web UI. Every method below returns plain
    JSON-serialisable values because pywebview marshals them through the JS bridge.
    """

    def __init__(self, role: str):
        self._role = role
        self._window = None
        self._frameless = False
        self._maximized = False
        self._on_close = None
        self._bounds_key = "window_bounds" if role == "main" else "overlay_bounds"
        self._restore_box = None
        self._title = ""
        self._prefix = ""
        self._hwnd_cache = 0
        # pywebview 创建窗口时传的尺寸 ≠ GetWindowRect 的可见尺寸（DWM 外框差值），
        # 所以持久化必须存「我们请求的尺寸」，否则每次重启窗口都会缩水一圈。
        self._creation_size = None
        self._requested_size = None

    def _bind(self, window, frameless: bool, maximized: bool = False, title: str = "",
              size=None, prefix: str = "") -> None:
        self._window = window
        self._frameless = bool(frameless)
        self._maximized = bool(maximized)
        self._title = title or ""
        self._prefix = prefix or ""
        if size:
            self._creation_size = (int(size[0]), int(size[1]))

    # ---------------------------------------------------------------- helpers
    def _is_zoomed(self) -> bool:
        """以 Win32 的真实状态为准，避免隐藏/显示后标志位和窗口实际状态脱节。"""
        hwnd = self._hwnd()
        if hwnd and IS_WINDOWS:
            try:
                return bool(ctypes.windll.user32.IsZoomed(hwnd))
            except Exception:
                pass
        return self._maximized

    def _hwnd(self) -> int:
        """窗口句柄：带缓存，且用「标题前缀 + 本进程」匹配。

        WebView2 加载完页面后会把窗口标题改成 <title>，所以不能用创建时
        的完整标题去 FindWindow，否则页面一加载完就再也找不到窗口。
        """
        if not IS_WINDOWS:
            return 0
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        if self._hwnd_cache:
            try:
                if user32.IsWindow(self._hwnd_cache):
                    return self._hwnd_cache
            except Exception:
                pass
            self._hwnd_cache = 0

        my_pid = os.getpid()
        candidates = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _cb(h, _lp):
            n = user32.GetWindowTextLengthW(h)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, buf, n + 1)
                title = buf.value
                if title == self._title or (self._prefix and title.startswith(self._prefix)):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                    if int(pid.value) == my_pid:
                        candidates.append(int(h))
            return True

        try:
            user32.EnumWindows(WNDENUMPROC(_cb), 0)
        except Exception:
            return 0

        self._hwnd_cache = candidates[0] if candidates else 0
        return self._hwnd_cache

    def apply_maximized(self, maximize: bool = True) -> bool:
        """用 Win32 ShowWindow 做最大化/还原。

        pywebview 的 FormBorderStyle.None 窗口走 WinForms Maximize 时会把窗口撑到
        屏幕尺寸却保留原 Location（表现为窗口一半在屏幕外），所以这里直接交给系统。
        """
        if self._window is None:
            return False
        SW_MAXIMIZE = 3
        SW_RESTORE = 9
        hwnd = self._hwnd()
        try:
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE if maximize else SW_RESTORE)
            elif maximize:
                self._window.maximize()
            else:
                self._window.restore()
            self._maximized = bool(maximize)
            return True
        except Exception as e:
            log_desktop_error(f"{self._role}.apply_maximized failed: {e}")
            return False

    def _position(self):
        try:
            x, y = self._window.gui.get_position(self._window.uid)
            return int(x), int(y)
        except Exception:
            b = _bounds_cfg(self._bounds_key)
            return int(b.get("x") or 0), int(b.get("y") or 0)

    def _current_size(self):
        if self._requested_size:
            return self._requested_size
        if self._creation_size:
            return self._creation_size
        _, _, w, h = self._geom()
        return int(w), int(h)

    def _geom(self):
        w = self._window
        if w is None:
            return 0, 0, 1200, 800
        try:
            x, y = w.gui.get_position(w.uid)
            width, height = w.gui.get_size(w.uid)
            return int(x), int(y), int(width), int(height)
        except Exception:
            b = _bounds_cfg(self._bounds_key)
            return (
                int(b.get("x") or 0), int(b.get("y") or 0),
                int(b.get("width") or 1200), int(b.get("height") or 800),
            )

    def _persist(self, maximized=None) -> None:
        if self._window is None:
            return
        if maximized is None:
            maximized = self._maximized
        if maximized:
            b = _bounds_cfg(self._bounds_key)
            _save_bounds_cfg(
                self._bounds_key,
                b.get("x") or 0, b.get("y") or 0,
                b.get("width") or 1200, b.get("height") or 800,
                maximized=True,
            )
            return
        x, y = self._position()
        _, _, width, height = self._geom()
        _save_bounds_cfg(self._bounds_key, x, y, width, height, maximized=False)

    # -------------------------------------------------------------------- api
    @_safe_api
    def win_get_state(self):
        if self._window is None:
            return {"ok": False}
        x, y = self._position()
        _, _, width, height = self._geom()
        return {
            "ok": True,
            "role": self._role,
            "frameless": self._frameless,
            "maximized": self._is_zoomed(),
            "x": x, "y": y, "width": width, "height": height,
        }

    @_safe_api
    def win_restore_for_drag(self, cursor_x=0, cursor_y=0):
        """
        像 Windows 一样：拖拽最大化的标题栏时先还原成窗口，并让光标仍停在标题栏
        的相对位置，然后由前端继续拖拽。
        """
        if self._window is None:
            return {"ok": False}
        hwnd = self._hwnd()
        u = ctypes.windll.user32
        if not hwnd or not u.IsZoomed(hwnd):
            return {"ok": False}

        screen_w = u.GetSystemMetrics(0) or 1920
        screen_h = u.GetSystemMetrics(1) or 1080
        ratio = max(0.0, min(1.0, float(cursor_x) / float(screen_w)))

        try:
            u.ShowWindow(hwnd, 9)  # SW_RESTORE
            time.sleep(0.06)
            _, _, width, height = self._geom()
            if width <= 0 or height <= 0:
                return {"ok": False}

            new_x = int(cursor_x - ratio * width)
            new_y = int(cursor_y - 15)
            new_x = max(120 - width, min(new_x, screen_w - 120))
            new_y = max(0, min(new_y, screen_h - 80))

            self._window.move(new_x, new_y)
            self._maximized = False
            self._persist()
            return {"ok": True, "x": new_x, "y": new_y, "width": width, "height": height}
        except Exception as e:
            log_desktop_error("win_restore_for_drag failed: %s" % e)
            return {"ok": False}

    @_safe_api
    def win_minimize(self):
        if self._window is None:
            return False
        try:
            self._window.minimize()
            return True
        except Exception:
            return False

    @_safe_api
    def win_toggle_maximize(self):
        if self._window is None:
            return False
        if self._is_zoomed():
            self.apply_maximized(False)
            box = self._restore_box
            if box:
                # 用最大化之前的尺寸写回，避免把最大化尺寸当成窗口尺寸存下来
                _save_bounds_cfg(self._bounds_key, box[0], box[1], box[2], box[3], maximized=False)
            else:
                self._persist(maximized=False)
        else:
            if self._frameless:
                px, py = self._position()
                _, _, sw, sh = self._geom()
                self._restore_box = (px, py, sw, sh)
            self.apply_maximized(True)
            self._persist(maximized=True)
        return self._maximized

    @_safe_api
    def win_close(self):
        if self._on_close is not None:
            try:
                return bool(self._on_close())
            except Exception:
                pass
        if self._window is None:
            return False
        try:
            self._window.hide()
            return True
        except Exception:
            return False

    @_safe_api
    def win_move(self, x, y):
        if self._window is None:
            return False
        try:
            self._window.move(int(x), int(y))
            return True
        except Exception:
            return False

    @_safe_api
    def win_resize(self, width, height):
        if self._window is None:
            return False
        try:
            self._requested_size = (int(width), int(height))
            self._window.resize(int(width), int(height))
            return True
        except Exception:
            return False

    @_safe_api
    def _frame_delta(self, hwnd):
        """窗口外框 - 客户区的差值（DWM 边框），用于把「可见尺寸」换算成 Form.Size。"""
        if not hwnd or not IS_WINDOWS:
            return (0.0, 0.0)
        try:
            from ctypes import wintypes
            u = ctypes.windll.user32
            wr = wintypes.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(wr))
            cr = wintypes.RECT()
            u.GetClientRect(hwnd, ctypes.byref(cr))
            scale = 1.0
            try:
                scale = (u.GetDpiForWindow(hwnd) or 96) / 96.0
            except Exception:
                scale = 1.0
            return ((wr.right - wr.left - cr.right) / scale,
                    (wr.bottom - wr.top - cr.bottom) / scale)
        except Exception:
            return (0.0, 0.0)

    @_safe_api
    def win_set_bounds(self, x=0, y=0, width=1024, height=680):
        """
        移动 + 缩放。

        必须走 pywebview 的 move/resize（内部是 WinForms 的 Location/Size），
        WebView2 子窗口才会跟着重排。直接 SetWindowPos 只改宿主窗口，子窗口
        会停在旧尺寸，表现为内容整体偏移/被裁掉一截。
        """
        if self._window is None:
            return False
        try:
            x = int(x)
            y = int(y)
            width = max(200, int(width))
            height = max(150, int(height))
            fw, fh = self._frame_delta(self._hwnd())
            self._window.move(x, y)
            self._window.resize(int(round(width + fw)), int(round(height + fh)))
            self._requested_size = (width, height)
            self._maximized = False
            return True
        except Exception as e:
            log_desktop_error("win_set_bounds failed: %s" % e)
            return False

    @_safe_api
    def win_save_bounds(self):
        try:
            self._persist()
            _force_relayout(self._hwnd())
            return True
        except Exception:
            return False

    @_safe_api
    def win_set_unlock_chip(self, x=0, y=0, w=0, h=0):
        if self._role != "overlay":
            return False
        _position_unlock_chip(int(x), int(y), int(w), int(h))
        return True

    @_safe_api
    def win_set_opacity(self, value=0.92):
        if self._role != "overlay":
            return False
        return bool(set_overlay_opacity(value).get("success"))

    @_safe_api
    def win_unlock(self):
        if self._role != "unlock":
            return False
        set_overlay_click_through(False)
        return True

    @_safe_api
    def win_set_click_through(self, enable=None):
        if self._role != "overlay":
            return {"success": False}
        return set_overlay_click_through(enable)

    @_safe_api
    def win_hide(self):
        if self._window is None:
            return False
        try:
            self._window.hide()
            return True
        except Exception:
            return False



def parse_hotkey_modifiers(hotkey_str: str):
    """Parses hotkey string like 'Alt+Space', 'Alt+G', or 'Ctrl+Alt+V' into Win32 (fsModifiers, vk)."""
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_NOREPEAT = 0x4000

    parts = [p.strip().upper() for p in (hotkey_str or "Alt+Space").split("+") if p.strip()]
    mods = MOD_NOREPEAT
    vk = 0x20  # VK_SPACE

    key_map = {
        "SPACE": 0x20,
        "TAB": 0x09,
        "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
        "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
        "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    }

    for p in parts:
        if p in ("ALT", "MENU"):
            mods |= MOD_ALT
        elif p in ("CTRL", "CONTROL"):
            mods |= MOD_CONTROL
        elif p == "SHIFT":
            mods |= MOD_SHIFT
        elif p in key_map:
            vk = key_map[p]
        elif len(p) == 1 and "A" <= p <= "Z":
            vk = ord(p)
        elif len(p) == 1 and "0" <= p <= "9":
            vk = ord(p)

    return mods, vk


def _find_overlay_hwnd() -> int:
    """Locates the Win32 HWND for the In-Game Companion Overlay window.

    多实例（比如源码版 + exe 版同时跑）时按标题找会命中别人的窗口，
    所以这里优先返回**本进程**拥有的那个。
    """
    if not IS_WINDOWS:
        return 0
    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        my_pid = os.getpid()

        def _pid_of(h):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            return int(pid.value)

        hwnd = user32.FindWindowW(None, OVERLAY_WINDOW_TITLE)
        if hwnd and _pid_of(hwnd) == my_pid:
            return int(hwnd)

        candidates = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _enum_cb(h, lparam):
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buf, length + 1)
                title = buf.value
                if "ACG Vault 游戏内攻略伴侣" in title or "ACG Vault 伴侣悬浮窗" in title:
                    candidates.append((int(h), _pid_of(h), bool(user32.IsWindowVisible(h))))
            return True

        user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
        if not candidates:
            return 0
        candidates.sort(key=lambda item: (item[1] != my_pid, not item[2]))
        return candidates[0][0]
    except Exception:
        return 0


def get_overlay_click_through_state() -> bool:
    """Returns whether the Companion Overlay window is currently in Click-Through HUD mode."""
    return bool(_overlay_click_through)


def _apply_overlay_layered(hwnd: int, click_through: bool, alpha: float) -> bool:
    """一次设置 WS_EX_TRANSPARENT + LWA_ALPHA，避免穿透和透明度互相覆盖。"""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        LWA_ALPHA = 0x00000002

        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED
        if click_through:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        value = int(max(0.2, min(1.0, float(alpha))) * 255)
        user32.SetLayeredWindowAttributes(hwnd, 0, value, LWA_ALPHA)
        return True
    except Exception as e:
        print(f"[Desktop] layered style failed: {e}")
        return False


def set_overlay_opacity(value: float) -> Dict[str, Any]:
    """设置伴侣窗整体不透明度（0.2~1.0）。"""
    global _overlay_opacity
    try:
        _overlay_opacity = max(0.2, min(1.0, float(value)))
    except Exception:
        return {"success": False, "message": "无效的透明度"}

    hwnd = _find_overlay_hwnd()
    applied = _apply_overlay_layered(hwnd, _overlay_click_through, _overlay_opacity)
    return {"success": True, "opacity": _overlay_opacity, "applied_win32": applied}


def get_overlay_state() -> Dict[str, Any]:
    return {
        "click_through": bool(_overlay_click_through),
        "opacity": float(_overlay_opacity),
        "visible": is_overlay_visible(),
    }


def _notify_overlay_page() -> None:
    """把穿透/透明度状态推给伴侣窗页面（热键改状态时避免 UI 滞后）。"""
    w = _overlay_window
    if w is None:
        return
    try:
        w.evaluate_js("window.__acgSyncOverlay && window.__acgSyncOverlay()")
    except Exception:
        pass


def _force_relayout(hwnd: int) -> None:
    """强制窗口和它的子窗口（WebView2）重新计算布局。

    快速连续 SetWindowPos 或隐藏状态下移动窗口后，WebView2 子窗口偶尔会停在
    旧位置，表现为内容整体偏移/被裁掉一截。SWP_FRAMECHANGED + 重绘可以纠正。
    """
    if not IS_WINDOWS or not hwnd:
        return
    try:
        u = ctypes.windll.user32
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        RDW_INVALIDATE = 0x0001
        RDW_ALLCHILDREN = 0x0080
        RDW_UPDATENOW = 0x0100
        u.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                       SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED)
        u.RedrawWindow(hwnd, None, None, RDW_INVALIDATE | RDW_ALLCHILDREN | RDW_UPDATENOW)
    except Exception:
        pass


def _unlock_hwnd() -> int:
    api = globals().get("_unlock_api")
    try:
        return api._hwnd() if api is not None else 0
    except Exception:
        return 0


def _position_unlock_chip(x: int, y: int, w: int, h: int) -> None:
    """把解锁小窗精确盖在「已穿透」按钮的位置上；尺寸为 0 时隐藏。"""
    win = _unlock_window
    if win is None:
        return
    if w <= 0 or h <= 0:
        _hide_unlock_window()
        return

    overlay = _find_overlay_hwnd()
    if not overlay:
        return
    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        pt = wintypes.POINT(int(x), int(y))
        user32.ClientToScreen(overlay, ctypes.byref(pt))
        sx, sy = int(pt.x), int(pt.y)
        sw, sh = max(18, int(w)), max(16, int(h))
        hwnd = _unlock_hwnd()
        if hwnd:
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            user32.SetWindowPos(hwnd, 0, sx, sy, sw, sh, SWP_NOZORDER | SWP_NOACTIVATE)
        if not getattr(win, "_is_visible", False):
            win.show()
            win._is_visible = True
        # 保持和伴侣窗一致的层级与不透明度
        try:
            _apply_overlay_layered(hwnd, False, _overlay_opacity)
        except Exception:
            pass
    except Exception as e:
        print(f"[Desktop] position unlock chip failed: {e}")


_wheel_hook_started = False


_wheel_lock = threading.Lock()
_wheel_pending = 0
_wheel_last_sent = 0.0


def _forward_overlay_wheel(delta: int) -> None:
    """把滚轮转发给伴侣窗页面。

    合并 40ms 内的多次滚动，避免高频 evaluate_js 把 pywebview 的回调表冲掉
    （表现为 win_get_state.<id> is not a function）。
    """
    global _wheel_pending, _wheel_last_sent

    w = _overlay_window
    if w is None:
        return

    with _wheel_lock:
        _wheel_pending += int(delta)
        now = time.time()
        if now - _wheel_last_sent < 0.04:
            return
        total = _wheel_pending
        _wheel_pending = 0
        _wheel_last_sent = now

    try:
        w.evaluate_js("window.__acgScrollBy && window.__acgScrollBy(%d)" % total)
    except Exception:
        pass


def _wheel_hook_loop() -> None:
    """WH_MOUSE_LL：只在「穿透锁定」时拦截伴侣窗范围内的滚轮。

    64 位下 WPARAM/LPARAM 是 8 字节，必须显式声明 argtypes，
    否则 CallNextHookEx 会抛 OverflowError —— 每个鼠标事件都写一条
    traceback，日志几分钟就能涨到上百 MB。
    """
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    WH_MOUSE_LL = 14
    WM_MOUSEWHEEL = 0x020A
    HC_ACTION = 0

    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)

    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, ctypes.c_ulong]
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
    user32.CallNextHookEx.restype = LRESULT
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]

    def _proc(n_code, w_param, l_param):
        try:
            if n_code == HC_ACTION and w_param == WM_MOUSEWHEEL and _overlay_click_through:
                hwnd = _find_overlay_hwnd()
                if hwnd:
                    pt = wintypes.POINT()
                    user32.GetCursorPos(ctypes.byref(pt))
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    if rect.left <= pt.x < rect.right and rect.top <= pt.y < rect.bottom:
                        delta = ctypes.c_short((l_param >> 16) & 0xFFFF).value
                        if delta:
                            _forward_overlay_wheel(delta)
                            return 1  # 吞掉，避免同时缩放游戏
        except Exception:
            pass
        try:
            return user32.CallNextHookEx(None, n_code, w_param, l_param)
        except Exception:
            return 0

    proc = HOOKPROC(_proc)  # 必须保持引用，否则会被 GC
    hook = user32.SetWindowsHookExW(WH_MOUSE_LL, proc, None, 0)
    if not hook:
        print("[Desktop] wheel hook install failed")
        return

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    user32.UnhookWindowsHookEx(hook)


def _ensure_wheel_hook() -> None:
    global _wheel_hook_started
    if _wheel_hook_started or not IS_WINDOWS:
        return
    _wheel_hook_started = True
    threading.Thread(target=_wheel_hook_loop, daemon=True).start()


def _show_unlock_window() -> None:
    """穿透锁定时在伴侣窗右上角显示一个可点击的「解锁」小窗。"""
    w = _unlock_window
    if w is None:
        return
    try:
        api = _overlay_api
        if api is not None:
            ox, oy = api._position()
            ow, _ = api._current_size()
            x = max(0, int(ox + ow - 116))
            y = max(0, int(oy + 4))
        else:
            x, y = 200, 200
        w.move(x, y)
        w.show()
        w._is_visible = True
        threading.Thread(target=_raise_hwnd_unlock, daemon=True).start()
    except Exception as e:
        print(f"[Desktop] show unlock window failed: {e}")


def _raise_hwnd_unlock() -> None:
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, UNLOCK_WINDOW_TITLE)
        if hwnd:
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
    except Exception:
        pass


def _hide_unlock_window() -> None:
    w = _unlock_window
    if w is None:
        return
    try:
        w.hide()
        w._is_visible = False
    except Exception:
        pass


def set_overlay_click_through(enable: Optional[bool] = None) -> Dict[str, Any]:
    """
    Toggles or sets Win32 WS_EX_LAYERED | WS_EX_TRANSPARENT on the Companion Overlay window.
    When enabled, mouse clicks pass directly through the overlay into the underlying full-screen game.
    """
    global _overlay_click_through
    target_state = (not _overlay_click_through) if enable is None else bool(enable)
    _overlay_click_through = target_state

    hwnd = _find_overlay_hwnd()
    applied_win32 = _apply_overlay_layered(hwnd, target_state, _overlay_opacity)

    # 穿透时给出一个可点击的解锁小窗（整窗穿透后自身无法再响应点击）
    if target_state:
        _show_unlock_window()
        _ensure_wheel_hook()
    else:
        _hide_unlock_window()
    _notify_overlay_page()

    return {
        "success": True,
        "click_through": _overlay_click_through,
        "applied_win32": applied_win32,
        "message": (
            "已开启 HUD 鼠标穿透锁定！鼠标点击将直接穿透至下层游戏（按 Alt+G 或 Alt+T 可随时解除锁定）"
            if _overlay_click_through
            else "已解除鼠标穿透锁定，伴侣窗恢复自由交互"
        )
    }


def wait_for_server_ready(port: int, timeout: float = 12.0) -> bool:
    import httpx
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/config"
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=0.8) as client:
                r = client.get(url)
                if r.status_code == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def launch_chromium_app_window(url: str, width: int = 1440, height: int = 900) -> bool:
    """Launches Microsoft Edge or Google Chrome in chromeless --app mode as a zero-dependency native window fallback."""
    if not IS_WINDOWS:
        return False
    candidates = [
        shutil.which("msedge"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for exe in candidates:
        if exe and os.path.exists(exe):
            try:
                subprocess.Popen([exe, f"--app={url}", f"--window-size={width},{height}"])
                return True
            except Exception:
                continue
    return False


def _restore_main_window() -> None:
    """从托盘/最小化恢复主窗口。

    pywebview 的 Window.restore() 会把 FormWindowState 设成 Normal —— 对最大化过的
    窗口就是"悄悄降级成窗口态"，但前端按钮还停留在最大化图标、拖拽也被判为不可拖。
    所以这里只在真的最小化时调用 SW_RESTORE，最大化状态则重新断言。
    """
    w = _webview_window
    if w is None:
        return
    u = ctypes.windll.user32
    api = _main_api
    hwnd = api._hwnd() if api is not None else 0
    want_max = bool(hwnd and u.IsZoomed(hwnd)) or bool(api is not None and api._maximized)

    w.show()
    if hwnd and u.IsIconic(hwnd):
        u.ShowWindow(hwnd, 9)  # SW_RESTORE
    if want_max and hwnd and not u.IsZoomed(hwnd):
        u.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
    if api is not None:
        api._maximized = want_max
    w._is_visible = True


def show_or_toggle_desktop_window(port: int, toggle: bool = False):
    """Restores or toggles the main PyWebView window (or opens app window if none active)."""
    global _webview_window
    url = f"http://127.0.0.1:{port}"
    if _webview_window is not None:
        try:
            if toggle and getattr(_webview_window, "_is_visible", True):
                _webview_window.hide()
                _webview_window._is_visible = False
            else:
                _restore_main_window()
            return
        except Exception:
            pass
    if not launch_chromium_app_window(url, 1440, 900):
        webbrowser.open(url)


def set_main_window_minimized(minimize: bool = True) -> bool:
    """
    Minimizes / restores the main PyWebView window. Used by Big Screen mode when a game is
    launched: the TV UI steps aside, then comes back automatically once the game exits.
    """
    global _webview_window
    w = _webview_window
    if w is None:
        return False
    try:
        if minimize:
            w.minimize()
        else:
            _restore_main_window()
        return True
    except Exception:
        try:
            if minimize:
                w.hide()
            else:
                w.show()
            return True
        except Exception:
            return False


def _raise_hwnd_topmost(hwnd: int = 0) -> bool:
    """Re-assert always-on-top for the companion overlay (some games steal the top band)."""
    if not IS_WINDOWS:
        return False
    try:
        user32 = ctypes.windll.user32
        h = hwnd or _find_overlay_hwnd()
        if not h:
            return False
        HWND_TOPMOST = -1
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_SHOWWINDOW = 0x0040
        user32.SetWindowPos(h, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
        return True
    except Exception:
        return False


def _edge_overlay_watchdog(port: int) -> None:
    """Edge fallback: poll for the overlay window handle and force it on top."""
    for _ in range(12):
        time.sleep(0.5)
        if _raise_hwnd_topmost():
            return


def is_overlay_visible() -> bool:
    """伴侣窗是否当前可见（供 /api/overlay/summon 判断该呼出还是关闭）。"""
    return bool(_overlay_window is not None and getattr(_overlay_window, "_is_visible", False))


def show_or_toggle_overlay_window(port: int, toggle: bool = True, game_id: Optional[int] = None) -> bool:
    """
    Restores or toggles the Always-on-Top In-Game Companion Overlay window (default Alt+G).
    If Click-Through HUD mode is currently locked and the user presses Alt+G, it unlocks
    Click-Through first so the user can interact with the overlay immediately.
    """
    global _overlay_window
    suffix = f"?game_id={game_id}" if game_id else ""
    url = f"http://127.0.0.1:{port}/overlay{suffix}"

    if _overlay_window is not None:
        try:
            if game_id:
                _overlay_window.load_url(url)
            if getattr(_overlay_window, "_is_visible", False):
                if _overlay_click_through and toggle:
                    set_overlay_click_through(False)
                    return True
                if toggle:
                    set_overlay_click_through(False)
                    if _overlay_api is not None:
                        _overlay_api.win_save_bounds()
                    _overlay_window.hide()
                    _overlay_window._is_visible = False
                    return True
            _overlay_window.show()
            _overlay_window.restore()
            _overlay_window._is_visible = True
            if _overlay_api is not None:
                ob = _bounds_cfg("overlay_bounds")
                _overlay_api.win_set_bounds(
                    int(ob.get("x") if ob.get("x") is not None else 120),
                    int(ob.get("y") if ob.get("y") is not None else 120),
                    int(ob.get("width") or 460),
                    int(ob.get("height") or 740),
                )
            threading.Thread(target=_force_relayout, args=(_find_overlay_hwnd(),), daemon=True).start()
            if _overlay_click_through:
                _show_unlock_window()
            # 让 WebView2 先完成一次布局，再抢顶层
            threading.Thread(target=_raise_hwnd_topmost, daemon=True).start()
            return True
        except Exception as e:
            print(f"[Desktop] Overlay toggle failed, falling back: {e}")

    if launch_chromium_app_window(url, 460, 740):
        threading.Thread(target=_edge_overlay_watchdog, args=(port,), daemon=True).start()
        return True
    webbrowser.open(url)
    return True


def reload_global_hotkeys():
    """Signals the Win32 hotkey listener thread to re-read config and re-register hotkeys without restart."""
    if not IS_WINDOWS or not _hotkey_thread_id:
        return
    try:
        WM_RELOAD_HOTKEYS = 0x0401
        ctypes.windll.user32.PostThreadMessageW(_hotkey_thread_id, WM_RELOAD_HOTKEYS, 0, 0)
    except Exception:
        pass


def start_global_hotkey_listener(port: int):
    """Registers global boss hotkey (Alt+Space), companion overlay hotkey (Alt+G), and click-through hotkey (Alt+T) on Windows."""
    if not IS_WINDOWS:
        return

    def _hotkey_loop():
        global _hotkey_thread_id
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            _hotkey_thread_id = int(kernel32.GetCurrentThreadId())

            BOSS_ID = 1001
            OVERLAY_ID = 1002
            CLICK_THROUGH_ID = 1003
            WM_RELOAD_HOTKEYS = 0x0401

            def _register_from_config():
                user32.UnregisterHotKey(None, BOSS_ID)
                user32.UnregisterHotKey(None, OVERLAY_ID)
                user32.UnregisterHotKey(None, CLICK_THROUGH_ID)
                cfg = load_config()
                boss_hk = (cfg.get("global_boss_hotkey") or "Alt+Space").strip()
                overlay_hk = (cfg.get("global_overlay_hotkey") or "Alt+G").strip()
                if boss_hk and boss_hk.lower() != "none":
                    mods, vk = parse_hotkey_modifiers(boss_hk)
                    user32.RegisterHotKey(None, BOSS_ID, mods, vk)
                if overlay_hk and overlay_hk.lower() != "none":
                    mods2, vk2 = parse_hotkey_modifiers(overlay_hk)
                    user32.RegisterHotKey(None, OVERLAY_ID, mods2, vk2)
                # Register Alt+T for instant Click-Through HUD lock/unlock in-game
                mods_ct, vk_ct = parse_hotkey_modifiers("Alt+T")
                user32.RegisterHotKey(None, CLICK_THROUGH_ID, mods_ct, vk_ct)

            _register_from_config()

            msg = wintypes.MSG()
            while not _server_should_exit:
                res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if res <= 0:
                    break
                if msg.message == WM_RELOAD_HOTKEYS:
                    _register_from_config()
                elif msg.message == 0x0312:
                    if msg.wParam == BOSS_ID:
                        show_or_toggle_desktop_window(port, toggle=True)
                    elif msg.wParam == OVERLAY_ID:
                        show_or_toggle_overlay_window(port, toggle=True)
                    elif msg.wParam == CLICK_THROUGH_ID:
                        set_overlay_click_through(None)

            user32.UnregisterHotKey(None, BOSS_ID)
            user32.UnregisterHotKey(None, OVERLAY_ID)
            user32.UnregisterHotKey(None, CLICK_THROUGH_ID)
        except Exception as e:
            print(f"[Desktop] Hotkey listener exited: {e}")

    threading.Thread(target=_hotkey_loop, daemon=True).start()


def start_system_tray(port: int, on_exit_callback):
    """Starts a system tray icon if pystray & PIL are available."""
    try:
        import pystray
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill=(99, 102, 241, 255))
        draw.rounded_rectangle((14, 20, 50, 44), radius=8, fill=(255, 255, 255, 240))
        draw.ellipse((36, 26, 44, 34), fill=(236, 72, 153, 255))
        draw.rectangle((20, 28, 28, 32), fill=(99, 102, 241, 255))
        draw.rectangle((22, 26, 26, 34), fill=(99, 102, 241, 255))

        def _on_show(icon, item):
            show_or_toggle_desktop_window(port, toggle=False)

        def _on_overlay(icon, item):
            show_or_toggle_overlay_window(port, toggle=False)

        def _on_toggle_click_through(icon, item):
            set_overlay_click_through(None)

        def _on_browser(icon, item):
            webbrowser.open(f"http://127.0.0.1:{port}")

        def _on_scan(icon, item):
            import httpx
            try:
                httpx.post(f"http://127.0.0.1:{port}/api/games/scan", timeout=2.0)
            except Exception:
                pass

        def _on_quit(icon, item):
            icon.stop()
            on_exit_callback()

        menu = pystray.Menu(
            pystray.MenuItem("打开 ACG Vault 主界面", _on_show, default=True),
            pystray.MenuItem("呼出游戏内攻略伴侣窗 (Alt+G)", _on_overlay),
            pystray.MenuItem("切换伴侣窗鼠标穿透锁定 (Alt+T)", _on_toggle_click_through),
            pystray.MenuItem("立即扫描本地游戏库", _on_scan),
            pystray.MenuItem("在浏览器中打开", _on_browser),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出程序", _on_quit)
        )
        tray = pystray.Icon("ACGVault", img, f"ACG Game Vault v{APP_VERSION}", menu)
        threading.Thread(target=tray.run, daemon=True).start()
        return tray
    except Exception:
        return None


def run_desktop_app():
    _ensure_std_streams()
    _init_taskbar_identity()
    global _webview_window, _overlay_window, _server_should_exit
    import uvicorn
    from main import app

    cfg = load_config()
    port = int(cfg.get("port", 8000))
    desktop_mode = (cfg.get("desktop_mode") or "native").lower()
    start_minimized = "--minimized" in sys.argv

    uv_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(uv_config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    wait_for_server_ready(port)

    def _clean_shutdown():
        """
        退出清理。

        注意：这个函数会被 FormClosing / JS API 回调调用，**绝对不能在里面同步
        destroy() 窗口**——destroy 会再次触发 FormClosing，于是重入到这里，
        形成无限递归：栈溢出 → pythonnet 再去构造异常类型时二次崩溃，
        弹出「Failed to create Python type for ExceptionDispatchInfo」。
        所以这里只置标志位，然后在一个独立线程里延时硬退出。
        """
        global _server_should_exit, _shutting_down

        if _shutting_down:
            return
        _shutting_down = True
        _server_should_exit = True

        try:
            server.should_exit = True
        except Exception:
            pass

        # 托盘 stop() 会等待托盘线程结束，若直接在自己的菜单回调里调用会死锁
        try:
            if tray_icon is not None:
                threading.Thread(target=tray_icon.stop, daemon=True).start()
        except Exception:
            pass

        def _finish():
            time.sleep(0.15)
            os._exit(0)

        threading.Thread(target=_finish, daemon=True).start()

    start_global_hotkey_listener(port)
    tray_icon = start_system_tray(port, _clean_shutdown)
    url = f"http://127.0.0.1:{port}"
    overlay_url = f"http://127.0.0.1:{port}/overlay"

    print("====================================================")
    print(f"  ACG Game Vault v{APP_VERSION} Desktop Service Ready")
    print(f"  Local URL      : {url}")
    print(f"  Boss Hotkey    : {cfg.get('global_boss_hotkey', 'Alt+Space')}")
    print(f"  Overlay Hotkey : {cfg.get('global_overlay_hotkey', 'Alt+G')} (Alt+T 鼠标穿透锁定)")
    print("====================================================")

    if desktop_mode == "native":
        try:
            import webview

            def _opt_int(v):
                try:
                    return int(v)
                except Exception:
                    return None

            frameless = bool(cfg.get("frameless_window", True))
            mb = cfg.get("window_bounds") if isinstance(cfg.get("window_bounds"), dict) else {}
            ob = cfg.get("overlay_bounds") if isinstance(cfg.get("overlay_bounds"), dict) else {}
            main_maximized = bool(mb.get("maximized")) and not start_minimized

            main_api = WindowBridge("main")
            overlay_api = WindowBridge("overlay")
            globals()["_main_api"] = main_api
            globals()["_overlay_api"] = overlay_api

            main_title = f"ACG Game Vault v{APP_VERSION} - 本地 ACG 游戏资产与攻略管理中心"
            window = webview.create_window(
                title=main_title,
                url=url,
                width=int(mb.get("width") or 1460),
                height=int(mb.get("height") or 920),
                x=_opt_int(mb.get("x")),
                y=_opt_int(mb.get("y")),
                min_size=(1024, 680),
                background_color="#070a12",
                text_select=True,
                hidden=start_minimized,
                frameless=frameless,
                easy_drag=False,
                shadow=True,
                js_api=main_api,
            )
            window._is_visible = not start_minimized
            _webview_window = window
            main_api._bind(window, frameless, maximized=main_maximized, title=main_title,
                           size=(int(mb.get("width") or 1460), int(mb.get("height") or 920)),
                           prefix="ACG Game Vault")

            def _apply_startup_bounds():
                """create_window 的 width/height 与真实可见尺寸差一圈 DWM 外框，
                所以启动后直接用 SetWindowPos 把上次的可见几何套回去。"""
                for _ in range(50):
                    time.sleep(0.2)
                    hwnd = main_api._hwnd()
                    if not hwnd:
                        continue
                    try:
                        bx = _opt_int(mb.get("x"))
                        by = _opt_int(mb.get("y"))
                        bw = int(mb.get("width") or 0)
                        bh = int(mb.get("height") or 0)
                        if bw > 200 and bh > 150 and not main_maximized:
                            main_api.win_set_bounds(
                                bx if bx is not None else 60,
                                by if by is not None else 60,
                                bw, bh
                            )
                    except Exception:
                        pass
                    return

            threading.Thread(target=_apply_startup_bounds, daemon=True).start()

            if main_maximized:
                # 启动即最大化时，把配置里的「还原框」先记下来，
                # 否则用户点还原会把最大化后的 (0,0) 存成窗口位置。
                main_api._restore_box = (
                    _opt_int(mb.get("x")) or 0,
                    _opt_int(mb.get("y")) or 0,
                    int(mb.get("width") or 1460),
                    int(mb.get("height") or 920),
                )
                # 无边框窗口不能用 WinForms 的 Maximize（会保留原 Location 导致窗口半屏在屏幕外），
                # 等 HWND 出现后用 Win32 ShowWindow 交给系统处理。
                def _apply_startup_maximize():
                    for _ in range(40):
                        time.sleep(0.25)
                        if main_api._hwnd():
                            main_api.apply_maximized(True)
                            return
                threading.Thread(target=_apply_startup_maximize, daemon=True).start()

            # Hidden always-on-top Companion Overlay, ready for an instant Alt+G summon.
            # Frameless + on_top is what makes it behave like a real in-game HUD.
            overlay_win = webview.create_window(
                title=OVERLAY_WINDOW_TITLE,
                url=overlay_url,
                width=int(ob.get("width") or 460),
                height=int(ob.get("height") or 740),
                x=_opt_int(ob.get("x")),
                y=_opt_int(ob.get("y")),
                min_size=(360, 480),
                background_color="#0a0f1a",
                on_top=True,
                text_select=True,
                hidden=True,
                frameless=True,
                easy_drag=False,
                shadow=False,
                js_api=overlay_api,
            )
            overlay_win._is_visible = False
            _overlay_window = overlay_win
            overlay_api._bind(overlay_win, True, title=OVERLAY_WINDOW_TITLE,
                              size=(int(ob.get("width") or 460), int(ob.get("height") or 740)),
                              prefix="ACG Vault 伴侣悬浮窗")

            # 穿透锁定时整窗不接收鼠标，必须另开一个不穿透的小窗做「解锁」按钮
            unlock_api = WindowBridge("unlock")
            unlock_win = webview.create_window(
                title=UNLOCK_WINDOW_TITLE,
                url=f"{url}/overlay_unlock",
                width=112,
                height=40,
                min_size=(24, 16),
                frameless=True,
                on_top=True,
                hidden=True,
                shadow=False,
                focus=False,
                background_color="#0b1020",
                js_api=unlock_api,
            )
            unlock_win._is_visible = False
            unlock_api._bind(unlock_win, True, title=UNLOCK_WINDOW_TITLE,
                             prefix="ACG Vault 穿透解锁条")
            globals()["_unlock_window"] = unlock_win
            globals()["_unlock_api"] = unlock_api

            def request_overlay_close() -> bool:
                set_overlay_click_through(False)
                overlay_api.win_save_bounds()
                overlay_win.hide()
                overlay_win._is_visible = False
                return True

            overlay_api._on_close = request_overlay_close

            def on_overlay_closing():
                if _shutting_down:
                    return True
                if not _server_should_exit:
                    set_overlay_click_through(False)
                    overlay_win.hide()
                    overlay_win._is_visible = False
                    return False
                return True

            overlay_win.events.closing += on_overlay_closing

            def request_main_close() -> bool:
                if _shutting_down:
                    return True
                try:
                    latest_cfg = load_config()
                    if latest_cfg.get("minimize_to_tray", True) and tray_icon is not None and not _server_should_exit:
                        main_api.win_save_bounds()
                        window.hide()
                        window._is_visible = False
                        return True
                except Exception as e:
                    print(f"[Desktop] close handler error: {e}")
                try:
                    main_api.win_save_bounds()
                except Exception:
                    pass
                _clean_shutdown()
                return True

            main_api._on_close = request_main_close

            def on_closing():
                if _shutting_down:
                    # 已经在退出流程里，放行关闭，绝不再进一次 _clean_shutdown
                    return True
                try:
                    latest_cfg = load_config()
                    if latest_cfg.get("minimize_to_tray", True) and tray_icon is not None and not _server_should_exit:
                        main_api.win_save_bounds()
                        window.hide()
                        window._is_visible = False
                        return False
                except Exception as e:
                    print(f"[Desktop] closing handler error: {e}")
                try:
                    main_api.win_save_bounds()
                except Exception:
                    pass
                _clean_shutdown()
                return True

            window.events.closing += on_closing

            # private_mode=False + storage_path 才能让 localStorage（大屏设置、
            # 攻略布局记忆、视图模式）跨重启保留。
            webview.start(
                private_mode=False,
                storage_path=str(DATA_DIR / "webview_profile"),
                icon=str(APP_ICON_PATH) if APP_ICON_PATH.exists() else None,
            )
            return
        except ImportError:
            if not start_minimized:
                if not launch_chromium_app_window(url):
                    webbrowser.open(url)
        except Exception as e:
            print(f"[Desktop] PyWebView fallback to App Window: {e}")
            if not start_minimized:
                if not launch_chromium_app_window(url):
                    webbrowser.open(url)
    else:
        if not start_minimized:
            webbrowser.open(url)

    try:
        while server_thread.is_alive() and not _server_should_exit:
            time.sleep(1.0)
    except KeyboardInterrupt:
        _clean_shutdown()


if __name__ == "__main__":
    run_desktop_app()
