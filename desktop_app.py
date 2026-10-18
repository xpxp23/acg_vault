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
from pathlib import Path
from typing import Optional, Dict, Any

from config import APP_VERSION, BASE_DIR, load_config

IS_WINDOWS = sys.platform == "win32"

_webview_window = None
_overlay_window = None
_server_should_exit = False
_overlay_click_through = False
_hotkey_thread_id: Optional[int] = None

OVERLAY_WINDOW_TITLE = "ACG Vault 游戏内攻略伴侣 (Alt+G)"


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
    """Locates the Win32 HWND for the In-Game Companion Overlay window."""
    if not IS_WINDOWS:
        return 0
    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, OVERLAY_WINDOW_TITLE)
        if hwnd:
            return int(hwnd)

        found_hwnd = [0]
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _enum_cb(h, lparam):
            if user32.IsWindowVisible(h):
                length = user32.GetWindowTextLengthW(h)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buf, length + 1)
                    title = buf.value
                    if "ACG Vault 游戏内攻略伴侣" in title or "ACG Vault 伴侣悬浮窗" in title:
                        found_hwnd[0] = int(h)
                        return False
            return True

        user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
        return found_hwnd[0]
    except Exception:
        return 0


def get_overlay_click_through_state() -> bool:
    """Returns whether the Companion Overlay window is currently in Click-Through HUD mode."""
    return bool(_overlay_click_through)


def set_overlay_click_through(enable: Optional[bool] = None) -> Dict[str, Any]:
    """
    Toggles or sets Win32 WS_EX_LAYERED | WS_EX_TRANSPARENT on the Companion Overlay window.
    When enabled, mouse clicks pass directly through the overlay into the underlying full-screen game.
    """
    global _overlay_click_through
    target_state = (not _overlay_click_through) if enable is None else bool(enable)
    _overlay_click_through = target_state

    hwnd = _find_overlay_hwnd()
    applied_win32 = False
    if IS_WINDOWS and hwnd:
        try:
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            LWA_ALPHA = 0x00000002

            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if target_state:
                new_style = style | WS_EX_LAYERED | WS_EX_TRANSPARENT
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
                user32.SetLayeredWindowAttributes(hwnd, 0, 232, LWA_ALPHA)
            else:
                new_style = (style | WS_EX_LAYERED) & ~WS_EX_TRANSPARENT
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
                user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
            applied_win32 = True
        except Exception as e:
            print(f"[Desktop] Failed to apply Win32 click-through style: {e}")

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
                _webview_window.show()
                _webview_window.restore()
                _webview_window._is_visible = True
            return
        except Exception:
            pass
    if not launch_chromium_app_window(url, 1440, 900):
        webbrowser.open(url)


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
                    _overlay_window.hide()
                    _overlay_window._is_visible = False
                    return True
            _overlay_window.show()
            _overlay_window.restore()
            _overlay_window._is_visible = True
            return True
        except Exception:
            pass

    if launch_chromium_app_window(url, 460, 740):
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
        global _server_should_exit
        _server_should_exit = True
        server.should_exit = True
        for w in (_overlay_window, _webview_window):
            if w is not None:
                try:
                    w.destroy()
                except Exception:
                    pass
        os._exit(0)

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

            window = webview.create_window(
                title=f"ACG Game Vault v{APP_VERSION} - 本地 ACG 游戏资产与攻略管理中心",
                url=url,
                width=1460,
                height=920,
                min_size=(1024, 680),
                background_color="#070a12",
                text_select=True,
                hidden=start_minimized
            )
            window._is_visible = not start_minimized
            _webview_window = window

            # Create hidden Always-on-Top In-Game Companion Overlay window ready for instant Alt+G summon
            overlay_win = webview.create_window(
                title=OVERLAY_WINDOW_TITLE,
                url=overlay_url,
                width=460,
                height=740,
                min_size=(360, 480),
                background_color="#070a12",
                on_top=True,
                text_select=True,
                hidden=True
            )
            overlay_win._is_visible = False
            _overlay_window = overlay_win

            def on_overlay_closing():
                if not _server_should_exit:
                    set_overlay_click_through(False)
                    overlay_win.hide()
                    overlay_win._is_visible = False
                    return False
                return True

            overlay_win.events.closing += on_overlay_closing

            def on_closing():
                latest_cfg = load_config()
                if latest_cfg.get("minimize_to_tray", True) and tray_icon is not None and not _server_should_exit:
                    window.hide()
                    window._is_visible = False
                    return False
                _clean_shutdown()
                return True

            window.events.closing += on_closing
            webview.start()
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
