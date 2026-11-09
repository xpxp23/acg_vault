"""
MTool 联动启动支撑模块 (v3.2)

解决的问题
----------
旧实现固定用 `mzHook.dll`（64 位）注入所有 RPG Maker 游戏，而 RPG Maker MV
默认窗体是 32 位 `Game.exe`（本库 81 个 MV 里 76 个是 32 位）。64 位 DLL 注入
32 位进程必然失败且**静默**：游戏照常启动、MTool 照常启动，但两者互不相识，
表现就是“无法准确关联，只会独立启动游戏和 mtool”。

本模块提供四件事
----------------
1. `get_exe_bitness()`  读 PE 头判定 32/64 位（支持任意偏移 e_lfanew），而不是靠引擎名猜。
2. `choose_hook()`      按「引擎 + 位数」选正确 hook DLL。
3. `ensure_launch_bat()` 优先复用 MTool 生成的「与工具一同启动.bat」，
   缺失或不一致（旧 MTool 路径 / 位数不符）时重新生成，旧文件留 .bak。
4. `ensure_launch_record()` 维护 `Tool\\gameLaunchs\\<md5(小写完整路径)>`，
   让 MTool 的 UI 一侧也认得这个游戏（文件名规则已实测验证）。

另外 `is_dll_loaded()` / `wait_dll_loaded()` 用来在启动后验证 hook 是否
真的进了游戏进程——这是“已关联 / 未关联”唯一可靠的判据。
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0

# MTool 首次启动某游戏后生成的联动脚本（中英文两版命名）
BAT_CANDIDATES = ("与工具一同启动.bat", "StartWithTool.bat")

# 引擎 -> {位数: hook DLL}。位数以 PE 头为准，读不到才退回引擎默认。
ENGINE_HOOKS: Dict[str, Dict[int, str]] = {
    "mv":   {32: "mzHook32.dll",  64: "mzHook.dll"},
    "mz":   {32: "mzHook32.dll",  64: "mzHook.dll"},
    "rgss": {32: "RGSSHook.dll",  64: "RGSSHook64.dll"},
    "wolf": {32: "wolfHook.dll",  64: "wolfHook.dll"},
    "krkr": {32: "krkrzHook32.dll", 64: "krkrzHook64.dll"},
}

# 引擎读不出位数时的默认猜测。MV 生态 32 位占绝对多数，MZ 一律 64 位。
ENGINE_DEFAULT_BITS = {"mv": 32, "mz": 64, "rgss": 32, "wolf": 32, "krkr": 32}

_MACHINE_MAP = {0x014C: 32, 0x8664: 64, 0xAA64: 64, 0x01C4: 32}


# ---------------------------------------------------------
# 引擎 / 位数 / hook 解析
# ---------------------------------------------------------
ENGINE_LABELS = {"mv": "MV/MZ", "mz": "MZ", "rgss": "RGSS", "wolf": "WOLF", "krkr": "KiriKiri"}


def detect_engine_key(engine_type: Optional[str]) -> Optional[str]:
    """把数据库里的 engine_type 归一成 hook 家族键。"""
    t = (engine_type or "").lower()
    if not t:
        return None
    if "wolf" in t:
        return "wolf"
    if "kiri" in t or "krkr" in t:
        return "krkr"
    if any(k in t for k in ("vx", "xp", "rgss", "2000", "2003")):
        return "rgss"
    if "mv" in t and "mz" in t:
        return "mv"  # 库里的 "RPG Maker MV/MZ" 合并档，两者 hook 相同
    if "mz" in t:
        return "mz"
    if "mv" in t or "rpg maker" in t:
        return "mv"
    return None


def get_exe_bitness(exe_path: Optional[str]) -> Optional[int]:
    """读取 DOS 头 e_lfanew 并 seek 到 PE 头验证签名与 Machine 字段，返回 32 / 64，失败返回 None。"""
    if not exe_path or not os.path.isfile(exe_path):
        return None
    try:
        with open(exe_path, "rb") as f:
            dos_head = f.read(0x40)
            if len(dos_head) < 0x40 or dos_head[:2] != b"MZ":
                return None
            e_lfanew = int.from_bytes(dos_head[0x3C:0x40], "little", signed=False)
            if e_lfanew <= 0 or e_lfanew > 64 * 1024 * 1024:
                return None
            f.seek(e_lfanew)
            pe_hdr = f.read(6)
            if len(pe_hdr) < 6 or pe_hdr[:4] != b"PE\x00\x00":
                return None
            machine = int.from_bytes(pe_hdr[4:6], "little", signed=False)
            return _MACHINE_MAP.get(machine)
    except Exception:
        return None


def choose_hook(mtool_dir: str, engine_type: Optional[str], exe_path: Optional[str]) -> Tuple[Path, int, str]:
    """
    返回 (hook_dll 路径, 位数, 判定依据说明)。
    路径可能不存在，调用方需自行校验。
    """
    key = detect_engine_key(engine_type) or "mv"
    bits = get_exe_bitness(exe_path)
    source = "PE 头"
    if bits is None:
        bits = ENGINE_DEFAULT_BITS.get(key, 32)
        source = "引擎默认"
    dll_name = ENGINE_HOOKS.get(key, ENGINE_HOOKS["mv"]).get(bits, "mzHook.dll")
    hook = Path(mtool_dir) / "Tool" / "loaders" / dll_name
    return hook, bits, source


def describe_hook(engine_type: Optional[str], hook_path: Path, bits: int) -> str:
    key = detect_engine_key(engine_type) or "mv"
    return f"{ENGINE_LABELS.get(key, key.upper())} · {bits} 位 · {hook_path.name}"


# ---------------------------------------------------------
# 「与工具一同启动.bat」管理
# ---------------------------------------------------------
def _read_bat_text(bat_path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return bat_path.read_text(encoding=enc)
        except Exception:
            continue
    return ""


def find_launch_bat(folder_path: str) -> Optional[Path]:
    folder = Path(folder_path)
    for name in BAT_CANDIDATES:
        cand = folder / name
        if cand.is_file():
            return cand
    return None


def inspect_launch_bat(bat_path: Path) -> Dict[str, Any]:
    """
    解析 bat 里的三条关键信息：inject.exe / 游戏 exe / hook DLL。
    解析不出来就视为不可用（宁可重建，也不要盲跑）。
    """
    text = _read_bat_text(bat_path)
    info: Dict[str, Any] = {
        "bat": str(bat_path),
        "inject": None,
        "game_exe": None,
        "hook": None,
        "valid": False,
        "reason": "",
    }
    if not text:
        info["reason"] = "文件不可读"
        return info

    m = re.search(r'"([^"]*inject\.exe)"\s+"([^"]+)"\s+"([^"]+)"', text, re.IGNORECASE)
    if not m:
        info["reason"] = "未找到 inject 调用行"
        return info

    base = str(bat_path.parent) + os.sep
    inject = m.group(1).replace("%~dp0", base).replace("%%", "%")
    game_exe = m.group(2).replace("%~dp0", base).replace("%%", "%")
    hook = m.group(3).replace("%~dp0", base).replace("%%", "%")
    inject = os.path.normpath(inject)
    game_exe = os.path.normpath(game_exe)
    hook = os.path.normpath(hook)
    info.update({"inject": inject, "game_exe": game_exe, "hook": hook})

    if not os.path.isfile(inject):
        info["reason"] = f"inject.exe 不存在: {inject}"
        return info
    if not os.path.isfile(game_exe):
        info["reason"] = f"游戏主程序不存在: {game_exe}"
        return info
    if not os.path.isfile(hook):
        info["reason"] = f"hook DLL 不存在: {hook}"
        return info

    exe_bits = get_exe_bitness(game_exe)
    hook_bits = get_exe_bitness(hook)
    if exe_bits and hook_bits and exe_bits != hook_bits:
        info["reason"] = f"位数不符：游戏 {exe_bits} 位 / hook {hook_bits} 位"
        return info

    info["valid"] = True
    info["reason"] = "ok"
    return info


def _escape_bat_percent(path_str: str) -> str:
    """将写入 .bat 的路径中的 % 转义为 %%，避免 cmd 展开环境变量导致路径截断。"""
    return str(path_str).replace("%", "%%")


def build_bat_text(mtool_dir: str, folder_path: str, game_exe: str, hook_dll: str) -> str:
    tool_dir = Path(mtool_dir) / "Tool"
    inject = tool_dir / "loaders" / "inject.exe"
    nw = tool_dir / "nw.exe"

    folder = Path(folder_path)
    try:
        rel_exe = Path(game_exe).resolve().relative_to(folder.resolve()).as_posix().replace("/", "\\")
    except Exception:
        rel_exe = Path(game_exe).name

    esc_inject = _escape_bat_percent(str(inject))
    esc_rel_exe = _escape_bat_percent(rel_exe)
    esc_hook = _escape_bat_percent(str(hook_dll))
    esc_nw = _escape_bat_percent(str(nw))
    esc_tool_dir = _escape_bat_percent(str(tool_dir))

    lines = [
        "@chcp 65001 >nul",
        "@cd /d \"%~dp0\"",
        f"\"{esc_inject}\" \"%~dp0{esc_rel_exe}\" \"{esc_hook}\"",
        f"start \"\" \"{esc_nw}\" \"{esc_tool_dir}\"",
    ]
    return "\r\n".join(lines) + "\r\n"


def ensure_launch_bat(folder_path: str, game_exe: str, mtool_dir: str,
                      engine_type: Optional[str]) -> Dict[str, Any]:
    """
    保证游戏目录下有一份可用的联动脚本。

    返回: {path, action: existing|created|repaired, hook, bits, backup, reason}
    """
    hook, bits, bits_source = choose_hook(mtool_dir, engine_type, game_exe)
    existing = find_launch_bat(folder_path)

    if existing is not None:
        info = inspect_launch_bat(existing)
        # 已被 MTool 生成且完全可用 -> 直接用，尊重 MTool 自己的判定
        if info.get("valid"):
            hook_bits = get_exe_bitness(info["hook"]) or bits
            return {
                "path": str(existing),
                "action": "existing",
                "hook": info["hook"],
                "bits": hook_bits,
                "backup": None,
                "reason": "复用 MTool 已生成的联动脚本",
            }
        reason = info.get("reason", "不可用")
    else:
        reason = "目录下没有联动脚本"

    if not os.path.isfile(str(hook)):
        return {
            "path": str(existing) if existing else "",
            "action": "failed",
            "hook": str(hook),
            "bits": bits,
            "backup": None,
            "reason": f"缺少 {hook.name}，无法生成联动脚本",
        }

    backup = None
    if existing is not None:
        backup = existing.with_suffix(existing.suffix + time.strftime(".bak_%Y%m%d_%H%M%S"))
        try:
            existing.replace(backup)
        except Exception:
            backup = None

    target = Path(folder_path) / BAT_CANDIDATES[0]
    try:
        target.write_text(
            build_bat_text(mtool_dir, folder_path, game_exe, str(hook)),
            encoding="utf-8",
            newline="",
        )
    except Exception as e:
        return {
            "path": str(target),
            "action": "failed",
            "hook": str(hook),
            "bits": bits,
            "backup": str(backup) if backup else None,
            "reason": f"写入联动脚本失败: {e}",
        }

    return {
        "path": str(target),
        "action": "repaired" if existing is not None else "created",
        "hook": str(hook),
        "bits": bits,
        "backup": str(backup) if backup else None,
        "reason": f"{reason}；已{'重建' if existing is not None else '生成'}（{bits} 位，依据 {bits_source}）",
    }


# ---------------------------------------------------------
# MTool 侧的 per-game 认知记录
# ---------------------------------------------------------
def _normalize_exe_for_md5(game_exe: str) -> str:
    return os.path.normpath(os.path.abspath(str(game_exe))).replace("/", "\\").lower()


def launch_record_path(mtool_dir: str, game_exe: str) -> Path:
    norm_exe = _normalize_exe_for_md5(game_exe)
    key = hashlib.md5(norm_exe.encode("utf-8")).hexdigest()
    return Path(mtool_dir) / "Tool" / "gameLaunchs" / key


def ensure_launch_record(mtool_dir: str, game_exe: str, hook_dll: str, bits: int) -> Dict[str, Any]:
    """
    维护 Tool\\gameLaunchs\\<md5(标准化小写 exe 完整路径)>。
    已存在则只修正 dllPath / is64Bit，保留用户在 MTool 里的其它选项。
    """
    path = launch_record_path(mtool_dir, game_exe)
    norm_exe = os.path.normpath(os.path.abspath(str(game_exe))).replace("/", "\\")
    is64 = bits == 64
    data: Dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig")) or {}
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}

    created = not data
    data.setdefault("gameExe", norm_exe)
    data.setdefault("injectAtOEP", True)
    data.setdefault("makeLaunchBat", True)
    data.setdefault("lazyInject", True)
    data.setdefault("injectOnTheFly", False)
    data.setdefault("packageRelease", False)
    data.setdefault("selfNWStart", False)

    data["gameExe"] = norm_exe
    data["dllPath"] = str(hook_dll)

    const_args = data.get("constArgs")
    if not isinstance(const_args, dict):
        const_args = {}
    const_args["gameExe"] = norm_exe
    const_args["dllPath"] = str(hook_dll)
    const_args["is64Bit"] = is64
    const_args.setdefault("needEnglishPath", True)
    const_args.setdefault("needEnglishExe", False)
    const_args.setdefault("engPathRegxp", None)
    data["constArgs"] = const_args

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        return {"path": str(path), "written": True, "created": created}
    except Exception as e:
        return {"path": str(path), "written": False, "created": created, "error": str(e)}


# ---------------------------------------------------------
# 启动与关联校验
# ---------------------------------------------------------
def run_launch_bat(bat_path: str, folder_path: str) -> bool:
    """
    用隐藏控制台执行联动脚本（脚本内部的 start 仍会正常弹出 MTool 窗口）。
    绝不回退到会闪黑窗的 os.startfile(bat_path)，若 cmd.exe 启动异常则直接无窗口执行解析出的命令。
    """
    if not IS_WINDOWS:
        return False
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            cwd=folder_path,
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
        )
        return True
    except Exception:
        try:
            info = inspect_launch_bat(Path(bat_path))
            if info.get("valid") and info.get("inject") and info.get("game_exe") and info.get("hook"):
                subprocess.Popen(
                    [info["inject"], info["game_exe"], info["hook"]],
                    cwd=folder_path,
                    creationflags=CREATE_NO_WINDOW,
                    close_fds=True,
                )
                tool_dir = Path(info["inject"]).resolve().parent.parent
                nw_exe = tool_dir / "nw.exe"
                if nw_exe.is_file():
                    subprocess.Popen(
                        [str(nw_exe), str(tool_dir)],
                        cwd=str(tool_dir),
                        creationflags=CREATE_NO_WINDOW,
                        close_fds=True,
                    )
                return True
        except Exception:
            pass
        return False


def is_dll_loaded(pid: Optional[int], dll_name: str) -> Optional[bool]:
    """
    枚举目标进程模块，判断 hook DLL 是否真的加载。
    WOW64 下用 TH32CS_SNAPMODULE32 才能看到 32 位进程的模块；权限不足返回 None。
    """
    if not IS_WINDOWS or not pid:
        return None
    TH32CS_SNAPMODULE = 0x00000008
    TH32CS_SNAPMODULE32 = 0x00000010
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    ERROR_BAD_LENGTH = 24

    class MODULEENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong),
            ("th32ModuleID", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong),
            ("GlblcntUsage", ctypes.c_ulong),
            ("ProccntUsage", ctypes.c_ulong),
            ("modBaseAddr", ctypes.c_void_p),
            ("modBaseSize", ctypes.c_ulong),
            ("hModule", ctypes.c_void_p),
            ("szModule", ctypes.c_wchar * 256),
            ("szExePath", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    target = dll_name.lower()
    for _ in range(6):
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, int(pid))
        if not snap or snap == INVALID_HANDLE_VALUE:
            return None
        try:
            me = MODULEENTRY32W()
            me.dwSize = ctypes.sizeof(MODULEENTRY32W)
            if not kernel32.Module32FirstW(snap, ctypes.byref(me)):
                err = ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else kernel32.GetLastError()
                if err == ERROR_BAD_LENGTH:
                    time.sleep(0.2)
                    continue
                return None
            while True:
                if me.szModule.lower() == target:
                    return True
                if not kernel32.Module32NextW(snap, ctypes.byref(me)):
                    return False
        finally:
            try:
                kernel32.CloseHandle(snap)
            except Exception:
                pass
    return None


def wait_dll_loaded(pid_getter, dll_name: str, timeout: float = 25.0, interval: float = 0.7) -> Optional[bool]:
    """
    pid_getter() 每次返回当前真实游戏 PID（可能从启动器派生到子进程）。
    返回 True=已关联, False=始终未加载, None=无法判定。
    """
    deadline = time.time() + timeout
    unknown = False
    while time.time() < deadline:
        pid = pid_getter()
        if pid:
            loaded = is_dll_loaded(pid, dll_name)
            if loaded is True:
                return True
            if loaded is None:
                unknown = True
        time.sleep(interval)
    return None if unknown else False
